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

Сервис показывает входящие и исходящие сообщения выбранных чатов. Если список пустой, проверьте выбранный чат,
увеличьте `MESSAGE_LIMIT` в `.env` или убедитесь, что Telegram session имеет доступ к этому диалогу.

## Ошибка MESSAGE_TIMEZONE

Укажите IANA-имя часового пояса, например:

```env
MESSAGE_TIMEZONE=Europe/Samara
```

После изменения `.env` перезапустите контейнер:

```bash
docker compose up -d
```
