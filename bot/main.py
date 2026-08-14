import asyncio
import socket
import sys
import threading

import uvicorn

from api import create_api, create_bot
from config import load_settings
from db import init_db

INSTANCE_LOCK_PORT = 47201


def ensure_single_instance() -> None:
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


def run_api(settings, bot) -> None:
    api = create_api(settings, bot)
    uvicorn.run(
        api,
        host=settings.api_host,
        port=settings.api_port,
        log_level="info",
    )


async def main() -> None:
    ensure_single_instance()
    settings = load_settings()
    init_db(settings.db_path)

    bot = create_bot(settings)

    api_thread = threading.Thread(
        target=run_api,
        args=(settings, bot),
        daemon=True,
    )
    api_thread.start()

    await bot.start(settings.discord_bot_token)


if __name__ == "__main__":
    asyncio.run(main())
