import os
from pathlib import Path


def _telegram_page_timeout_seconds():
    raw_value = os.getenv("TELEGRAM_PAGE_TIMEOUT_SECONDS", "10")
    try:
        timeout_seconds = float(raw_value)
    except ValueError as exc:
        raise RuntimeError("TELEGRAM_PAGE_TIMEOUT_SECONDS must be a number in the range (0, 20]") from exc
    if not 0 < timeout_seconds <= 20:
        raise RuntimeError("TELEGRAM_PAGE_TIMEOUT_SECONDS must be in the range (0, 20]")
    return timeout_seconds


def _telegram_dialog_list_timeout_seconds():
    raw_value = os.getenv("TELEGRAM_DIALOG_LIST_TIMEOUT_SECONDS", "3")
    try:
        timeout_seconds = float(raw_value)
    except ValueError as exc:
        raise RuntimeError("TELEGRAM_DIALOG_LIST_TIMEOUT_SECONDS must be a number in the range (0, 5]") from exc
    if not 0 < timeout_seconds <= 5:
        raise RuntimeError("TELEGRAM_DIALOG_LIST_TIMEOUT_SECONDS must be in the range (0, 5]")
    return timeout_seconds


def _pinned_chats():
    raw_value = os.getenv("PINNED_CHATS", "").strip()
    if not raw_value:
        return ()

    chats = {}
    for item in raw_value.split(";"):
        chat_id_value, separator, title = item.strip().partition(":")
        if not separator or not title.strip():
            raise RuntimeError("PINNED_CHATS must use the format chat_id:title;chat_id:title")
        try:
            chat_id = int(chat_id_value)
        except ValueError as exc:
            raise RuntimeError("PINNED_CHATS chat ids must be integers") from exc
        chats[chat_id] = title.strip()
    return tuple(chats.items())


class Config:
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "change-me-local-only")
    TELEGRAM_API_ID = os.getenv("TELEGRAM_API_ID", "")
    TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH", "")
    TELEGRAM_SESSION_NAME = os.getenv("TELEGRAM_SESSION_NAME", "telegram-inbox")
    TELEGRAM_SESSION_DIR = Path(os.getenv("TELEGRAM_SESSION_DIR", "/data"))
    MEDIA_CACHE_DIR = Path(os.getenv("MEDIA_CACHE_DIR", str(TELEGRAM_SESSION_DIR / "media")))
    MEDIA_CACHE_LIMIT_BYTES = int(os.getenv("MEDIA_CACHE_LIMIT_BYTES", str(1024 * 1024 * 1024)))
    MESSAGE_LIMIT = int(os.getenv("MESSAGE_LIMIT", "50"))
    MESSAGE_TIMEZONE = os.getenv("MESSAGE_TIMEZONE", "Europe/Samara")
    LEFT_CHAT_ID = os.getenv("LEFT_CHAT_ID", "")
    RIGHT_CHAT_ID = os.getenv("RIGHT_CHAT_ID", "")
    PINNED_CHATS = _pinned_chats()
    REFRESH_SECONDS = int(os.getenv("REFRESH_SECONDS", "30"))
    TELEGRAM_PAGE_TIMEOUT_SECONDS = _telegram_page_timeout_seconds()
    TELEGRAM_DIALOG_LIST_TIMEOUT_SECONDS = _telegram_dialog_list_timeout_seconds()
