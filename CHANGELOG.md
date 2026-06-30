# Changelog

## Unreleased

- Added inline rendering for Telegram photo messages with a local on-disk cache capped at `1 GB`.
- Replaced the raw `[media/service message]` fallback with a `media` placeholder for non-photo media.
- Added `MEDIA_CACHE_DIR` and `MEDIA_CACHE_LIMIT_BYTES` configuration for photo storage.
- Simplified the dual-chat main view to dropdown-only chat selection with immediate pane refresh.
- Updated the chat layout with independently scrollable panes and emphasized incoming messages.
- Added `MESSAGE_TIMEZONE`, `LEFT_CHAT_ID`, and `RIGHT_CHAT_ID` configuration.
- Removed the visible `Чат` label from dual-chat selectors and capped selector width at `300px` on wide screens.
