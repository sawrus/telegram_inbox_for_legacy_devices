# Test Report: Dual Chat

Дата проверки: 2026-06-30.

## Automated

- `make test` — pass, 12 tests.
- `make lint` — pass, `compileall` completed for app, tests, scripts, and `wsgi.py`.
- `make build` — pass, Docker image built successfully.

## Manual

- Проверить две панели на ширине iPad.
- Проверить вертикальное складывание на узком экране.
- Проверить входящие и исходящие сообщения в обоих выбранных чатах.

Manual browser/device checks are still recommended on the target iPad Safari iOS 12 device before production use.
