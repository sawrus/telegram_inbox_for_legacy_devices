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
| `MESSAGE_TIMEZONE` | Часовой пояс отображения времени сообщений | `Europe/Samara` |
| `MEDIA_CACHE_DIR` | Каталог локального кэша фото | `/data/media` |
| `MEDIA_CACHE_LIMIT_BYTES` | Лимит кэша фото в байтах | `1073741824` |
| `LEFT_CHAT_ID` | Чат, открываемый в левой панели по умолчанию | `123456789` |
| `RIGHT_CHAT_ID` | Чат, открываемый в правой панели по умолчанию | `987654321` |

Session-файлы хранятся в `./data` на хосте и монтируются в контейнер как `/data`.
По умолчанию кэш Telegram-фото хранится в `./data/media` на хосте через тот же volume.

`LEFT_CHAT_ID` и `RIGHT_CHAT_ID` используются только как стартовые значения. Параметры URL `left_chat_id` и
`right_chat_id` переопределяют их для конкретной страницы, чтобы автообновление сохраняло выбранные чаты.

Если `MESSAGE_TIMEZONE` задан неверно, сервис показывает ошибку конфигурации вместо страницы сообщений.
Если лимит `MEDIA_CACHE_LIMIT_BYTES` превышен, сервис удаляет самые старые кэшированные изображения, пока размер кэша не вернётся в предел.
