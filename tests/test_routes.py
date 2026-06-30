import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path


def test_health_returns_ok(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_index_renders_two_chat_panes_with_env_defaults(client):
    response = client.get("/")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'name="left_chat_id"' in body
    assert 'name="right_chat_id"' in body
    assert "Жена" in body
    assert "Семейный чат" in body


def test_url_params_override_default_chats(client):
    response = client.get("/?left_chat_id=3&right_chat_id=1")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Созвон" in body
    assert "Привет" in body
    assert "media" in body


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


def test_index_renders_photo_media(client):
    response = client.get("/?right_chat_id=2")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'src="/media/chat-2-message-20.jpg"' in body
    assert 'class="message-photo"' in body


def test_index_renders_generic_media_placeholder(client):
    response = client.get("/?left_chat_id=3")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'class="message-media-placeholder"' in body
    assert ">media<" in body
    assert "[media/service message]" not in body


def test_index_includes_legacy_meta_refresh(client):
    response = client.get("/")
    body = response.get_data(as_text=True)

    assert '<meta http-equiv="refresh" content="7">' in body


def test_legacy_chat_route_redirects_to_left_pane(client):
    response = client.get("/chats/1")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/?left_chat_id=1")


def test_media_file_route_serves_cached_photo(client):
    media_dir = Path(client.application.config["MEDIA_CACHE_DIR"])
    media_dir.mkdir(parents=True, exist_ok=True)
    media_file = media_dir / "chat-2-message-20.jpg"
    media_file.write_bytes(b"fake-jpeg")

    response = client.get("/media/chat-2-message-20.jpg")

    assert response.status_code == 200
    assert response.data == b"fake-jpeg"


def test_media_file_route_rejects_missing_file(client):
    response = client.get("/media/../secret.jpg")

    assert response.status_code == 404


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


class FakeMessageFile:
    def __init__(self, ext=".jpg", mime_type="image/jpeg"):
        self.ext = ext
        self.mime_type = mime_type


class FakePhotoMessage:
    def __init__(self, message_id=40, text="", photo=True, media=True):
        self.id = message_id
        self.message = text
        self.sender = None
        self.date = datetime(2026, 6, 24, 10, 0, tzinfo=timezone.utc)
        self.incoming = True
        self.photo = object() if photo else None
        self.media = object() if media else None
        self.action = None
        self.file = FakeMessageFile()


class FakeDownloadClient:
    def __init__(self):
        self.calls = []

    async def download_media(self, message, filename):
        self.calls.append((message.id, filename))
        Path(filename).write_bytes(b"img")
        return filename


def test_build_message_summary_keeps_text_only_message(tmp_path):
    from app.telegram_client import TelegramService

    service = TelegramService("1", "hash", tmp_path, "test")
    message = FakePhotoMessage(message_id=50, text="Привет", photo=False, media=False)

    summary = asyncio.run(service._build_message_summary(FakeDownloadClient(), 1, message))

    assert summary.text == "Привет"
    assert summary.has_media is False
    assert summary.media_kind == "none"


def test_build_message_summary_downloads_photo_and_sets_media(tmp_path):
    from app.telegram_client import TelegramService

    service = TelegramService("1", "hash", tmp_path, "test", media_cache_dir=tmp_path / "media")
    client = FakeDownloadClient()
    message = FakePhotoMessage(message_id=51, text="")

    summary = asyncio.run(service._build_message_summary(client, 5, message))

    assert summary.media_kind == "photo"
    assert summary.has_media is True
    assert summary.media_filename == "chat-5-message-51.jpg"
    assert client.calls == [(51, str(tmp_path / "media" / "chat-5-message-51.jpg"))]


def test_build_message_summary_preserves_photo_caption(tmp_path):
    from app.telegram_client import TelegramService

    service = TelegramService("1", "hash", tmp_path, "test", media_cache_dir=tmp_path / "media")
    summary = asyncio.run(service._build_message_summary(FakeDownloadClient(), 5, FakePhotoMessage(message_id=52, text="Подпись")))

    assert summary.media_kind == "photo"
    assert summary.text == "Подпись"


def test_build_message_summary_uses_generic_media_placeholder(tmp_path):
    from app.telegram_client import TelegramService

    service = TelegramService("1", "hash", tmp_path, "test")
    message = FakePhotoMessage(message_id=53, text="", photo=False, media=True)

    summary = asyncio.run(service._build_message_summary(FakeDownloadClient(), 7, message))

    assert summary.media_kind == "generic"
    assert summary.media_label == "Медиа"
    assert summary.text == ""


def test_cache_photo_reuses_existing_file(tmp_path):
    from app.telegram_client import TelegramService

    media_dir = tmp_path / "media"
    media_dir.mkdir()
    existing = media_dir / "chat-8-message-54.jpg"
    existing.write_bytes(b"img")
    service = TelegramService("1", "hash", tmp_path, "test", media_cache_dir=media_dir)
    client = FakeDownloadClient()

    filename = asyncio.run(service._cache_photo(client, 8, FakePhotoMessage(message_id=54)))

    assert filename == "chat-8-message-54.jpg"
    assert client.calls == []


def test_media_cache_limit_removes_oldest_files(tmp_path):
    from app.telegram_client import TelegramService

    media_dir = tmp_path / "media"
    media_dir.mkdir()
    old_file = media_dir / "old.jpg"
    new_file = media_dir / "new.jpg"
    old_file.write_bytes(b"12345")
    new_file.write_bytes(b"67890")
    os.utime(old_file, (1, 1))
    os.utime(new_file, (2, 2))
    service = TelegramService("1", "hash", tmp_path, "test", media_cache_dir=media_dir, media_cache_limit_bytes=5)

    service._enforce_media_cache_limit()

    assert not old_file.exists()
    assert new_file.exists()
