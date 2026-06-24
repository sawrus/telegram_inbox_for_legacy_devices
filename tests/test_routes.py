def test_health_returns_ok(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_index_shows_chats(client):
    response = client.get("/")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Жена" in body
    assert "/chats/1" in body


def test_chat_messages_show_incoming_messages(client):
    response = client.get("/chats/1")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Привет" in body
    assert "Мария" in body


def test_chat_messages_include_legacy_meta_refresh(client):
    response = client.get("/chats/1")
    body = response.get_data(as_text=True)

    assert '<meta http-equiv="refresh" content="7">' in body



class MessageWithIncoming:
    incoming = True


class OutgoingMessageWithoutIncoming:
    out = True


class IncomingMessageWithoutIncoming:
    out = False


def test_message_direction_supports_telethon_incoming_property():
    from app.telegram_client import TelegramService

    assert TelegramService._is_incoming_message(MessageWithIncoming()) is True


def test_message_direction_falls_back_to_out_property():
    from app.telegram_client import TelegramService

    assert TelegramService._is_incoming_message(OutgoingMessageWithoutIncoming()) is False
    assert TelegramService._is_incoming_message(IncomingMessageWithoutIncoming()) is True
