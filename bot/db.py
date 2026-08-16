import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def init_db(db_path: str) -> None:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS verify_sessions (
                session_id TEXT PRIMARY KEY,
                discord_user_id TEXT NOT NULL,
                nonce TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                used INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS verifications (
                discord_user_id TEXT PRIMARY KEY,
                wallet_address TEXT NOT NULL UNIQUE,
                verified_at TEXT NOT NULL
            );
            """
        )


@contextmanager
def connect(db_path: str):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def create_session(
    db_path: str, session_id: str, discord_user_id: str, nonce: str, expires_at: datetime
) -> None:
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO verify_sessions (session_id, discord_user_id, nonce, expires_at)
            VALUES (?, ?, ?, ?)
            """,
            (session_id, discord_user_id, nonce, expires_at.isoformat()),
        )


def get_session(db_path: str, session_id: str) -> sqlite3.Row | None:
    with connect(db_path) as conn:
        return conn.execute(
            "SELECT * FROM verify_sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()


def mark_session_used(db_path: str, session_id: str) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE verify_sessions SET used = 1 WHERE session_id = ?",
            (session_id,),
        )


def get_verification_by_discord(db_path: str, discord_user_id: str) -> sqlite3.Row | None:
    with connect(db_path) as conn:
        return conn.execute(
            "SELECT * FROM verifications WHERE discord_user_id = ?",
            (discord_user_id,),
        ).fetchone()


def get_verification_by_wallet(db_path: str, wallet_address: str) -> sqlite3.Row | None:
    with connect(db_path) as conn:
        return conn.execute(
            "SELECT * FROM verifications WHERE wallet_address = ?",
            (wallet_address.lower(),),
        ).fetchone()


def save_verification(db_path: str, discord_user_id: str, wallet_address: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO verifications (discord_user_id, wallet_address, verified_at)
            VALUES (?, ?, ?)
            ON CONFLICT(discord_user_id) DO UPDATE SET
                wallet_address = excluded.wallet_address
            """,
            (discord_user_id, wallet_address.lower(), now),
        )


def get_first_verifier_ids(db_path: str, limit: int) -> list[str]:
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT discord_user_id
            FROM verifications
            ORDER BY verified_at ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [row["discord_user_id"] for row in rows]


def is_og_verifier(db_path: str, discord_user_id: str, limit: int) -> bool:
    return discord_user_id in get_first_verifier_ids(db_path, limit)
