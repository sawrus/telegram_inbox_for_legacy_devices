# План реализации двух панелей чатов

## Архитектура

Основной маршрут `/` строит две независимые модели панелей из общего списка Telegram-чатов. Состояние хранится в query
string: `left_chat_id`, `right_chat_id`, `left_q`, `right_q`. Если chat id не передан в URL, используются env-дефолты
`LEFT_CHAT_ID` и `RIGHT_CHAT_ID`.

## Изменения

- `app/config.py`: добавить `MESSAGE_TIMEZONE`, `LEFT_CHAT_ID`, `RIGHT_CHAT_ID`.
- `app/telegram_client.py`: заменить входящий-only путь на `list_messages`, сохранять direction, форматировать дату через
  `zoneinfo`.
- `app/routes.py`: рендерить две панели на `/`, сохранить `/chats/<id>` как redirect.
- `app/templates/chats.html`: добавить две формы поиска/выбора, списки сообщений и pane-local empty/error states.
- `app/static/style.css`: добавить flex layout, толстый divider, outgoing message style и narrow-screen fallback.

## Риски

- Неверный timezone может ломать вывод сообщений; конфигурационная ошибка должна быть видимой.
- Поиск и выбор в одной панели не должны сбрасывать вторую панель.
- iPad Safari iOS 12 не должен зависеть от современного JS; формы обязаны работать без autosubmit.
