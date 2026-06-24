# Диагностика

## Сервис не открывается

Проверьте контейнеры:

```bash
docker compose ps
docker compose logs -f
```

Проверьте IP Orange Pi:

```bash
hostname -I
```

## Ошибка TELEGRAM_API_ID или TELEGRAM_API_HASH

Проверьте `.env` и перезапустите контейнер:

```bash
docker compose up -d
```

## Telegram session is not authorized

Запустите первичную авторизацию:

```bash
docker compose run --rm telegram-inbox python scripts/init_telegram_session.py
```

## Пустой список сообщений

Сервис показывает только входящие сообщения. Если в выбранном чате последние сообщения были исходящими или сервисными, список может быть пустым. Увеличьте `MESSAGE_LIMIT` в `.env`.
