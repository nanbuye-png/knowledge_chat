"""Audit Log Service — 审计日志记录与查询。

提供 create_audit_log 用于记录业务事件，以及 get_logs 用于分页查询。
自动从 fastapi.Request 提取客户端 IP 和 User-Agent。
"""

import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import Request
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from ..models.audit_log import AuditLog


def _extract_client_info(request: Request | None) -> tuple[str | None, str | None]:
    """从 Request 中提取客户端 IP 和 User-Agent。

    Args:
        request: FastAPI Request 对象

    Returns:
        (ip_address, user_agent)
    """
    if request is None:
        return None, None

    ip_address = None
    try:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            ip_address = forwarded.split(",")[0].strip()
        elif request.client:
            ip_address = request.client.host
    except Exception:
        ip_address = None

    user_agent = request.headers.get("User-Agent")
    if user_agent and len(user_agent) > 255:
        user_agent = user_agent[:255]

    return ip_address, user_agent


async def create_audit_log(
    db: AsyncSession,
    operator_id: int,
    action: str,
    target_type: str = "system",
    target_id: int | None = None,
    detail: dict | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    status: str = "SUCCESS",
) -> AuditLog:
    """创建审计日志记录。

    Args:
        db: 数据库会话
        operator_id: 操作者用户 ID
        action: 操作类型（如 LOGIN_SUCCESS, USER_DISABLE, DOCUMENT_DELETE）
        target_type: 目标对象类型（如 user, document, knowledge_base）
        target_id: 目标对象 ID
        detail: 附加详情字典，存储为 JSON 字符串
        ip_address: 操作者 IP
        user_agent: 客户端 User-Agent
        status: 操作结果（SUCCESS / FAILURE）

    Returns:
        创建的 AuditLog 对象
    """
    log_entry = AuditLog(
        operator_id=operator_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        detail=json.dumps(detail, ensure_ascii=False) if detail is not None else None,
        ip_address=ip_address,
        user_agent=user_agent,
        status=status,
        created_at=datetime.now(timezone.utc),
    )
    db.add(log_entry)
    await db.commit()
    await db.refresh(log_entry)
    logger.debug(f"Audit log created: action={action}, operator_id={operator_id}")
    return log_entry


async def get_logs(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    action: str | None = None,
    user_id: int | None = None,
    target_type: str | None = None,
    status: str | None = None,
) -> dict:
    """分页查询审计日志。

    Args:
        db: 数据库会话
        page: 页码（从 1 开始）
        page_size: 每页条数（最大 100）
        action: 按操作类型过滤（可选）
        user_id: 按操作者过滤（可选）
        target_type: 按目标类型过滤（可选）
        status: 按状态过滤（可选）

    Returns:
        {
            "items": [...],
            "total": int,
            "page": int,
            "page_size": int,
        }
    """
    page_size = min(page_size, 100)
    offset = (page - 1) * page_size

    query = select(AuditLog)
    count_query = select(func.count(AuditLog.id))

    filters = []
    if action:
        filters.append(AuditLog.action == action)
    if user_id:
        filters.append(AuditLog.operator_id == user_id)
    if target_type:
        filters.append(AuditLog.target_type == target_type)
    if status:
        filters.append(AuditLog.status == status)

    for f in filters:
        query = query.where(f)
        count_query = count_query.where(f)

    # Total
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Items
    query = query.order_by(desc(AuditLog.created_at)).offset(offset).limit(page_size)
    result = await db.execute(query)
    items = result.scalars().all()

    return {
        "items": [item.to_dict() for item in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }