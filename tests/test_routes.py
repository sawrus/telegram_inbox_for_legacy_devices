import asyncio
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app import create_app
from app.telegram_client import (
    ChatSummary,
    MessageSummary,
    PageLoadResult,
    TelegramConfigurationError,
    TelegramTimeoutError,
    TelegramUnavailableError,
)


def test_health_returns_ok(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_liveness_does_not_call_telegram(client):
    service = client.application.config["TELEGRAM_SERVICE"]

    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}
    assert service.timeouts == []


def test_readiness_calls_telegram_with_bounded_timeout(client):
    service = client.application.config["TELEGRAM_SERVICE"]

    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ready"}
    assert 0 < service.timeouts[0] <= 10.0


def test_readiness_returns_safe_503_when_telegram_is_unavailable(client):
    class UnavailableService:
        def check_readiness(self, timeout_seconds=None):
            raise TelegramUnavailableError("secret upstream detail")

    app = create_app(type("TestConfig", (), dict(client.application.config)), UnavailableService())

    response = app.test_client().get("/health/ready")

    assert response.status_code == 503
    assert response.get_json() == {"status": "unavailable"}
    assert "secret" not in response.get_data(as_text=True)


def test_index_renders_two_chat_panes_with_env_defaults(client):
    response = client.get("/")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'name="left_chat_id"' in body
    assert 'name="right_chat_id"' in body
    assert "Жена" in body
    assert "Семейный чат" in body


def test_index_keeps_configured_pinned_chat_in_both_selectors(client):
    config = dict(client.application.config)
    config["PINNED_CHATS"] = ((1363824162, "Любимая"),)
    app = create_app(type("TestConfig", (), config), client.application.config["TELEGRAM_SERVICE"])

    response = app.test_client().get("/")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert body.count('value="1363824162"') == 2
    assert body.count("Любимая") == 2


def test_index_calls_page_loader_once_with_bounded_budgets(client):
    service = client.application.config["TELEGRAM_SERVICE"]

    response = client.get("/")

    assert response.status_code == 200
    assert service.page_calls == [(1, 2, 3.0, 10.0)]


def test_index_does_not_fall_back_for_non_timeout_dialog_error(client):
    class UnexpectedFailureService:
        def load_page(self, left_chat_id, right_chat_id, dialog_timeout_seconds, timeout_seconds=None):
            raise RuntimeError("unexpected failure detail")

    service = UnexpectedFailureService()
    config = dict(client.application.config)
    app = create_app(type("TestConfig", (), config), service)

    with pytest.raises(RuntimeError, match="unexpected failure detail"):
        app.test_client().get("/?left_chat_id=1&right_chat_id=2")


def test_readiness_does_not_hide_programming_error(client):
    class BrokenService:
        def check_readiness(self, timeout_seconds=None):
            raise RuntimeError("programming defect")

    config = dict(client.application.config)
    app = create_app(type("TestConfig", (), config), BrokenService())

    with pytest.raises(RuntimeError, match="programming defect"):
        app.test_client().get("/health/ready")


def test_message_loading_does_not_hide_programming_error(client):
    class BrokenMessageService:
        def load_page(self, left_chat_id, right_chat_id, dialog_timeout_seconds, timeout_seconds=None):
            raise RuntimeError("message programming defect")

    config = dict(client.application.config)
    app = create_app(type("TestConfig", (), config), BrokenMessageService())

    with pytest.raises(RuntimeError, match="message programming defect"):
        app.test_client().get("/?left_chat_id=1")


