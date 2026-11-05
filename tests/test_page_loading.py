import asyncio
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from telethon import types

from app.telegram_client import TelegramConfigurationError, TelegramService, TelegramUnavailableError


class FakeEntity:
    def __init__(self, entity_id):
        self.id = entity_id
        self.title = f"Chat {entity_id}"


class FakeMessage:
    def __init__(self, message_id):
        self.id = message_id
        self.message = f"Message {message_id}"
        self.entities = []
        self.sender = None
        self.date = datetime(2026, 11, 3, tzinfo=timezone.utc)
        self.incoming = True
        self.photo = None
        self.media = None
        self.action = None


class PageClient:
    def __init__(
        self,
        *,
        dialog_delay=0,
        failing_chat_id=None,
        programming_error=False,
        timeout_chat_id=None,
        entity_failure=False,
        dialog_failure=False,
    ):
        self.dialog_delay = dialog_delay
        self.failing_chat_id = failing_chat_id
        self.programming_error = programming_error
        self.timeout_chat_id = timeout_chat_id
        self.entity_failure = entity_failure
        self.dialog_failure = dialog_failure
        self.enter_count = 0
        self.authorization_count = 0
        self.entity_ids = []
        self.history_ids = []
        self.active_histories = 0
        self.histories_started = asyncio.Event()
        self.dialog_cancelled = False
        self.dialog_started_after_histories = False
        self.session = SimpleNamespace(auth_key=object())

    async def __aenter__(self):
        self.enter_count += 1
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        return None

    async def is_user_authorized(self):
        self.authorization_count += 1
        return True

    async def get_dialogs(self):
        try:
            self.dialog_started_after_histories = bool(self.entity_ids) and len(self.history_ids) == len(
                set(self.entity_ids)
            )
            if self.dialog_delay:
                await asyncio.sleep(self.dialog_delay)
            if self.dialog_failure:
                raise ConnectionError("dialog unavailable")
            return [type("Dialog", (), {"id": 1, "name": "Dialog 1"})()]
        finally:
            if self.dialog_delay:
                self.dialog_cancelled = True

    async def get_entity(self, chat_id):
        self.entity_ids.append(chat_id)
        if self.entity_failure:
            raise ConnectionError("entity unavailable")
        return FakeEntity(chat_id)

    def iter_messages(self, entity, limit):
        async def messages():
            self.history_ids.append(entity.id)
            self.active_histories += 1
            if self.active_histories == 2:
                self.histories_started.set()
            await asyncio.wait_for(self.histories_started.wait(), timeout=0.2)
            if entity.id == self.failing_chat_id:
                if self.programming_error:
                    raise RuntimeError("programming defect")
                raise ConnectionError("upstream detail")
            if entity.id == self.timeout_chat_id:
                raise TimeoutError("history timeout")
            yield FakeMessage(entity.id * 10)

        return messages()


def make_service(tmp_path, client):
    service = TelegramService("1", "hash", tmp_path, "test", page_timeout_seconds=0.5)

    async def get_client():
        return client

    service._client = get_client
    return service


def test_runtime_session_copies_authorized_database(tmp_path, monkeypatch):
    service = TelegramService("1", "hash", tmp_path, "test", page_timeout_seconds=0.5)
    service.session_file_path.write_bytes(b"authorized-session")
    temporary_dir = tmp_path / "ephemeral"
    temporary_dir.mkdir()
    monkeypatch.setattr("app.telegram_client.tempfile.mkdtemp", lambda **_kwargs: str(temporary_dir))

    session_path, session_dir = service._create_runtime_session()

    assert session_dir == temporary_dir
    assert Path(f"{session_path}.session").read_bytes() == b"authorized-session"


