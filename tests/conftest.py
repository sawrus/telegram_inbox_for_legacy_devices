import pytest

from app import create_app
from app.telegram_client import ChatSummary, MessageSummary


class FakeTelegramService:
    def __init__(self):
        self.message_timezone = "Europe/Samara"

    def validate_timezone(self):
        return None

    def list_chats(self):
        return [
            ChatSummary(id=1, title="Жена"),
            ChatSummary(id=2, title="Семья"),
            ChatSummary(id=3, title="Работа"),
        ]

    def list_incoming_messages(self, chat_id):
        return self.list_messages(chat_id)

    def list_messages(self, chat_id):
        messages = {
            1: [
                MessageSummary(id=10, text="Привет", sender="Мария", date="2026-06-24 10:00:00", incoming=True),
                MessageSummary(id=11, text="Я скоро", sender="Me", date="2026-06-24 10:01:00", incoming=False),
            ],
            2: [
                MessageSummary(
                    id=20,
                    text="Семейный чат",
                    sender="Олег",
                    date="2026-06-24 11:00:00",
                    incoming=True,
                    has_media=True,
                    media_kind="photo",
                    media_filename="chat-2-message-20.jpg",
                ),
            ],
            3: [
                MessageSummary(
                    id=30,
                    text="Созвон",
                    sender="Анна",
                    date="2026-06-24 12:00:00",
                    incoming=True,
                    has_media=True,
                    media_kind="generic",
                    media_label="Медиа",
                ),
            ],
        }
        return messages.get(int(chat_id), [])


class TestConfig:
    TESTING = True
    SECRET_KEY = "test"
    REFRESH_SECONDS = 7
    MESSAGE_LIMIT = 50
    MESSAGE_TIMEZONE = "Europe/Samara"
    LEFT_CHAT_ID = "1"
    RIGHT_CHAT_ID = "2"
    TELEGRAM_API_ID = "1"
    TELEGRAM_API_HASH = "hash"
    TELEGRAM_SESSION_NAME = "test"
    TELEGRAM_SESSION_DIR = "/tmp"
    MEDIA_CACHE_DIR = "/tmp/telegram-inbox-media-tests"
    MEDIA_CACHE_LIMIT_BYTES = 1024 * 1024 * 1024


@pytest.fixture
def client():
    app = create_app(TestConfig, telegram_service=FakeTelegramService())
    return app.test_client()
