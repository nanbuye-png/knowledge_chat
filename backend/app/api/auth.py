from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from loguru import logger

from ..auth.jwt import create_access_token
from ..auth.security import hash_password, verify_password
from ..auth.deps import get_current_user
from ..models.user import User
from ..models.knowledge_base import KnowledgeBase
from ..storage.database import get_db

router = APIRouter(prefix="/api/auth", tags=["认证"])


# ---------- Request / Response schemas ----------

class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=6, max_length=100)


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: int
    username: str
    created_at: str | None = None


# ---------- Endpoints ----------

@router.post("/register", response_model=UserResponse, summary="注册用户")
async def register(request: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Register a new user account."""
    # Check if username already exists
    result = await db.execute(select(User).where(User.username == request.username))
    existing = result.scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="用户名已存在",
        )

    user = User(
        username=request.username,
        password_hash=hash_password(request.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    logger.info(f"User registered: {user.username} (id={user.id})")
    return UserResponse(**user.to_dict())


@router.post("/login", response_model=TokenResponse, summary="登录")
async def login(request: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Authenticate and return JWT access token."""
    result = await db.execute(select(User).where(User.username == request.username))
    user = result.scalar_one_or_none()

    if user is None or not verify_password(request.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )

    # Auto-create default knowledge base if user has none
    count_result = await db.execute(
        select(KnowledgeBase).where(KnowledgeBase.user_id == user.id)
    )
    existing_kb = count_result.scalars().first()
    if existing_kb is None:
        default_kb = KnowledgeBase(
            user_id=user.id,
            name="默认知识库",
            description="系统自动创建的默认知识库",
        )
        db.add(default_kb)
        await db.commit()
        logger.info(f"Auto-created default knowledge base for user {user.username} (id={user.id})")

    token = create_access_token(user.id)
    logger.info(f"User logged in: {user.username} (id={user.id})")
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserResponse, summary="当前用户信息")
async def get_me(current_user: User = Depends(get_current_user)):
    """Return current authenticated user's info."""
    return UserResponse(**current_user.to_dict())