def test_page_load_uses_cached_input_user_without_network_entity_lookup(tmp_path):
    client = PageClient()

    class CachedSession:
        auth_key = object()

        @staticmethod
        def get_input_entity(chat_id):
            return types.InputPeerUser(chat_id, 123)

        @staticmethod
        def _execute(_query, chat_id):
            return (f"Cached {chat_id}", f"bot_{chat_id}")

    client.session = CachedSession()

    async def unexpected_get_entity(_chat_id):
        raise AssertionError("network entity lookup must not run")

    client.get_entity = unexpected_get_entity
    service = make_service(tmp_path, client)

    async def fetch_bot_messages(_client, entity):
        return [FakeMessage(entity.user_id * 10)]

    service._fetch_bot_messages = fetch_bot_messages

    result = service.load_page(1, 2, dialog_timeout_seconds=0.1, timeout_seconds=0.5)

    assert [message.id for message in result.messages_by_chat_id[1]] == [10]
    assert [message.id for message in result.messages_by_chat_id[2]] == [20]


def test_page_load_uses_one_client_and_loads_distinct_histories(tmp_path):
    client = PageClient()
    client.histories_started.set()
    result = make_service(tmp_path, client).load_page(1, 2, dialog_timeout_seconds=0.1, timeout_seconds=0.5)

    assert client.enter_count == 1
    assert client.authorization_count == 0
    assert sorted(client.entity_ids) == [1, 2]
    assert sorted(client.history_ids) == [1, 2]
    assert [message.id for message in result.messages_by_chat_id[1]] == [10]
    assert [message.id for message in result.messages_by_chat_id[2]] == [20]
    assert client.dialog_started_after_histories is True


def test_selected_histories_finish_before_slow_dialog_loading_starts(tmp_path):
    client = PageClient(dialog_delay=1)
    client.histories_started.set()

    result = make_service(tmp_path, client).load_page(1, 2, dialog_timeout_seconds=0.01, timeout_seconds=0.5)

    assert [message.id for message in result.messages_by_chat_id[1]] == [10]
    assert [message.id for message in result.messages_by_chat_id[2]] == [20]


def test_bot_peer_requests_are_serialized_on_the_shared_client(tmp_path):
    class BotPageClient(PageClient):
        async def get_entity(self, chat_id):
            entity = await super().get_entity(chat_id)
            entity.bot = True
            return entity

    client = BotPageClient()
    service = make_service(tmp_path, client)
    active_requests = 0
    max_active_requests = 0

    async def fetch_messages(_client, entity):
        nonlocal active_requests, max_active_requests
        active_requests += 1
        max_active_requests = max(max_active_requests, active_requests)
        await asyncio.sleep(0.01)
        active_requests -= 1
        return [FakeMessage(entity.id * 10)]

    service._fetch_bot_messages = fetch_messages

    result = service.load_page(1, 2, dialog_timeout_seconds=0.1, timeout_seconds=0.5)

    assert max_active_requests == 1
    assert [message.id for message in result.messages_by_chat_id[1]] == [10]
    assert [message.id for message in result.messages_by_chat_id[2]] == [20]


def test_page_load_reuses_one_service_event_loop(tmp_path):
    client = PageClient()
    client.histories_started.set()
    service = make_service(tmp_path, client)

    service.load_page(1, 2, dialog_timeout_seconds=0.1, timeout_seconds=0.5)
    event_loop = service._event_loop
    service.load_page(1, 2, dialog_timeout_seconds=0.1, timeout_seconds=0.5)

    assert service._event_loop is event_loop
    assert not event_loop.is_closed()


def test_page_load_rejects_session_without_local_auth_key(tmp_path):
    client = PageClient()
    client.session.auth_key = None

    with pytest.raises(TelegramConfigurationError, match="not authorized"):
        make_service(tmp_path, client).load_page(1, 2, dialog_timeout_seconds=0.1, timeout_seconds=0.5)

    assert client.authorization_count == 0


def test_page_load_deduplicates_same_selected_chat(tmp_path):
    client = PageClient()
    client.histories_started.set()

    result = make_service(tmp_path, client).load_page(1, 1, dialog_timeout_seconds=0.1, timeout_seconds=0.5)

    assert client.entity_ids == [1]
    assert client.history_ids == [1]
    assert [message.id for message in result.messages_by_chat_id[1]] == [10]


