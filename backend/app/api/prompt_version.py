"""PromptTemplateVersion API — version history & rollback endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from ..schemas.prompt_version import PromptVersionResponse
from ..schemas.prompt_template import PromptTemplateResponse
from ..services.prompt_version_service import (
    get_prompt_versions,
    rollback_prompt_version,
)
from ..storage.database import get_db

router = APIRouter(prefix="/api/prompt-templates", tags=["Prompt 版本管理"])


@router.get(
    "/{template_id}/versions",
    response_model=list[PromptVersionResponse],
    summary="获取模板版本历史",
)
async def list_versions(
    template_id: int,
    db: AsyncSession = Depends(get_db),
):
    """返回指定 Prompt 模板的所有历史版本（按版本号升序）。"""
    versions = await get_prompt_versions(db, template_id)
    return [v.to_dict() for v in versions]


@router.post(
    "/{template_id}/rollback/{target_version}",
    response_model=PromptTemplateResponse,
    summary="回滚到指定版本",
)
async def rollback_version(
    template_id: int,
    target_version: int,
    db: AsyncSession = Depends(get_db),
):
    """将模板回滚到指定版本（创建新版本号，不删除历史）。"""
    template = await rollback_prompt_version(db, template_id, target_version)
    if template is None:
        raise HTTPException(
            status_code=404,
            detail=f"模板不存在或版本 {target_version} 不存在",
        )
    logger.info(
        f"PromptTemplate rolled back: id={template.id} to version {template.version}"
    )
    return template.to_dict()