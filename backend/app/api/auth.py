from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
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
from .admin.users import active_user_filter
from ..services.user_service import update_user_activity
from ..services.session_service import create_session
from ..core.config import settings
from ..core.password_policy import validate_password_strength
from ..core.rate_limit import rate_limit
from ..services.audit_service import create_audit_log, _extract_client_info
from ..services.auth.token_service import revoke_token
from ..auth.deps import oauth2_scheme
from ..core.roles import UserRole

# 登录安全配置
MAX_FAILED_LOGIN_ATTEMPTS = 5
LOCK_DURATION_MINUTES = 15

router = APIRouter(prefix="/api/auth", tags=["认证"])


# ---------- Request / Response schemas ----------

class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=100)
    email: str | None = None
    password: str = Field(..., min_length=6, max_length=100)


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str | None = None


class UserResponse(BaseModel):
    id: int
    username: str
    email: str | None = None
    role: str | None = None
    is_system_account: bool | None = None
    created_at: str | None = None


# ---------- Endpoints ----------

@router.post("/register", response_model=UserResponse, summary="注册用户")
async def register(request: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Register a new user account."""
    # Password strength validation
    is_valid, errors = validate_password_strength(request.password)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="；".join(errors),
        )

    # Check if username already exists (including soft-deleted)
    result = await db.execute(select(User).where(User.username == request.username, active_user_filter()))
    existing = result.scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="用户名已存在",
        )

    user = User(
        username=request.username,
        email=request.email,
        password_hash=hash_password(request.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    logger.info(f"User registered: {user.username} (id={user.id})")
    return UserResponse(**user.to_dict())


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="登录",
    dependencies=[
        Depends(rate_limit(
            limit=settings.RATE_LIMIT_LOGIN,
            window_seconds=settings.RATE_LIMIT_WINDOW,
            scope="login",
            use_user=False,
        )),
    ],
)
async def login(
    request: LoginRequest,
    req: Request = None,
    db: AsyncSession = Depends(get_db),
):
    """Authenticate and return JWT access token."""
    now = datetime.now(timezone.utc)
    ip, ua = None, None
    if req is not None:
        ip, ua = _extract_client_info(req)

    result = await db.execute(select(User).where(User.username == request.username, active_user_filter()))
    user = result.scalar_one_or_none()

    # --- 1. 用户不存在，直接返回统一错误（避免枚举用户名） ---
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )

    # --- 2. 检查账户是否被禁用 ---
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账户已被禁用，请联系管理员",
        )

    # --- 3. 检查账户是否被锁定 ---
    if user.locked_until is not None and user.locked_until > now:
        remaining_minutes = int((user.locked_until - now).total_seconds() // 60) + 1
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"账户已被暂时锁定，请 {remaining_minutes} 分钟后再试",
        )

    # --- 4. 密码验证 ---
    if not verify_password(request.password, user.password_hash):
        # 密码错误：增加失败计数
        user.failed_login_count = (user.failed_login_count or 0) + 1

        # 达到阈值则锁定账户
        if user.failed_login_count >= MAX_FAILED_LOGIN_ATTEMPTS:
            user.locked_until = now + timedelta(minutes=LOCK_DURATION_MINUTES)
            logger.warning(
                f"Account locked due to too many failed attempts: "
                f"{user.username} (id={user.id}), locked until {user.locked_until}"
            )

        db.add(user)
        await db.commit()

        # 审计日志：登录失败
        await create_audit_log(
            db=db, operator_id=user.id, action="LOGIN_FAILED",
            target_type="user", target_id=user.id,
            ip_address=ip, user_agent=ua, status="FAILURE",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )

    # --- 5. 登录成功：重置安全字段 ---
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    db.add(user)
    await db.commit()

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

    token = create_access_token(user.id, role=user.role)
    await update_user_activity(db, user.id)

    # 创建 Session 记录
    expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.ACCESS_TOKEN_EXPIRE_HOURS)
    await create_session(
        db=db,
        user_id=user.id,
        token=token,
        ip_address=None,
        expires_at=expires_at,
    )

    # 审计日志：登录成功
    await create_audit_log(
        db=db, operator_id=user.id, action="LOGIN_SUCCESS",
        target_type="user", target_id=user.id,
        ip_address=ip, user_agent=ua, status="SUCCESS",
    )
    logger.info(f"User logged in: {user.username} (id={user.id}, role={user.role})")
    return TokenResponse(access_token=token, role=user.role)


class LogoutResponse(BaseModel):
    message: str


@router.post("/logout", response_model=LogoutResponse, summary="注销登录")
async def logout(
    req: Request = None,
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
):
    """撤销当前 JWT token，使其立即失效。"""
    ip, ua = None, None
    if req is not None:
        ip, ua = _extract_client_info(req)

    # 尝试解析用户 ID 用于审计日志
    user_id = None
    try:
        from ..auth.jwt import decode_access_token
        payload = decode_access_token(token)
        user_id = int(payload.get("sub", 0)) if payload.get("sub") else None
    except Exception:
        pass

    try:
        await revoke_token(db, token, reason="logout")
    except Exception:
        pass

    # 审计日志：注销
    if user_id:
        await create_audit_log(
            db=db, operator_id=user_id, action="LOGOUT",
            target_type="user", target_id=user_id,
            ip_address=ip, user_agent=ua, status="SUCCESS",
        )
    return LogoutResponse(message="已成功退出登录")


@router.get("/me", response_model=UserResponse, summary="当前用户信息")
async def get_me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return current authenticated user's info.
    
    is_system_account 只对 ROOT 用户返回，普通用户不返回此字段。
    """
    await update_user_activity(db, current_user.id)
    return UserResponse(**current_user.to_dict(include_system_flag=(current_user.role == UserRole.ROOT)))
