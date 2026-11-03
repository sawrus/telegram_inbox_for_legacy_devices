# Telegram page timeout: root cause

Date: 2026-11-03  
Affected endpoint: `GET /`  
Impact: a slow or unreachable Telegram MTProto connection could occupy a Gunicorn worker until an external timeout and surface as `Internal Server Error`.

## What failed

The page loaded the dialog list and up to two message panes as three sequential synchronous wrappers around Telethon coroutines.
Those wrappers used `asyncio.run` without `asyncio.wait_for`. A stalled connect, authorization check, entity lookup, message
iteration, or media download therefore had no application-level deadline. Independent full timeouts would also have allowed
the total page latency to become the sum of three limits.

After the first containment change, a valid Telegram session could still return a bounded `503`: Telethon's unbounded
`get_dialogs()` may enumerate every dialog and consume the complete page deadline before either selected pane starts.
For at least one supergroup `Channel`, Telethon's normal multi-message history request also stalled, while a one-message
head lookup followed by an explicit descending ID batch completed within the deadline.

The Docker Compose healthcheck used `/health`, but the service did not expose a separate bounded Telegram readiness signal.
Operators could only see that the web process was alive, not whether its upstream dependency was usable.

## Fix

- Added `TELEGRAM_PAGE_TIMEOUT_SECONDS`, default `10`, with strict validation to `(0, 20]`.
- Added one page-level `TelegramService.load_page` operation: it creates one event loop, enters one Telethon client, and
  validates the session auth key locally without an extra network preflight. Remote authorization remains part of
  `/health/ready`; on this session, calling it immediately before `messages.Search` could leave Search unanswered.
- Load deduplicated selected histories sequentially, then use the reserved remainder of the page deadline for the dialog
  task. Concurrent RPCs on this Telegram session could leave bot-history Search unanswered.
- Open one process-lifetime connection from a disposable copy of the authorized SQLite session and reuse its event loop
  across HTTP refreshes. Reconnecting with the same auth key made later bot-history Search calls hang.
- Give full dialog enumeration a separate `TELEGRAM_DIALOG_LIST_TIMEOUT_SECONDS` budget, capped by the remaining page time.
- When dialog enumeration reaches its short timeout, cancel and await that task, then reuse selected-chat summaries already
  resolved on the same client. All still-pending history tasks are also cancelled and awaited before closing the client.
- For `Channel` and supergroup entities only, load the newest message with `limit=1`, then query a bounded descending ID
  window, discard missing IDs, preserve newest-first order, and cap the result at `MESSAGE_LIMIT`. Non-bot user chats retain
  `iter_messages`; bot-user dialogs use `messages.Search` because their `GetHistory` request may remain unanswered, with
  `GetPeerDialogs` retained as a one-message emergency fallback.
- An expected pane failure preserves the sibling pane and selector state, renders a safe pane-local error, and returns HTTP
  `200`; programming errors are not reclassified and continue to propagate.
- Render a safe `503` page when Telegram is unavailable instead of exposing exception text or allowing an unhandled `500`.
- Keep `/health` and `/health/live` independent of Telegram; add bounded `/health/ready` returning `200` or `503`.
- Point the Compose healthcheck at `/health/live`.

## Prevention and operational notes

Regression tests cover the single process-level event loop/client/auth flow, serialized and deduplicated histories, task
cancellation, same-client dialog fallback, pane-local degradation, safe rendered `503` behavior, liveness isolation, and
bounded readiness. Logs record only the failing route and exception type; upstream messages can contain sensitive account or
session details and are not logged.

A circuit breaker was deliberately deferred. The fixed deadline prevents worker starvation, and a breaker would add shared
state, recovery thresholds, and multi-worker coordination that this small single-service deployment does not currently need.
If repeated Telegram failures create excessive connection load, add a measured breaker with explicit open/half-open metrics
as a separate hardening change.

Rollback is code/config rollback to the preceding image. `TELEGRAM_PAGE_TIMEOUT_SECONDS` is additive, so no data migration is required.
