import asyncio
import os
import socket
import sys
import threading

import uvicorn

from api import create_api, create_bot
from config import load_settings
from db import init_db

INSTANCE_LOCK_PORT = 47201
_instance_lock: socket.socket | None = None


def ensure_single_instance() -> None:
    global _instance_lock
    lock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        lock.bind(("127.0.0.1", INSTANCE_LOCK_PORT))
    except OSError:
        print(
            "Bot is already running! Close all other bot windows first, "
            "then run start-bot.bat again.",
            flush=True,
        )
        sys.exit(1)
    # Keep the socket open for the process lifetime so the lock is not released.
    _instance_lock = lock


def run_api(settings, bot) -> None:
    api = create_api(settings, bot)
    uvicorn.run(
        api,
        host=settings.api_host,
        port=settings.api_port,
        log_level="info",
    )


async def main() -> None:
    if not os.getenv("RENDER") and not os.getenv("RAILWAY_ENVIRONMENT"):
        ensure_single_instance()
    settings = load_settings()
    init_db(settings.db_path)

    bot = create_bot(settings)

    api_thread = threading.Thread(
        target=run_api,
        args=(settings, bot),
        daemon=True,
        name="verify-api",
    )
    api_thread.start()

    await bot.start(settings.discord_bot_token)


if __name__ == "__main__":
    asyncio.run(main())
