import asyncio
from dataclasses import dataclass
from datetime import timezone
from pathlib import Path
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


class TelegramConfigurationError(RuntimeError):
    pass


class TelegramService:
    def __init__(self, api_id, api_hash, session_dir, session_name, message_limit=50, message_timezone="Europe/Samara"):
        self.api_id = int(api_id) if api_id else 0
        self.api_hash = api_hash
        self.session_dir = Path(session_dir)
        self.session_name = session_name
        self.message_limit = message_limit
        self.message_timezone = message_timezone or "Europe/Samara"

    @classmethod
    def from_config(cls, config):
        return cls(
            api_id=config.get("TELEGRAM_API_ID"),
            api_hash=config.get("TELEGRAM_API_HASH"),
            session_dir=config.get("TELEGRAM_SESSION_DIR"),
            session_name=config.get("TELEGRAM_SESSION_NAME"),
            message_limit=config.get("MESSAGE_LIMIT", 50),
            message_timezone=config.get("MESSAGE_TIMEZONE", "Europe/Samara"),
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
                sender = "Unknown"
                message_sender = getattr(message, "sender", None)
                if message_sender:
                    sender = getattr(message_sender, "first_name", None) or getattr(message_sender, "title", None) or "Unknown"
                text = getattr(message, "message", None) or "[media/service message]"
                message_date = getattr(message, "date", None)
                date = self._format_message_date(message_date)
                incoming = self._is_incoming_message(message)
                messages.append(MessageSummary(id=message.id, text=text, sender=sender, date=date, incoming=incoming))
            return messages
