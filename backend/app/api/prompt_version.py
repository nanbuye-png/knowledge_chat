"""PromptTemplateVersion API — version history endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..schemas.prompt_version import PromptVersionResponse
from ..services.prompt_version_service import get_prompt_versions
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
