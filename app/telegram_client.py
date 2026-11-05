import asyncio
import atexit
import itertools
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from datetime import timezone
from pathlib import Path
from sqlite3 import OperationalError
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from markupsafe import Markup
from telethon import TelegramClient
from telethon import functions, types, utils
from telethon.errors import RPCError
from telethon.tl.types import Channel

from .telegram_html import render_telegram_html


CHANNEL_HISTORY_OVERSCAN_MULTIPLIER = 2
CHANNEL_HISTORY_MAX_CANDIDATE_IDS = 100
PAGE_CLEANUP_GRACE_SECONDS = 0.1
USER_HISTORY_PRIMARY_TIMEOUT_SECONDS = 3
BOT_SEARCH_TIMEOUT_SECONDS = 1.5
BOT_LATEST_TIMEOUT_SECONDS = 1.5
BOT_SEARCH_COOLDOWN_SECONDS = 60


@dataclass
class ChatSummary:
    id: int
    title: str


@dataclass
class MessageSummary:
    id: int
    text: str
    sender: str
    date: str
    incoming: bool
    has_media: bool = False
    media_kind: str = "none"
    media_url: str | None = None
    media_label: str | None = None
    media_filename: str | None = None
    safe_html: Markup | None = None


@dataclass
class SelectedChatLoad:
    summary: ChatSummary | None
    messages: list
    error: Exception | None = None
    preserve_cached_messages: bool = False


@dataclass
class PageLoadResult:
    chats: list
    messages_by_chat_id: dict
    errors_by_chat_id: dict
    stale_chat_ids: set = field(default_factory=set)


class TelegramConfigurationError(RuntimeError):
    pass


class TelegramUnavailableError(RuntimeError):
    pass


class TelegramTimeoutError(TelegramUnavailableError):
    pass


class PersistentTelegramClient(TelegramClient):
    def __init__(self, *args, temporary_session_dir, **kwargs):
        self._temporary_session_dir = Path(temporary_session_dir)
        super().__init__(*args, **kwargs)

    async def __aenter__(self):
        if not self.is_connected():
            await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        return None


