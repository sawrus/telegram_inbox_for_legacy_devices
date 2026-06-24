# Конфигурация

Конфигурация задаётся через `.env`, который подключается в `docker-compose.yml`.

| Переменная | Назначение | Пример |
| --- | --- | --- |
| `TELEGRAM_API_ID` | API ID из my.telegram.org | `123456` |
| `TELEGRAM_API_HASH` | API hash из my.telegram.org | `abcdef...` |
| `TELEGRAM_SESSION_NAME` | Имя session-файла | `telegram-inbox` |
| `FLASK_SECRET_KEY` | Секрет Flask | `long-random-string` |
| `REFRESH_SECONDS` | Интервал автообновления | `30` |
| `MESSAGE_LIMIT` | Лимит последних сообщений | `50` |

Session-файлы хранятся в `./data` на хосте и монтируются в контейнер как `/data`.
