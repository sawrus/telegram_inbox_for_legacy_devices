from datetime import datetime, timezone


def test_health_returns_ok(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_index_renders_two_chat_panes_with_env_defaults(client):
    response = client.get("/")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert '<label class="chat-selector-label" for="left_chat_id">Чат</label>' in body
    assert '<label class="chat-selector-label" for="right_chat_id">Чат</label>' in body
    assert "chat-divider" not in body
    assert 'type="search"' not in body
    assert "Жена" in body
    assert "Семейный чат" in body


def test_url_params_override_default_chats(client):
    response = client.get("/?left_chat_id=3&right_chat_id=1")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Созвон" in body
    assert "Привет" in body


def test_index_hides_global_header_on_main_screen(client):
    response = client.get("/")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert '<header class="header">' not in body


def test_outgoing_messages_are_visible_and_styled(client):
    response = client.get("/?left_chat_id=1")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Я скоро" in body
    assert "Моё" in body
    assert "message-outgoing" in body
    assert "message-incoming" in body


def test_selected_chat_title_is_not_rendered_above_messages(client):
    response = client.get("/?left_chat_id=1")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "<h3>" not in body
    assert "<ol" not in body
    assert "<ul" in body


def test_search_query_params_are_ignored_in_markup(client):
    response = client.get("/?left_q=жен&right_q=раб")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'name="left_q"' not in body
    assert 'name="right_q"' not in body
    assert "Чаты по запросу не найдены." not in body
    assert "Жена" in body
    assert "Работа" in body


def test_index_includes_legacy_meta_refresh(client):
    response = client.get("/")
    body = response.get_data(as_text=True)

    assert '<meta http-equiv="refresh" content="7">' in body


def test_legacy_chat_route_redirects_to_left_pane(client):
    response = client.get("/chats/1")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/?left_chat_id=1")


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


def test_message_dates_are_formatted_in_samara_timezone():
    from app.telegram_client import TelegramService

    service = TelegramService("1", "hash", "/tmp", "test", message_timezone="Europe/Samara")
    formatted = service._format_message_date(datetime(2026, 6, 24, 21, 30, tzinfo=timezone.utc))

    assert formatted == "2026-06-25 01:30:00"


def test_naive_message_dates_are_treated_as_utc():
    from app.telegram_client import TelegramService

    service = TelegramService("1", "hash", "/tmp", "test", message_timezone="Europe/Samara")
    formatted = service._format_message_date(datetime(2026, 6, 24, 21, 30))

    assert formatted == "2026-06-25 01:30:00"


def test_invalid_message_timezone_raises_configuration_error():
    import pytest

    from app.telegram_client import TelegramConfigurationError, TelegramService

    service = TelegramService("1", "hash", "/tmp", "test", message_timezone="Bad/Zone")

    with pytest.raises(TelegramConfigurationError, match="MESSAGE_TIMEZONE is invalid"):
        service.validate_timezone()
