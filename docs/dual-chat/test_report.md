# Test Report: Dual Chat

Дата проверки: 2026-11-03.

## Automated

- `make test` — pass, 64 tests.
- `make lint` — pass, `compileall` completed for app, tests, scripts, and `wsgi.py`.
- `git diff --check` — pass.

Проверены отдельными regression-тестами: один page-level event loop и Telegram client/auth, параллельность и дедупликация
историй, отмена зависших задач, fallback списка диалогов, pane-local ошибки, UTF-16 offsets Telegram entities, raw HTML и
небезопасные URL.

## Manual

- Проверить две панели на ширине iPad.
- Проверить вертикальное складывание на узком экране.
- Проверить входящие и исходящие сообщения в обоих выбранных чатах.

Manual browser/device checks are still recommended on the target iPad Safari iOS 12 device before production use.
