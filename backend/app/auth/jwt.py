import uuid
from datetime import datetime, timedelta, timezone

import jwt

from ..core.config import settings

ALGORITHM = "HS256"


def create_access_token(user_id: int, role: str = None) -> str:
    """创建 JWT 访问令牌，user_id 存储在 'sub' 声明中（以字符串形式存储）。

    Args:
        user_id: 用户 ID
        role: 用户角色，如 ROOT / ADMIN / USER。若提供则写入 token payload。

    Payload 包含：
        - sub: 用户 ID（字符串形式）
        - iat: 签发时间
        - exp: 过期时间
        - jti: JWT 唯一标识符（UUID，用于黑名单撤销）
        - role: 用户角色（可选）
    """
    now = datetime.now(timezone.utc)
    expire = now + timedelta(hours=settings.ACCESS_TOKEN_EXPIRE_HOURS)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": expire,
        "jti": str(uuid.uuid4()),
    }
    if role is not None:
        payload["role"] = role
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