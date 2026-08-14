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
    try:
        settings = load_settings()
    except Exception as exc:
        print(f"STARTUP FAILED: {exc}", flush=True)
        sys.exit(1)

    print(
        f"Starting verify API on {settings.api_host}:{settings.api_port}",
        flush=True,
    )
    print(f"Verify URL base: {settings.verify_base_url}", flush=True)
    build = os.getenv("RAILWAY_GIT_COMMIT_SHA", "local")
    print(f"Build: {build[:12] if build else 'local'}", flush=True)

    init_db(settings.db_path)
    bot = create_bot(settings)

    api_thread = threading.Thread(
        target=run_api,
        args=(settings, bot),
        daemon=True,
        name="verify-api",
    )
    api_thread.start()

    # Let uvicorn bind before Discord connects (Railway health checks).
    await asyncio.sleep(2)

    try:
        await bot.start(settings.discord_bot_token)
    except Exception as exc:
        print(f"Discord login failed: {exc}", flush=True)
        print("Verify API stays online; fix token and redeploy.", flush=True)
        while True:
            await asyncio.sleep(3600)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
