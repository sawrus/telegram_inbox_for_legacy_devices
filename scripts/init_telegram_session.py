import asyncio
import os
from pathlib import Path

from telethon import TelegramClient


async def main():
    api_id = os.getenv("TELEGRAM_API_ID")
    api_hash = os.getenv("TELEGRAM_API_HASH")
    session_name = os.getenv("TELEGRAM_SESSION_NAME", "telegram-inbox")
    session_dir = Path(os.getenv("TELEGRAM_SESSION_DIR", "/data"))

    if not api_id or not api_hash:
        raise SystemExit("Set TELEGRAM_API_ID and TELEGRAM_API_HASH in .env first")

    session_dir.mkdir(parents=True, exist_ok=True)
    session_path = session_dir / session_name

    client = TelegramClient(str(session_path), int(api_id), api_hash)
    await client.start()
    me = await client.get_me()
    print("Authorized Telegram session for:", me.first_name or me.username or me.id)
    print("Session file prefix:", session_path)
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
