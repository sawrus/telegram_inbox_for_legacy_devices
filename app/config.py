import os
from pathlib import Path


class Config:
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "change-me-local-only")
    TELEGRAM_API_ID = os.getenv("TELEGRAM_API_ID", "")
    TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH", "")
    TELEGRAM_SESSION_NAME = os.getenv("TELEGRAM_SESSION_NAME", "telegram-inbox")
    TELEGRAM_SESSION_DIR = Path(os.getenv("TELEGRAM_SESSION_DIR", "/data"))
    MESSAGE_LIMIT = int(os.getenv("MESSAGE_LIMIT", "50"))
    MESSAGE_TIMEZONE = os.getenv("MESSAGE_TIMEZONE", "Europe/Samara")
    LEFT_CHAT_ID = os.getenv("LEFT_CHAT_ID", "")
    RIGHT_CHAT_ID = os.getenv("RIGHT_CHAT_ID", "")
    REFRESH_SECONDS = int(os.getenv("REFRESH_SECONDS", "30"))