def test_right_expected_failure_preserves_left_pane_and_returns_200(client):
    class PartiallyAvailableService:
        def load_page(self, left_chat_id, right_chat_id, dialog_timeout_seconds, timeout_seconds=None):
            return PageLoadResult(
                chats=[ChatSummary(id=1, title="Left selected"), ChatSummary(id=2, title="Right selected")],
                messages_by_chat_id={
                    1: [MessageSummary(id=10, text="Left survives", sender="Sender", date="", incoming=True)],
                    2: [],
                },
                errors_by_chat_id={2: TelegramUnavailableError("right upstream detail")},
            )

    config = dict(client.application.config)
    app = create_app(type("TestConfig", (), config), PartiallyAvailableService())

    response = app.test_client().get("/?left_chat_id=1&right_chat_id=2")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Left survives" in body
    assert "Left selected" in body
    assert "Right selected" in body
    assert 'value="1" selected' in body
    assert 'value="2" selected' in body
    assert "Telegram временно недоступен" in body
    assert "right upstream detail" not in body


def test_dialog_timeout_without_selected_chats_returns_safe_503(client):
    class DialogTimeoutService:
        def load_page(self, left_chat_id, right_chat_id, dialog_timeout_seconds, timeout_seconds=None):
            raise TelegramTimeoutError("dialog timeout detail")

    service = DialogTimeoutService()
    config = dict(client.application.config)
    config["LEFT_CHAT_ID"] = ""
    config["RIGHT_CHAT_ID"] = ""
    app = create_app(type("TestConfig", (), config), service)

    response = app.test_client().get("/")

    assert response.status_code == 503
    assert "dialog timeout detail" not in response.get_data(as_text=True)


def test_index_renders_safe_503_when_telegram_is_unavailable(client):
    class UnavailableService:
        def load_page(self, left_chat_id, right_chat_id, dialog_timeout_seconds, timeout_seconds=None):
            raise TelegramUnavailableError("phone number and upstream detail")

    service = UnavailableService()
    app = create_app(type("TestConfig", (), dict(client.application.config)), service)

    response = app.test_client().get("/")
    body = response.get_data(as_text=True)

    assert response.status_code == 503
    assert "Telegram временно недоступен" in body
    assert "phone number" not in body


def test_index_cancels_hanging_message_fetch_within_shared_budget(client, tmp_path):
    from app.telegram_client import TelegramService

    service = TelegramService("1", "hash", tmp_path, "test", page_timeout_seconds=0.03)
    cancelled_chat_ids = []

    class HangingClient:
        session = type("Session", (), {"auth_key": object()})()

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_value, traceback):
            return None

        async def is_user_authorized(self):
            return True

        async def get_dialogs(self):
            return [
                type("Dialog", (), {"id": 1, "name": "Жена"})(),
                type("Dialog", (), {"id": 2, "name": "Семья"})(),
            ]

        async def get_entity(self, chat_id):
            return type("Entity", (), {"id": chat_id, "title": f"Chat {chat_id}"})()

        def iter_messages(self, entity, limit):
            async def messages():
                try:
                    await asyncio.sleep(1)
                    if False:
                        yield None
                finally:
                    cancelled_chat_ids.append(entity.id)

            return messages()

    async def get_client():
        return HangingClient()

    service._client = get_client
    config = dict(client.application.config)
    config["TELEGRAM_PAGE_TIMEOUT_SECONDS"] = 0.03
    app = create_app(type("TestConfig", (), config), service)
    started_at = time.monotonic()

    response = app.test_client().get("/")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert time.monotonic() - started_at < 0.5
    assert body.count("Telegram временно недоступен") == 2
    assert "Жена" in body
    assert "Семья" in body
    assert cancelled_chat_ids == []


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
    from app.telegram_client import TelegramConfigurationError, TelegramService

    service = TelegramService("1", "hash", "/tmp", "test", message_timezone="Bad/Zone")

    with pytest.raises(TelegramConfigurationError, match="MESSAGE_TIMEZONE is invalid"):
        service.validate_timezone()


@pytest.mark.parametrize("timeout_seconds", [0, -1, 20.1])
def test_telegram_page_timeout_must_be_in_strict_range(timeout_seconds):
    from app.telegram_client import TelegramConfigurationError, TelegramService

    with pytest.raises(TelegramConfigurationError, match="TELEGRAM_PAGE_TIMEOUT_SECONDS"):
        TelegramService("1", "hash", "/tmp", "test", page_timeout_seconds=timeout_seconds)