class TelegramService:
    def __init__(
        self,
        api_id,
        api_hash,
        session_dir,
        session_name,
        message_limit=50,
        message_timezone="Europe/Samara",
        media_cache_dir=None,
        media_cache_limit_bytes=1024 * 1024 * 1024,
        page_timeout_seconds=10,
    ):
        self.api_id = int(api_id) if api_id else 0
        self.api_hash = api_hash
        self.session_dir = Path(session_dir)
        self.session_name = session_name
        self.message_limit = message_limit
        self.message_timezone = message_timezone or "Europe/Samara"
        self.media_cache_dir = Path(media_cache_dir) if media_cache_dir else self.session_dir / "media"
        self.media_cache_limit_bytes = int(media_cache_limit_bytes)
        self.page_timeout_seconds = float(page_timeout_seconds)
        self._selected_load_cache = {}
        self._event_loop = None
        self._persistent_client = None
        self._bot_search_retry_at = 0.0
        if not 0 < self.page_timeout_seconds <= 20:
            raise TelegramConfigurationError("TELEGRAM_PAGE_TIMEOUT_SECONDS must be in the range (0, 20]")

    @classmethod
    def from_config(cls, config):
        return cls(
            api_id=config.get("TELEGRAM_API_ID"),
            api_hash=config.get("TELEGRAM_API_HASH"),
            session_dir=config.get("TELEGRAM_SESSION_DIR"),
            session_name=config.get("TELEGRAM_SESSION_NAME"),
            message_limit=config.get("MESSAGE_LIMIT", 50),
            message_timezone=config.get("MESSAGE_TIMEZONE", "Europe/Samara"),
            media_cache_dir=config.get("MEDIA_CACHE_DIR"),
            media_cache_limit_bytes=config.get("MEDIA_CACHE_LIMIT_BYTES", 1024 * 1024 * 1024),
            page_timeout_seconds=config.get("TELEGRAM_PAGE_TIMEOUT_SECONDS", 10),
        )

    @property
    def session_path(self):
        return self.session_dir / self.session_name

    @property
    def session_file_path(self):
        return Path(f"{self.session_path}.session")

    def _create_runtime_session(self):
        if not self.session_file_path.is_file():
            raise TelegramConfigurationError(
                "Telegram session is not authorized. Run scripts/init_telegram_session.py first."
            )
        temporary_session_dir = Path(tempfile.mkdtemp(prefix="telegram-inbox-session-"))
        temporary_session_path = temporary_session_dir / self.session_name
        shutil.copy2(self.session_file_path, Path(f"{temporary_session_path}.session"))
        atexit.register(shutil.rmtree, temporary_session_dir, ignore_errors=True)
        return temporary_session_path, temporary_session_dir

    def _run_coroutine(self, coroutine, timeout):
        if self._event_loop is None or self._event_loop.is_closed():
            self._event_loop = asyncio.new_event_loop()
        return self._event_loop.run_until_complete(asyncio.wait_for(coroutine, timeout=timeout))

    def _validate(self):
        if not self.api_id or not self.api_hash:
            raise TelegramConfigurationError("TELEGRAM_API_ID and TELEGRAM_API_HASH must be configured")

    def _run_operation(self, operation_factory, timeout_seconds=None):
        timeout = self.page_timeout_seconds if timeout_seconds is None else float(timeout_seconds)
        if timeout <= 0:
            raise TelegramTimeoutError("Telegram is temporarily unavailable")
        try:
            operation = operation_factory()
            return self._run_coroutine(operation, timeout=min(timeout, self.page_timeout_seconds))
        except TimeoutError as exc:
            raise TelegramTimeoutError("Telegram is temporarily unavailable") from exc
        except (ConnectionError, OperationalError, RPCError) as exc:
            raise TelegramUnavailableError("Telegram is temporarily unavailable") from exc

    def list_chats(self, timeout_seconds=None):
        self._validate()
        return self._run_operation(self._list_chats, timeout_seconds)

    def check_readiness(self, timeout_seconds=None):
        self._validate()
        return self._run_operation(self._check_readiness, timeout_seconds)

    def resolve_chat_summaries(self, chat_ids, timeout_seconds=None):
        self._validate()
        unique_chat_ids = list(dict.fromkeys(int(chat_id) for chat_id in chat_ids if chat_id is not None))
        if not unique_chat_ids:
            return []
        return self._run_operation(lambda: self._resolve_chat_summaries(unique_chat_ids), timeout_seconds)

    def list_incoming_messages(self, chat_id):
        return self.list_messages(chat_id)

    def list_messages(self, chat_id, timeout_seconds=None):
        self._validate()
        self.validate_timezone()
        return self._run_operation(lambda: self._list_messages(chat_id), timeout_seconds)

    def load_page(self, left_chat_id, right_chat_id, dialog_timeout_seconds, timeout_seconds=None):
        self._validate()
        self.validate_timezone()
        timeout = self.page_timeout_seconds if timeout_seconds is None else float(timeout_seconds)
        if timeout <= 0:
            raise TelegramTimeoutError("Telegram is temporarily unavailable")
        selected_chat_ids = list(
            dict.fromkeys(int(chat_id) for chat_id in (left_chat_id, right_chat_id) if chat_id is not None)
        )
        try:
            operation = self._load_page(selected_chat_ids, float(dialog_timeout_seconds), timeout)
            page_timeout = min(timeout, self.page_timeout_seconds)
            return self._run_coroutine(operation, timeout=page_timeout + PAGE_CLEANUP_GRACE_SECONDS)
        except TimeoutError as exc:
            raise TelegramTimeoutError("Telegram is temporarily unavailable") from exc
        except (ConnectionError, OperationalError, RPCError) as exc:
            raise TelegramUnavailableError("Telegram is temporarily unavailable") from exc

    def validate_timezone(self):
        try:
            ZoneInfo(self.message_timezone)
        except ZoneInfoNotFoundError as exc:
            raise TelegramConfigurationError(f"MESSAGE_TIMEZONE is invalid: {self.message_timezone}") from exc

    def ensure_media_cache_dir(self):
        self.media_cache_dir.mkdir(parents=True, exist_ok=True)

    def _detect_photo_extension(self, message):
        message_file = getattr(message, "file", None)
        extension = getattr(message_file, "ext", None)
        if extension:
            return extension

        mime_type = getattr(message_file, "mime_type", None)
        if mime_type == "image/png":
            return ".png"
        if mime_type == "image/webp":
            return ".webp"
        return ".jpg"

    def _photo_cache_filename(self, chat_id, message):
        return f"chat-{int(chat_id)}-message-{int(message.id)}{self._detect_photo_extension(message)}"

    def _cache_size_bytes(self):
        if not self.media_cache_dir.exists():
            return 0
        return sum(path.stat().st_size for path in self.media_cache_dir.iterdir() if path.is_file())

    def _enforce_media_cache_limit(self):
        if self.media_cache_limit_bytes <= 0 or not self.media_cache_dir.exists():
            return

        files = [path for path in self.media_cache_dir.iterdir() if path.is_file()]
        total_size = sum(path.stat().st_size for path in files)
        if total_size <= self.media_cache_limit_bytes:
            return

        for path in sorted(files, key=lambda item: item.stat().st_mtime):
            try:
                file_size = path.stat().st_size
                path.unlink()
            except FileNotFoundError:
                continue
            total_size -= file_size
            if total_size <= self.media_cache_limit_bytes:
                break

    @staticmethod
    def _has_photo(message):
        return getattr(message, "photo", None) is not None

    @staticmethod
    def _has_generic_media(message):
        return getattr(message, "media", None) is not None or getattr(message, "action", None) is not None

    @staticmethod
    def _generic_media_label(_message):
        return "Медиа"

    async def _cache_photo(self, client, chat_id, message):
        self.ensure_media_cache_dir()
        filename = self._photo_cache_filename(chat_id, message)
        target_path = self.media_cache_dir / filename
        if target_path.exists():
            target_path.touch()
            return filename

        downloaded_path = await client.download_media(message, str(target_path))
        if not downloaded_path:
            return None

        actual_path = Path(downloaded_path)
        if actual_path != target_path and actual_path.exists():
            actual_path.replace(target_path)
        if not target_path.exists():
            return None

        self._enforce_media_cache_limit()
        return filename

    async def _build_message_summary(self, client, chat_id, message):
        sender = "Unknown"
        message_sender = getattr(message, "sender", None)
        if message_sender:
            sender = getattr(message_sender, "first_name", None) or getattr(message_sender, "title", None) or "Unknown"

        text = getattr(message, "message", None) or ""
        message_date = getattr(message, "date", None)
        date = self._format_message_date(message_date)
        incoming = self._is_incoming_message(message)

        summary = MessageSummary(
            id=message.id,
            text=text,
            sender=sender,
            date=date,
            incoming=incoming,
            safe_html=render_telegram_html(text, getattr(message, "entities", None)),
        )

        if self._has_photo(message):
            filename = await self._cache_photo(client, chat_id, message)
            if filename:
                summary.has_media = True
                summary.media_kind = "photo"
                summary.media_label = "Фото"
                summary.media_filename = filename
                return summary

        if self._has_generic_media(message) or not text:
            summary.has_media = True
            summary.media_kind = "generic"
            summary.media_label = self._generic_media_label(message)

        return summary

    async def _client(self):
        self.session_dir.mkdir(parents=True, exist_ok=True)
        if self._persistent_client is None:
            temporary_session_path, temporary_session_dir = self._create_runtime_session()
            self._persistent_client = PersistentTelegramClient(
                str(temporary_session_path),
                self.api_id,
                self.api_hash,
                temporary_session_dir=temporary_session_dir,
            )
        return self._persistent_client

    async def _list_chats(self):
        client = await self._client()
        async with client:
            if not await client.is_user_authorized():
                raise TelegramConfigurationError("Telegram session is not authorized. Run scripts/init_telegram_session.py first.")
            dialogs = await client.get_dialogs()
            chats = []
            for dialog in dialogs:
                title = dialog.name or "Untitled chat"
                chats.append(ChatSummary(id=dialog.id, title=title))
            return chats

    async def _fetch_selected_chat(self, client, chat_id):
        summary = None
        try:
            entity = self._cached_input_entity(client, chat_id)
            if entity is None:
                entity = await client.get_entity(chat_id)
                title = self._entity_title(entity)
            else:
                title = self._cached_entity_title(client, chat_id)
            summary = ChatSummary(id=chat_id, title=title)
            fetched_messages = await self._fetch_messages(client, entity)
            return entity, SelectedChatLoad(
                summary=summary,
                messages=list(fetched_messages),
                preserve_cached_messages=isinstance(entity, types.InputPeerUser) or getattr(entity, "bot", False),
            )
        except (TelegramUnavailableError, TelegramConfigurationError) as exc:
            return None, SelectedChatLoad(summary=summary, messages=[], error=exc)
        except TimeoutError:
            error = TelegramTimeoutError("Telegram is temporarily unavailable")
            return None, SelectedChatLoad(summary=summary, messages=[], error=error)
        except (ConnectionError, OperationalError, RPCError):
            error = TelegramUnavailableError("Telegram is temporarily unavailable")
            return None, SelectedChatLoad(summary=summary, messages=[], error=error)

    async def _summarize_selected_chat(self, client, chat_id, load):
        if load.error is not None:
            return load
        try:
            messages = []
            for message in load.messages:
                messages.append(await self._build_message_summary(client, chat_id, message))
            return SelectedChatLoad(
                summary=load.summary,
                messages=messages,
                preserve_cached_messages=load.preserve_cached_messages,
            )
        except (TelegramUnavailableError, TelegramConfigurationError) as exc:
            return SelectedChatLoad(summary=load.summary, messages=[], error=exc)
        except TimeoutError:
            error = TelegramTimeoutError("Telegram is temporarily unavailable")
            return SelectedChatLoad(summary=load.summary, messages=[], error=error)
        except (ConnectionError, OperationalError, RPCError):
            error = TelegramUnavailableError("Telegram is temporarily unavailable")
            return SelectedChatLoad(summary=load.summary, messages=[], error=error)

    @staticmethod
    async def _cancel_tasks(tasks):
        tasks = list(tasks)
        pending_tasks = [task for task in tasks if not task.done()]
        for task in pending_tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    @staticmethod
    def _has_local_auth_key(client):
        return getattr(getattr(client, "session", None), "auth_key", None) is not None

    async def _load_page(self, selected_chat_ids, dialog_timeout_seconds, timeout_seconds):
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_seconds
        client = await self._client()
        all_tasks = set()
        async with client:
            if not self._has_local_auth_key(client):
                raise TelegramConfigurationError(
                    "Telegram session is not authorized. Run scripts/init_telegram_session.py first."
                )

            dialogs = None
            try:
                reserved_dialog_budget = min(dialog_timeout_seconds, timeout_seconds)
                selected_deadline = deadline - reserved_dialog_budget
                selected_loads = {}
                for chat_id in selected_chat_ids:
                    remaining = max(selected_deadline - loop.time(), 0)
                    if remaining == 0:
                        selected_loads[chat_id] = SelectedChatLoad(
                            summary=None,
                            messages=[],
                            error=TelegramTimeoutError("Telegram is temporarily unavailable"),
                        )
                        continue
                    try:
                        _entity, selected_loads[chat_id] = await asyncio.wait_for(
                            self._fetch_selected_chat(client, chat_id),
                            timeout=remaining,
                        )
                    except TimeoutError:
                        selected_loads[chat_id] = SelectedChatLoad(
                            summary=None,
                            messages=[],
                            error=TelegramTimeoutError("Telegram is temporarily unavailable"),
                        )
                for chat_id, load in selected_loads.items():
                    remaining = max(selected_deadline - loop.time(), 0)
                    if load.error is not None:
                        continue
                    if remaining == 0:
                        selected_loads[chat_id] = SelectedChatLoad(
                            summary=load.summary,
                            messages=[],
                            error=TelegramTimeoutError("Telegram is temporarily unavailable"),
                        )
                        continue
                    try:
                        selected_loads[chat_id] = await asyncio.wait_for(
                            self._summarize_selected_chat(client, chat_id, load),
                            timeout=remaining,
                        )
                    except TimeoutError:
                        selected_loads[chat_id] = SelectedChatLoad(
                            summary=load.summary,
                            messages=[],
                            error=TelegramTimeoutError("Telegram is temporarily unavailable"),
                        )
                stale_chat_ids = set()
                for chat_id, load in selected_loads.items():
                    cached_load = self._selected_load_cache.get(chat_id)
                    if load.error is None and load.summary is not None:
                        if load.preserve_cached_messages and cached_load is not None:
                            messages_by_id = {message.id: message for message in cached_load.messages}
                            messages_by_id.update({message.id: message for message in load.messages})
                            load = SelectedChatLoad(
                                summary=load.summary,
                                messages=sorted(messages_by_id.values(), key=lambda message: message.id, reverse=True)[
                                    : self.message_limit
                                ],
                                preserve_cached_messages=True,
                            )
                            selected_loads[chat_id] = load
                        self._selected_load_cache[chat_id] = load
                    elif cached_load is not None:
                        selected_loads[chat_id] = cached_load
                        stale_chat_ids.add(chat_id)

                dialog_task = asyncio.create_task(client.get_dialogs())
                all_tasks.add(dialog_task)
                dialog_budget = min(dialog_timeout_seconds, max(deadline - loop.time(), 0))
                try:
                    dialogs = await asyncio.wait_for(asyncio.shield(dialog_task), timeout=dialog_budget)
                except TimeoutError:
                    await self._cancel_tasks([dialog_task])
                except (ConnectionError, OperationalError, RPCError):
                    await self._cancel_tasks([dialog_task])
                if dialogs is None and not selected_chat_ids:
                    raise TelegramTimeoutError("Telegram is temporarily unavailable")

                if dialogs is None:
                    chats = [
                        selected_loads[chat_id].summary
                        for chat_id in selected_chat_ids
                        if selected_loads[chat_id].summary is not None
                    ]
                    if not chats:
                        raise TelegramUnavailableError("Telegram is temporarily unavailable")
                else:
                    chats = [ChatSummary(id=dialog.id, title=dialog.name or "Untitled chat") for dialog in dialogs]

                return PageLoadResult(
                    chats=chats,
                    messages_by_chat_id={chat_id: load.messages for chat_id, load in selected_loads.items()},
                    errors_by_chat_id={
                        chat_id: load.error for chat_id, load in selected_loads.items() if load.error is not None
                    },
                    stale_chat_ids=stale_chat_ids,
                )
            finally:
                await self._cancel_tasks(all_tasks)

    async def _check_readiness(self):
        client = await self._client()
        async with client:
            if not await client.is_user_authorized():
                raise TelegramConfigurationError(
                    "Telegram session is not authorized. Run scripts/init_telegram_session.py first."
                )

    @staticmethod
    def _entity_title(entity):
        title = getattr(entity, "title", None)
        if title:
            return title
        name_parts = [getattr(entity, "first_name", None), getattr(entity, "last_name", None)]
        display_name = " ".join(part for part in name_parts if part)
        return display_name or getattr(entity, "username", None) or "Untitled chat"

    @staticmethod
    def _cached_input_entity(client, chat_id):
        session = getattr(client, "session", None)
        get_input_entity = getattr(session, "get_input_entity", None)
        if not callable(get_input_entity):
            return None
        try:
            return get_input_entity(int(chat_id))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _cached_entity_title(client, chat_id):
        execute = getattr(getattr(client, "session", None), "_execute", None)
        if callable(execute):
            row = execute("select name, username from entities where id = ?", int(chat_id))
            if row:
                name, username = row
                return name or (f"@{username}" if username else None) or str(chat_id)
        return str(chat_id)

    async def _resolve_chat_summaries(self, chat_ids):
        client = await self._client()
        async with client:
            if not await client.is_user_authorized():
                raise TelegramConfigurationError(
                    "Telegram session is not authorized. Run scripts/init_telegram_session.py first."
                )
            chats = []
            for chat_id in chat_ids:
                entity = await client.get_entity(chat_id)
                chats.append(ChatSummary(id=chat_id, title=self._entity_title(entity)))
            return chats

    @staticmethod
    def _is_incoming_message(message):
        if hasattr(message, "incoming"):
            return bool(message.incoming)
        if hasattr(message, "out"):
            return not bool(message.out)
        return True

    def _format_message_date(self, message_date):
        if not message_date:
            return ""
        if message_date.tzinfo is None:
            message_date = message_date.replace(tzinfo=timezone.utc)
        local_date = message_date.astimezone(ZoneInfo(self.message_timezone))
        return local_date.strftime("%Y-%m-%d %H:%M:%S")

    async def _fetch_channel_messages(self, client, entity):
        if self.message_limit <= 0:
            return []

        latest_messages = await client.get_messages(entity, limit=1)
        if not latest_messages:
            return []

        latest_message = latest_messages[0]
        candidate_window_size = min(
            self.message_limit * CHANNEL_HISTORY_OVERSCAN_MULTIPLIER,
            CHANNEL_HISTORY_MAX_CANDIDATE_IDS,
        )
        oldest_candidate_id = max(latest_message.id - candidate_window_size, 0)
        candidate_ids = list(range(latest_message.id - 1, oldest_candidate_id, -1))
        candidate_messages = await client.get_messages(entity, ids=candidate_ids) if candidate_ids else []
        messages = [latest_message, *(message for message in candidate_messages if message is not None)]
        messages.sort(key=lambda message: message.id, reverse=True)
        return messages[: self.message_limit]

    async def _fetch_messages(self, client, entity):
        if isinstance(entity, (Channel, types.InputPeerChannel)):
            return await self._fetch_channel_messages(client, entity)
        if isinstance(entity, types.InputPeerUser) or getattr(entity, "bot", False):
            return await self._fetch_bot_messages(client, entity)
        try:
            return await asyncio.wait_for(
                self._collect_iter_messages(client, entity),
                timeout=min(USER_HISTORY_PRIMARY_TIMEOUT_SECONDS, self.page_timeout_seconds),
            )
        except TimeoutError:
            return await self._fetch_latest_peer_message(client, entity)

    async def _collect_iter_messages(self, client, entity):
        return [message async for message in client.iter_messages(entity, limit=self.message_limit)]

    async def _fetch_bot_messages(self, client, entity):
        if time.monotonic() >= self._bot_search_retry_at:
            try:
                messages = await asyncio.wait_for(
                    client.get_messages(entity, limit=self.message_limit, search=""),
                    timeout=min(BOT_SEARCH_TIMEOUT_SECONDS, self.page_timeout_seconds),
                )
                if messages:
                    return list(messages)
            except (TimeoutError, ConnectionError, OperationalError, RPCError):
                self._bot_search_retry_at = time.monotonic() + BOT_SEARCH_COOLDOWN_SECONDS
                await client.disconnect()
                await client.connect()

        return await asyncio.wait_for(
            self._fetch_latest_peer_message(client, entity),
            timeout=min(BOT_LATEST_TIMEOUT_SECONDS, self.page_timeout_seconds),
        )

    @staticmethod
    async def _fetch_latest_peer_message(client, entity):
        input_peer = await client.get_input_entity(entity)
        result = await client(
            functions.messages.GetPeerDialogsRequest(peers=[types.InputDialogPeer(input_peer)])
        )
        if not result.dialogs:
            return []

        top_message_id = result.dialogs[0].top_message
        messages = [message for message in result.messages if message.id == top_message_id]
        entities = {
            utils.get_peer_id(item): item
            for item in itertools.chain(result.users, result.chats)
        }
        for message in messages:
            message._finish_init(client, entities, entity)
        return messages

    async def _list_messages(self, chat_id):
        client = await self._client()
        async with client:
            if not await client.is_user_authorized():
                raise TelegramConfigurationError("Telegram session is not authorized. Run scripts/init_telegram_session.py first.")
            entity = await client.get_entity(int(chat_id))
            messages = []
            for message in await self._fetch_messages(client, entity):
                messages.append(await self._build_message_summary(client, entity.id, message))
            return messages
