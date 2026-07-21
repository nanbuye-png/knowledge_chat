"""PromptTemplate management API — CRUD for prompt_templates table."""
from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from ..schemas.prompt_template import (
    PromptTemplateCreate,
    PromptTemplateResponse,
    PromptTemplateUpdate,
)
from ..services.prompt_template_service import (
    create_prompt_template,
    get_prompt_templates,
    get_prompt_template_by_id,
    update_prompt_template,
    delete_prompt_template,
)
from ..services.prompt_version_service import PromptVersionService
from ..auth.deps import get_current_user
from ..core.permissions import require_admin_or_root
from ..models.user import User
from ..storage.database import get_db

router = APIRouter(prefix="/api/prompt-templates", tags=["Prompt 模板管理"])


@router.get("", response_model=list[PromptTemplateResponse], summary="获取模板列表")
async def list_templates(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin_or_root),
):
    """返回所有 Prompt 模板。"""
    templates = await get_prompt_templates(db)
    return [t.to_dict() for t in templates]


@router.post("", response_model=PromptTemplateResponse, status_code=201, summary="创建模板")
async def create_template(
    data: PromptTemplateCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin_or_root),
):
    """创建一个新的 Prompt 模板。"""
    template = await create_prompt_template(db, data)
    logger.info(f"PromptTemplate created: id={template.id}, name='{template.name}'")
    return template.to_dict()


@router.get("/{template_id}", response_model=PromptTemplateResponse, summary="获取单个模板")
async def get_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin_or_root),
):
    """根据 ID 获取单个 Prompt 模板。"""
    template = await get_prompt_template_by_id(db, template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Prompt 模板不存在")
    return template.to_dict()


@router.put("/{template_id}", response_model=PromptTemplateResponse, summary="更新模板")
async def update_template(
    template_id: int,
    data: PromptTemplateUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin_or_root),
):
    """更新已有的 Prompt 模板（部分更新）。"""
    template = await update_prompt_template(db, template_id, data)
    if template is None:
        raise HTTPException(status_code=404, detail="Prompt 模板不存在")
    logger.info(f"PromptTemplate updated: id={template.id}")
    return template.to_dict()


@router.delete("/{template_id}", status_code=200, summary="删除模板")
async def delete_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin_or_root),
):
    """删除一个 Prompt 模板。"""
    deleted = await delete_prompt_template(db, template_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Prompt 模板不存在")
    logger.info(f"PromptTemplate deleted: id={template_id}")
    return {"success": True}


@router.post(
    "/{template_id}/versions/{version}/rollback",
    response_model=PromptTemplateResponse,
    summary="回滚模板版本",
)
async def rollback_version(
    template_id: int,
    version: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin_or_root),
):
    """将 Prompt 模板回滚到指定历史版本。

    通过切换 ``is_active`` 标志激活目标版本，
    不创建新的版本记录。成功后返回当前模板。
    """
    service = PromptVersionService()
    template = await service.rollback_prompt_version(db, template_id, version)
    logger.info(
        f"PromptTemplate rolled back: id={template.id}, name='{template.name}', "
        f"version={template.version}"
    )
    return template.to_dict()