@pytest.mark.parametrize("timeout_seconds", ["0", "-1", "5.1", "invalid"])
def test_telegram_dialog_list_timeout_must_be_in_strict_range(monkeypatch, timeout_seconds):
    from app.config import _telegram_dialog_list_timeout_seconds

    monkeypatch.setenv("TELEGRAM_DIALOG_LIST_TIMEOUT_SECONDS", timeout_seconds)

    with pytest.raises(RuntimeError, match="TELEGRAM_DIALOG_LIST_TIMEOUT_SECONDS"):
        _telegram_dialog_list_timeout_seconds()


def test_pinned_chats_are_parsed_from_environment(monkeypatch):
    from app.config import _pinned_chats

    monkeypatch.setenv("PINNED_CHATS", "1363824162:Любимая;8978077889:isaev-live")

    assert _pinned_chats() == ((1363824162, "Любимая"), (8978077889, "isaev-live"))


@pytest.mark.parametrize("value", ["bad", "abc:Title", "1:"])
def test_invalid_pinned_chats_raise_configuration_error(monkeypatch, value):
    from app.config import _pinned_chats

    monkeypatch.setenv("PINNED_CHATS", value)

    with pytest.raises(RuntimeError, match="PINNED_CHATS"):
        _pinned_chats()


def test_telegram_operation_timeout_raises_domain_error(tmp_path):
    from app.telegram_client import TelegramService

    service = TelegramService("1", "hash", tmp_path, "test", page_timeout_seconds=0.01)
    operation_was_cancelled = False

    async def never_finishes():
        nonlocal operation_was_cancelled
        try:
            await asyncio.sleep(1)
        finally:
            operation_was_cancelled = True

    service._list_chats = never_finishes
    started_at = time.monotonic()

    with pytest.raises(TelegramTimeoutError, match="temporarily unavailable"):
        service.list_chats()

    assert time.monotonic() - started_at < 0.5
    assert operation_was_cancelled is True


def test_known_operational_failures_are_translated_to_domain_error(tmp_path):
    from sqlite3 import OperationalError

    from telethon.errors import RPCError

    from app.telegram_client import TelegramService

    failures = [
        ConnectionError("connection detail"),
        OperationalError("database detail"),
        RPCError(None, "rpc detail", 500),
    ]

    for failure in failures:
        service = TelegramService("1", "hash", tmp_path, "test")

        async def fail(failure=failure):
            raise failure

        service._list_chats = fail

        with pytest.raises(TelegramUnavailableError, match="temporarily unavailable"):
            service.list_chats()


@pytest.mark.parametrize(
    "error_type",
    [RuntimeError, OSError, TelegramConfigurationError, TelegramUnavailableError],
)
def test_unexpected_or_existing_domain_errors_are_not_reclassified(tmp_path, error_type):
    from app.telegram_client import TelegramService

    service = TelegramService("1", "hash", tmp_path, "test")

    async def fail():
        raise error_type("original detail")

    service._list_chats = fail

    with pytest.raises(error_type, match="original detail"):
        service.list_chats()


def test_resolve_chat_summaries_uses_one_client_for_unique_ids(tmp_path):
    from app.telegram_client import TelegramService

    class Entity:
        def __init__(self, entity_id, title):
            self.id = entity_id
            self.title = title

    class FakeClient:
        def __init__(self):
            self.enter_count = 0
            self.requested_ids = []

        async def __aenter__(self):
            self.enter_count += 1
            return self

        async def __aexit__(self, exc_type, exc_value, traceback):
            return None

        async def is_user_authorized(self):
            return True

        async def get_entity(self, chat_id):
            self.requested_ids.append(chat_id)
            return Entity(chat_id, f"Chat {chat_id}")

    service = TelegramService("1", "hash", tmp_path, "test")
    client = FakeClient()

    async def get_client():
        return client

    service._client = get_client

    summaries = service.resolve_chat_summaries([1, 2, 1])

    assert [(summary.id, summary.title) for summary in summaries] == [(1, "Chat 1"), (2, "Chat 2")]
    assert client.enter_count == 1
    assert client.requested_ids == [1, 2]


