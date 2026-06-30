# Telegram Inbox для локальной сети

Простой Flask-сервис для просмотра сообщений из Telegram через MTProto. Проект рассчитан на запуск внутри домашней сети на Orange Pi Zero 2 с Ubuntu ARM и Docker Compose.

## Возможности

- просмотр двух Telegram-чатов на одном экране;
- независимый поиск и выбор чата для левой и правой панели;
- просмотр входящих и исходящих сообщений выбранных чатов;
- отображение времени сообщений в заданном часовом поясе;
- автообновление страницы через обычный HTML meta refresh;
- фронтенд без SPA-фреймворков, совместимый с iPad Safari iOS 12;
- развёртывание через Docker Compose;
- первичная авторизация Telegram session отдельным скриптом.

## Безопасность

Сервис предназначен для локальной сети. Не публикуйте порт `8080` в интернет без дополнительной авторизации, HTTPS и reverse proxy. Telegram session-файл даёт доступ к аккаунту, поэтому каталог `data/` нельзя коммитить или передавать третьим лицам.

## Быстрый старт на Orange Pi

```bash
git clone <repo-url>
cd test_codex
cp .env.example .env
nano .env
```

Получите `api_id` и `api_hash` на <https://my.telegram.org>, затем укажите их в `.env`.

Создайте Telegram session:

```bash
docker compose run --rm telegram-inbox python scripts/init_telegram_session.py
```

Запустите сервис:

```bash
docker compose up -d --build
```

Откройте с iPad в той же сети:

```text
http://<orange-pi-ip>:8080
```

## Настройки

Основные переменные окружения описаны в `.env.example`:

- `TELEGRAM_API_ID` — числовой API ID Telegram;
- `TELEGRAM_API_HASH` — API hash Telegram;
- `TELEGRAM_SESSION_NAME` — имя session-файла в `/data`;
- `FLASK_SECRET_KEY` — произвольная секретная строка Flask;
- `REFRESH_SECONDS` — интервал автообновления страницы сообщений;
- `MESSAGE_LIMIT` — максимальное число последних сообщений для чтения;
- `MESSAGE_TIMEZONE` — часовой пояс отображения сообщений, по умолчанию `Europe/Samara`;
- `LEFT_CHAT_ID` — чат, выбранный в левой панели при открытии `/`;
- `RIGHT_CHAT_ID` — чат, выбранный в правой панели при открытии `/`.

## Тесты

```bash
make test
```

Тесты используют mock Telegram-клиент и не подключаются к реальному Telegram API.

## Документация

- [Развёртывание на Orange Pi](docs/orangepi-deploy.md)
- [Конфигурация](docs/configuration.md)
- [Совместимость с iPad Safari iOS 12](docs/ipad-ios12-compatibility.md)
- [Диагностика](docs/troubleshooting.md)
