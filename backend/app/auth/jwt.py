from datetime import datetime, timedelta, timezone

import jwt

from ..core.config import settings

ALGORITHM = "HS256"


def create_access_token(user_id: int) -> str:
    """创建 JWT 访问令牌，user_id 存储在 'sub' 声明中（以字符串形式存储）。"""
    now = datetime.now(timezone.utc)
    expire = now + timedelta(hours=settings.ACCESS_TOKEN_EXPIRE_HOURS)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": expire,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    """解码并验证 JWT 令牌。如果无效则抛出 JWTError。"""
    # 禁用 'sub' 类型检查 — user_id 以字符串形式存储
    return jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[ALGORITHM],
        options={"verify_sub": False},
    )