class FakeHistoryMessage:
    def __init__(self, message_id):
        self.id = message_id


class FakeChannelHistoryClient:
    def __init__(self, latest_message, messages_by_id=None):
        self.latest_message = latest_message
        self.messages_by_id = messages_by_id or {}
        self.calls = []

    async def get_messages(self, entity, **kwargs):
        self.calls.append(kwargs)
        if kwargs == {"limit": 1}:
            return [self.latest_message] if self.latest_message else []
        return [self.messages_by_id.get(message_id) for message_id in kwargs["ids"]]

    def iter_messages(self, entity, limit):
        raise AssertionError("Channel history must not use iter_messages")


def test_channel_history_uses_bounded_id_batch_and_handles_gaps(tmp_path):
    from telethon.tl.types import Channel

    from app.telegram_client import TelegramService

    service = TelegramService("1", "hash", tmp_path, "test", message_limit=3)
    latest = FakeHistoryMessage(105)
    client = FakeChannelHistoryClient(
        latest,
        {
            104: FakeHistoryMessage(104),
            102: FakeHistoryMessage(102),
            101: FakeHistoryMessage(101),
        },
    )
    entity = Channel(id=7, title="Channel", photo=None, date=None, megagroup=True)

    messages = asyncio.run(service._fetch_messages(client, entity))

    assert [message.id for message in messages] == [105, 104, 102]
    assert client.calls[0] == {"limit": 1}
    assert client.calls[1] == {"ids": [104, 103, 102, 101, 100]}


def test_channel_history_handles_empty_history_without_id_batch(tmp_path):
    from telethon.tl.types import Channel

    from app.telegram_client import TelegramService

    service = TelegramService("1", "hash", tmp_path, "test", message_limit=3)
    client = FakeChannelHistoryClient(None)
    entity = Channel(id=7, title="Channel", photo=None, date=None, broadcast=True)

    messages = asyncio.run(service._fetch_messages(client, entity))

    assert messages == []
    assert client.calls == [{"limit": 1}]


def test_channel_history_candidate_batch_stays_bounded_for_large_message_limit(tmp_path):
    from telethon.tl.types import Channel

    from app.telegram_client import CHANNEL_HISTORY_MAX_CANDIDATE_IDS, TelegramService

    service = TelegramService("1", "hash", tmp_path, "test", message_limit=10_000)
    client = FakeChannelHistoryClient(FakeHistoryMessage(1_000))
    entity = Channel(id=7, title="Channel", photo=None, date=None, megagroup=True)

    asyncio.run(service._fetch_messages(client, entity))

    assert len(client.calls[1]["ids"]) == CHANNEL_HISTORY_MAX_CANDIDATE_IDS - 1


def test_user_history_keeps_iter_messages_path(tmp_path):
    from telethon.tl.types import User

    from app.telegram_client import TelegramService

    class UserHistoryClient:
        def __init__(self):
            self.iterator_limits = []

        async def get_messages(self, entity, **kwargs):
            raise AssertionError("User history must not use get_messages")

        async def _messages(self):
            yield FakeHistoryMessage(8)
            yield FakeHistoryMessage(7)

        def iter_messages(self, entity, limit):
            self.iterator_limits.append(limit)
            return self._messages()

    service = TelegramService("1", "hash", tmp_path, "test", message_limit=2)
    client = UserHistoryClient()
    entity = User(id=9, first_name="User")

    messages = asyncio.run(service._fetch_messages(client, entity))

    assert [message.id for message in messages] == [8, 7]
    assert client.iterator_limits == [2]


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
