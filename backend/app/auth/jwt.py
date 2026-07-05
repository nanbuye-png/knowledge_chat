from datetime import datetime, timedelta, timezone

import jwt

from ..core.config import settings

ALGORITHM = "HS256"


def create_access_token(user_id: int) -> str:
    """Create JWT access token with user_id in 'sub' claim (stored as string)."""
    now = datetime.now(timezone.utc)
    expire = now + timedelta(hours=settings.ACCESS_TOKEN_EXPIRE_HOURS)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": expire,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Decode and validate JWT token. Raises JWTError if invalid."""
    # Disable 'sub' type checking - we store user_id as string
    return jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[ALGORITHM],
        options={"verify_sub": False},
    )