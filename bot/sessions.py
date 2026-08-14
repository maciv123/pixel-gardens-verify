import re
import secrets

# URL-safe codes from token_urlsafe(12): ~96 bits entropy, single-use, 15-minute TTL.
SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{16,24}$")


def new_session_id() -> str:
    return secrets.token_urlsafe(12).rstrip("=")


def normalize_session_id(session_id: str) -> str:
    code = session_id.strip()
    if not SESSION_ID_PATTERN.match(code):
        raise ValueError("Invalid verification code")
    return code


def build_verify_url(base_url: str, session_id: str) -> str:
    return f"{base_url.rstrip('/')}/verify/{session_id}"
