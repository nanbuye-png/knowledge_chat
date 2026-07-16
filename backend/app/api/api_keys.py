"""API Key 管理 API — 用户端创建、查询、撤销、删除自己的 API Key。

端点：
  POST   /api/api-keys         — 创建新的 API Key（返回明文一次）
  GET    /api/api-keys         — 查询用户的 API Key 列表
  PATCH  /api/api-keys/{id}/revoke  — 撤销 API Key
  DELETE /api/api-keys/{id}    — 删除 API Key
"""

from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from ..auth.deps import get_current_user
from ..models.user import User
from ..schemas.api_key import (
    ApiKeyCreate, ApiKeyResponse, ApiKeyCreatedResponse, ApiKeyRevokeResponse,
)
from ..services.api_key_service import (
    create_api_key, revoke_api_key, delete_api_key, get_user_api_keys,
)
from ..services.audit_service import create_audit_log
from ..storage.database import get_db

router = APIRouter(prefix="/api/api-keys", tags=["API Key 管理"])


@router.post("", response_model=ApiKeyCreatedResponse, status_code=status.HTTP_201_CREATED, summary="创建 API Key")
async def create_api_key_endpoint(
    request: ApiKeyCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """创建新的 API Key。

    密钥仅在创建时返回一次（api_key 字段），请立即保存。
    数据库仅存储密钥的 SHA256 hash。
    """
    api_key, raw_key = await create_api_key(
        db=db,
        user_id=current_user.id,
        name=request.name,
    )

    await create_audit_log(
        db=db, operator_id=current_user.id, action="API_KEY_CREATE",
        target_type="api_key", target_id=api_key.id,
        detail={"name": request.name}, status="SUCCESS",
    )

    logger.info(f"API Key created: {api_key.key_prefix} by user {current_user.username}")
    return ApiKeyCreatedResponse(
        id=api_key.id,
        name=api_key.name,
        api_key=raw_key,
        created_at=api_key.created_at.isoformat() if api_key.created_at else None,
    )


@router.get("", response_model=list[ApiKeyResponse], summary="获取 API Key 列表")
async def list_api_keys(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取当前用户的所有 API Key。"""
    keys = await get_user_api_keys(db, current_user.id)
    return [
        ApiKeyResponse(
            id=k.id,
            name=k.name,
            key_prefix=k.key_prefix,
            is_active=k.is_active,
            last_used_at=k.last_used_at.isoformat() if k.last_used_at else None,
            expires_at=k.expires_at.isoformat() if k.expires_at else None,
            created_at=k.created_at.isoformat() if k.created_at else None,
        )
        for k in keys
    ]


@router.patch("/{key_id}/revoke", response_model=ApiKeyRevokeResponse, summary="撤销 API Key")
async def revoke_api_key_endpoint(
    key_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """撤销指定的 API Key（软删除，设置 is_active=False）。"""
    api_key = await revoke_api_key(db=db, key_id=key_id, user_id=current_user.id)

    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API Key 不存在",
        )

    await create_audit_log(
        db=db, operator_id=current_user.id, action="API_KEY_REVOKE",
        target_type="api_key", target_id=api_key.id,
        detail={"name": api_key.name}, status="SUCCESS",
    )

    logger.info(f"API Key revoked: {api_key.key_prefix} by user {current_user.username}")
    return ApiKeyRevokeResponse(
        id=api_key.id,
        name=api_key.name,
        is_active=api_key.is_active,
        message=f"API Key '{api_key.name}' 已撤销",
    )


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除 API Key")
async def delete_api_key_endpoint(
    key_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """物理删除指定的 API Key。"""
    # 先获取 key 信息用于审计日志
    from ..models.api_key import ApiKey as ApiKeyModel
    from sqlalchemy import select

    result = await db.execute(
        select(ApiKeyModel).where(ApiKeyModel.id == key_id, ApiKeyModel.user_id == current_user.id)
    )
    existing = result.scalar_one_or_none()

    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API Key 不存在",
        )

    deleted = await delete_api_key(db=db, key_id=key_id, user_id=current_user.id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API Key 不存在",
        )

    await create_audit_log(
        db=db, operator_id=current_user.id, action="API_KEY_DELETE",
        target_type="api_key", target_id=key_id,
        detail={"name": existing.name}, status="SUCCESS",
    )
    logger.info(f"API Key deleted: {existing.key_prefix} by user {current_user.username}")