def test_dialog_timeout_is_cancelled_and_uses_selected_chat_fallback(tmp_path):
    client = PageClient(dialog_delay=1)
    client.histories_started.set()
    result = make_service(tmp_path, client).load_page(1, 2, dialog_timeout_seconds=0.01, timeout_seconds=0.5)

    assert client.dialog_cancelled is True
    assert [(chat.id, chat.title) for chat in result.chats] == [(1, "Chat 1"), (2, "Chat 2")]


def test_dialog_operational_failure_uses_selected_chat_fallback(tmp_path):
    client = PageClient(dialog_failure=True)
    client.histories_started.set()

    result = make_service(tmp_path, client).load_page(1, 2, dialog_timeout_seconds=0.1, timeout_seconds=0.5)

    assert [(chat.id, chat.title) for chat in result.chats] == [(1, "Chat 1"), (2, "Chat 2")]
    assert [message.id for message in result.messages_by_chat_id[1]] == [10]
    assert [message.id for message in result.messages_by_chat_id[2]] == [20]


def test_expected_selected_history_error_is_pane_local(tmp_path):
    client = PageClient(failing_chat_id=2)
    client.histories_started.set()
    result = make_service(tmp_path, client).load_page(1, 2, dialog_timeout_seconds=0.1, timeout_seconds=0.5)

    assert [message.id for message in result.messages_by_chat_id[1]] == [10]
    assert result.messages_by_chat_id[2] == []
    assert isinstance(result.errors_by_chat_id[2], TelegramUnavailableError)


def test_selected_history_timeout_is_pane_local(tmp_path):
    client = PageClient(timeout_chat_id=1)
    service = make_service(tmp_path, client)

    async def latest_peer_message(_client, entity):
        return [FakeMessage(entity.id * 100)]

    service._fetch_latest_peer_message = latest_peer_message
    result = service.load_page(1, 2, dialog_timeout_seconds=0.1, timeout_seconds=0.5)

    assert [message.id for message in result.messages_by_chat_id[1]] == [100]
    assert [message.id for message in result.messages_by_chat_id[2]] == [20]
    assert 1 not in result.errors_by_chat_id


def test_dialog_timeout_and_unresolved_selected_chats_is_global_failure(tmp_path):
    client = PageClient(dialog_delay=1, entity_failure=True)

    with pytest.raises(TelegramUnavailableError):
        make_service(tmp_path, client).load_page(1, 2, dialog_timeout_seconds=0.01, timeout_seconds=0.5)


def test_later_refresh_reuses_last_successful_selected_chats(tmp_path):
    client = PageClient()
    client.histories_started.set()
    service = make_service(tmp_path, client)
    initial = service.load_page(1, 2, dialog_timeout_seconds=0.1, timeout_seconds=0.5)

    client.entity_failure = True
    client.dialog_failure = True
    refreshed = service.load_page(1, 2, dialog_timeout_seconds=0.1, timeout_seconds=0.5)

    assert [message.id for message in initial.messages_by_chat_id[1]] == [10]
    assert [message.id for message in refreshed.messages_by_chat_id[1]] == [10]
    assert [message.id for message in refreshed.messages_by_chat_id[2]] == [20]
    assert refreshed.errors_by_chat_id == {}
    assert refreshed.stale_chat_ids == {1, 2}


def test_peer_dialog_fallback_returns_and_initializes_only_latest_message(tmp_path):
    class RawMessage:
        def __init__(self, message_id):
            self.id = message_id
            self.finished = False

        def _finish_init(self, client, entities, entity):
            self.finished = (client, entities, entity)

    latest = RawMessage(7)
    older = RawMessage(6)

    class PeerDialogClient:
        async def get_input_entity(self, entity):
            return entity

        async def __call__(self, request):
            return SimpleNamespace(
                dialogs=[SimpleNamespace(top_message=7)],
                messages=[older, latest],
                users=[],
                chats=[],
            )

    client = PeerDialogClient()
    entity = FakeEntity(1)

    messages = asyncio.run(TelegramService._fetch_latest_peer_message(client, entity))

    assert messages == [latest]
    assert latest.finished == (client, {}, entity)
    assert older.finished is False


