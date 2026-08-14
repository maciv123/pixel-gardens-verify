import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from nft_collections import Collection, load_collections

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    discord_bot_token: str
    discord_guild_id: int
    verify_channel_id: int | None
    verify_base_url: str
    api_host: str
    api_port: int
    db_path: str
    collections: tuple[Collection, ...]
    # Primary PG collection fields (web session + backward compatibility)
    contract_address: str
    chain_id: int
    robinhood_rpc_url: str


def _require(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def load_settings() -> Settings:
    verify_channel = os.getenv("VERIFY_CHANNEL_ID", "").strip()
    collections = load_collections()

    pg = next((c for c in collections if c.name == "PG"), None)
    if pg is None or not pg.enabled or not pg.contract:
        raise RuntimeError(
            "PG collection is not configured. Set CONTRACT_ADDRESS (or PG_CONTRACT_ADDRESS) "
            "and at least PG_ROLE_HOLDER or HOLDER_ROLE_ID."
        )

    return Settings(
        discord_bot_token=_require("DISCORD_BOT_TOKEN"),
        discord_guild_id=int(_require("DISCORD_GUILD_ID")),
        verify_channel_id=int(verify_channel) if verify_channel else None,
        verify_base_url=os.getenv("VERIFY_BASE_URL", "http://localhost:8080").rstrip("/"),
        api_host=os.getenv("API_HOST", "0.0.0.0"),
        api_port=int(os.getenv("PORT", os.getenv("API_PORT", "8080"))),
        db_path=os.getenv("DB_PATH", str(PROJECT_ROOT / "data" / "verifications.db")),
        collections=collections,
        contract_address=pg.contract,
        chain_id=pg.chain_id,
        robinhood_rpc_url=pg.rpc_url,
    )
