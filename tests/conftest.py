import pytest

from app import create_app
from app.telegram_client import ChatSummary, MessageSummary


class FakeTelegramService:
    def list_chats(self):
        return [ChatSummary(id=1, title="Жена"), ChatSummary(id=2, title="Семья")]

    def list_incoming_messages(self, chat_id):
        return [MessageSummary(id=10, text="Привет", sender="Мария", date="2026-06-24 10:00:00", incoming=True)]


class TestConfig:
    TESTING = True
    SECRET_KEY = "test"
    REFRESH_SECONDS = 7
    MESSAGE_LIMIT = 50
    TELEGRAM_API_ID = "1"
    TELEGRAM_API_HASH = "hash"
    TELEGRAM_SESSION_NAME = "test"
    TELEGRAM_SESSION_DIR = "/tmp"


@pytest.fixture
def client():
    app = create_app(TestConfig, telegram_service=FakeTelegramService())
    return app.test_client()