def test_bot_history_uses_search_and_returns_multiple_messages(tmp_path):
    service = make_service(tmp_path, PageClient())
    entity = SimpleNamespace(id=1, bot=True)
    latest = FakeMessage(10)
    older = FakeMessage(9)

    class SearchClient:
        def __init__(self):
            self.calls = []

        async def get_messages(self, selected_entity, *, limit, search):
            self.calls.append((selected_entity, limit, search))
            return [latest, older]

    client = SearchClient()

    messages = asyncio.run(service._fetch_messages(client, entity))

    assert messages == [latest, older]
    assert client.calls == [(entity, service.message_limit, "")]


def test_bot_history_reconnects_and_uses_latest_fallback_after_search_timeout(tmp_path):
    service = make_service(tmp_path, PageClient())
    entity = SimpleNamespace(id=1, bot=True)
    latest = FakeMessage(10)
    class ReconnectingClient:
        def __init__(self):
            self.disconnect_count = 0
            self.connect_count = 0

        async def disconnect(self):
            self.disconnect_count += 1

        async def connect(self):
            self.connect_count += 1

        async def get_messages(self, selected_entity, *, limit, search):
            raise TimeoutError("temporary timeout")

    client = ReconnectingClient()

    async def latest_peer_message(_client, selected_entity):
        assert selected_entity is entity
        return [latest]

    service._fetch_latest_peer_message = latest_peer_message

    messages = asyncio.run(service._fetch_bot_messages(client, entity))

    assert messages == [latest]
    assert client.disconnect_count == 1
    assert client.connect_count == 1


def test_bot_history_skips_search_during_cooldown(tmp_path):
    service = make_service(tmp_path, PageClient())
    service._bot_search_retry_at = float("inf")
    entity = SimpleNamespace(id=1, bot=True)
    latest = FakeMessage(10)

    class CooldownClient:
        async def get_messages(self, *_args, **_kwargs):
            raise AssertionError("search must be skipped during cooldown")

    async def latest_peer_message(_client, selected_entity):
        assert selected_entity is entity
        return [latest]

    service._fetch_latest_peer_message = latest_peer_message

    messages = asyncio.run(service._fetch_bot_messages(CooldownClient(), entity))

    assert messages == [latest]


def test_single_message_bot_fallback_does_not_replace_cached_history(tmp_path):
    class BotPageClient(PageClient):
        async def get_entity(self, chat_id):
            entity = await super().get_entity(chat_id)
            entity.bot = True
            return entity

    client = BotPageClient()
    service = make_service(tmp_path, client)
    service.message_limit = 2
    fetch_count = 0

    async def fetch_bot_messages(_client, _entity):
        nonlocal fetch_count
        fetch_count += 1
        if fetch_count == 1:
            return [FakeMessage(20), FakeMessage(10)]
        return [FakeMessage(30)]

    service._fetch_bot_messages = fetch_bot_messages

    initial = service.load_page(1, 1, dialog_timeout_seconds=0.1, timeout_seconds=0.5)
    refreshed = service.load_page(1, 1, dialog_timeout_seconds=0.1, timeout_seconds=0.5)

    assert [message.id for message in initial.messages_by_chat_id[1]] == [20, 10]
    assert [message.id for message in refreshed.messages_by_chat_id[1]] == [30, 20]


def test_selected_history_programming_error_propagates(tmp_path):
    client = PageClient(failing_chat_id=2, programming_error=True)
    client.histories_started.set()

    with pytest.raises(RuntimeError, match="programming defect"):
        make_service(tmp_path, client).load_page(1, 2, dialog_timeout_seconds=0.1, timeout_seconds=0.5)
