import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    discord_bot_token: str
    discord_guild_id: int
    holder_role_id: int
    verify_channel_id: int | None
    contract_address: str
    chain_id: int
    robinhood_rpc_url: str
    verify_base_url: str
    api_host: str
    api_port: int
    db_path: str


def _require(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def load_settings() -> Settings:
    verify_channel = os.getenv("VERIFY_CHANNEL_ID", "").strip()
    return Settings(
        discord_bot_token=_require("DISCORD_BOT_TOKEN"),
        discord_guild_id=int(_require("DISCORD_GUILD_ID")),
        holder_role_id=int(_require("HOLDER_ROLE_ID")),
        verify_channel_id=int(verify_channel) if verify_channel else None,
        contract_address=_require("CONTRACT_ADDRESS"),
        chain_id=int(os.getenv("CHAIN_ID", "4663")),
        robinhood_rpc_url=os.getenv(
            "ROBINHOOD_RPC_URL", "https://rpc.mainnet.chain.robinhood.com"
        ),
        verify_base_url=os.getenv("VERIFY_BASE_URL", "http://localhost:8080").rstrip("/"),
        api_host=os.getenv("API_HOST", "0.0.0.0"),
        api_port=int(os.getenv("API_PORT", "8080")),
        db_path=os.getenv("DB_PATH", str(PROJECT_ROOT / "data" / "verifications.db")),
    )
