import asyncio
from dataclasses import dataclass
from pathlib import Path
from datetime import timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from telethon import TelegramClient


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


class TelegramConfigurationError(RuntimeError):
    pass


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
    ):
        self.api_id = int(api_id) if api_id else 0
        self.api_hash = api_hash
        self.session_dir = Path(session_dir)
        self.session_name = session_name
        self.message_limit = message_limit
        self.message_timezone = message_timezone or "Europe/Samara"
        self.media_cache_dir = Path(media_cache_dir) if media_cache_dir else self.session_dir / "media"
        self.media_cache_limit_bytes = int(media_cache_limit_bytes)

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
        )

    @property
    def session_path(self):
        return self.session_dir / self.session_name

    def _validate(self):
        if not self.api_id or not self.api_hash:
            raise TelegramConfigurationError("TELEGRAM_API_ID and TELEGRAM_API_HASH must be configured")

    def list_chats(self):
        self._validate()
        return asyncio.run(self._list_chats())

    def list_incoming_messages(self, chat_id):
        return self.list_messages(chat_id)

    def list_messages(self, chat_id):
        self._validate()
        self.validate_timezone()
        return asyncio.run(self._list_messages(chat_id))

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
        return TelegramClient(str(self.session_path), self.api_id, self.api_hash)

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

    async def _list_messages(self, chat_id):
        client = await self._client()
        async with client:
            if not await client.is_user_authorized():
                raise TelegramConfigurationError("Telegram session is not authorized. Run scripts/init_telegram_session.py first.")
            entity = await client.get_entity(int(chat_id))
            messages = []
            async for message in client.iter_messages(entity, limit=self.message_limit):
                messages.append(await self._build_message_summary(client, entity.id, message))
            return messages
