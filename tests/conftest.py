import pytest

from app import create_app
from app.telegram_client import ChatSummary, MessageSummary, PageLoadResult


class FakeTelegramService:
    def __init__(self):
        self.message_timezone = "Europe/Samara"
        self.timeouts = []
        self.page_calls = []

    def validate_timezone(self):
        return None

    def list_chats(self, timeout_seconds=None):
        self.timeouts.append(timeout_seconds)
        return [
            ChatSummary(id=1, title="Жена"),
            ChatSummary(id=2, title="Семья"),
            ChatSummary(id=3, title="Работа"),
        ]

    def check_readiness(self, timeout_seconds=None):
        self.timeouts.append(timeout_seconds)
        return None

    def list_incoming_messages(self, chat_id):
        return self.list_messages(chat_id)

    def list_messages(self, chat_id, timeout_seconds=None):
        self.timeouts.append(timeout_seconds)
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

    def load_page(self, left_chat_id, right_chat_id, dialog_timeout_seconds, timeout_seconds=None):
        self.page_calls.append((left_chat_id, right_chat_id, dialog_timeout_seconds, timeout_seconds))
        chats = self.list_chats()
        selected_ids = dict.fromkeys(chat_id for chat_id in (left_chat_id, right_chat_id) if chat_id is not None)
        return PageLoadResult(
            chats=chats,
            messages_by_chat_id={chat_id: self.list_messages(chat_id) for chat_id in selected_ids},
            errors_by_chat_id={},
        )


class TestConfig:
    TESTING = True
    INBOX_USERNAME = "test"
    INBOX_PASSWORD = "test-password"
    SECRET_KEY = "test"
    REFRESH_SECONDS = 7
    MESSAGE_LIMIT = 50
    MESSAGE_TIMEZONE = "Europe/Samara"
    LEFT_CHAT_ID = "1"
    RIGHT_CHAT_ID = "2"
    PINNED_CHATS = ()
    TELEGRAM_API_ID = "1"
    TELEGRAM_API_HASH = "hash"
    TELEGRAM_SESSION_NAME = "test"
    TELEGRAM_SESSION_DIR = "/tmp"
    MEDIA_CACHE_DIR = "/tmp/telegram-inbox-media-tests"
    MEDIA_CACHE_LIMIT_BYTES = 1024 * 1024 * 1024
    TELEGRAM_PAGE_TIMEOUT_SECONDS = 10.0
    TELEGRAM_DIALOG_LIST_TIMEOUT_SECONDS = 3.0


@pytest.fixture
def client():
    app = create_app(TestConfig, telegram_service=FakeTelegramService())
    client = app.test_client()
    client.environ_base["HTTP_AUTHORIZATION"] = "Basic dGVzdDp0ZXN0LXBhc3N3b3Jk"
    return client
