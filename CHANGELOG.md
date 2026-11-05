# Changelog

## Unreleased

- Preserved the last successful selected-pane results across temporary auto-refresh failures, preventing a working page
  from turning into `Telegram временно недоступен` after a transient Telegram RPC outage.
- Added `PINNED_CHATS` so important choices remain in both selectors when full dialog enumeration times out.
- Set the deployed left default to `@isaev_live_bot` while retaining `Любимая` as a pinned option.
- Changed the dual-pane loader to use one process-lifetime event loop and authorized Telethon client, with serialized,
  deduplicated selected histories, explicit task cancellation, and dialog-timeout fallback on the same client.
- Added a targeted `messages.Search` path for bot-user histories where Telegram leaves `GetHistory` unanswered, returning
  up to `MESSAGE_LIMIT`; `GetPeerDialogs` remains the one-message emergency fallback.
- Removed the redundant remote authorization preflight from page loading because it could stall the immediately following
  bot-history Search; readiness retains the remote authorization check.
- Serialized selected-pane reads on the shared Telegram session because concurrent bot-history RPCs could time out and
  degrade the affected pane to the one-message fallback.
- Reused one process-lifetime Telethon event loop and MTProto connection backed by a disposable authorized session copy,
  preventing repeated connections from poisoning bot-history Search on later refreshes.
- Upgraded Telethon from `1.36.0` to `1.45.0` for the current Telegram MTProto layer and request handling.
- Added a 60-second bot-history Search circuit breaker so 30-second auto-refresh does not continuously reconnect and
  prolong a transient Telegram-side timeout.
- Added safe Telegram entity rendering through Telethon's UTF-16-aware HTML formatter and pinned Bleach sanitization;
  raw HTML and unsafe or non-absolute links are never trusted as markup.
- Bounded Telegram page loading with a shared `TELEGRAM_PAGE_TIMEOUT_SECONDS` deadline (default `10`, valid range `(0, 20]`) and rendered `503` responses during upstream failure.
- Added a short `TELEGRAM_DIALOG_LIST_TIMEOUT_SECONDS` budget and a timeout-only fallback that resolves the two selected chats through one Telegram connection without resetting the page deadline.
- Added a bounded ID-window workaround for Channel/supergroup history when Telethon's normal multi-message iterator stalls; non-bot personal chats keep the iterator path.
- Added independent pane degradation: an expected failure in one selected chat now preserves the successful sibling pane and returns a partial HTTP `200` page with a safe pane-local error.
- Split process liveness (`/health`, `/health/live`) from bounded Telegram readiness (`/health/ready`) and switched the Compose healthcheck to liveness.
- Sanitized Telegram failure logging so upstream exception details are not exposed to clients or logs.
- Added inline rendering for Telegram photo messages with a local on-disk cache capped at `1 GB`.
- Replaced the raw `[media/service message]` fallback with a `media` placeholder for non-photo media.
- Added `MEDIA_CACHE_DIR` and `MEDIA_CACHE_LIMIT_BYTES` configuration for photo storage.
- Simplified the dual-chat main view to dropdown-only chat selection with immediate pane refresh.
- Updated the chat layout with independently scrollable panes and emphasized incoming messages.
- Added `MESSAGE_TIMEZONE`, `LEFT_CHAT_ID`, and `RIGHT_CHAT_ID` configuration.
- Removed the visible `Чат` label from dual-chat selectors and capped selector width at `300px` on wide screens.
