"""LLM Model management API — CRUD for llm_models table."""
from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from ..schemas.llm_model import (
    LLMModelCreate,
    LLMModelResponse,
    LLMModelUpdate,
)
from ..services.llm_model_service import (
    create_llm_model,
    get_llm_models,
    get_llm_model_by_id,
    update_llm_model,
    delete_llm_model,
)
from ..storage.database import get_db

router = APIRouter(prefix="/api/llm-models", tags=["LLM 模型管理"])


@router.get("", response_model=list[LLMModelResponse], summary="获取模型配置列表")
async def list_llm_models(
    db: AsyncSession = Depends(get_db),
):
    """返回所有已配置的 LLM 模型。"""
    models = await get_llm_models(db)
    return [m.to_dict() for m in models]


@router.post("", response_model=LLMModelResponse, status_code=201, summary="创建模型配置")
async def create_model(
    data: LLMModelCreate,
    db: AsyncSession = Depends(get_db),
):
    """创建一个新的 LLM 模型配置。"""
    model = await create_llm_model(db, data)
    logger.info(f"LLM model created: id={model.id}, name='{model.name}', provider='{model.provider}'")
    return model.to_dict()


@router.get("/{model_id}", response_model=LLMModelResponse, summary="获取单个模型配置")
async def get_model(
    model_id: int,
    db: AsyncSession = Depends(get_db),
):
    """根据 ID 获取单个 LLM 模型配置。"""
    model = await get_llm_model_by_id(db, model_id)
    if model is None:
        raise HTTPException(status_code=404, detail="LLM 模型配置不存在")
    return model.to_dict()


@router.put("/{model_id}", response_model=LLMModelResponse, summary="更新模型配置")
async def update_model(
    model_id: int,
    data: LLMModelUpdate,
    db: AsyncSession = Depends(get_db),
):
    """更新已有的 LLM 模型配置（部分更新）。"""
    model = await update_llm_model(db, model_id, data)
    if model is None:
        raise HTTPException(status_code=404, detail="LLM 模型配置不存在")
    logger.info(f"LLM model updated: id={model.id}")
    return model.to_dict()


@router.delete("/{model_id}", status_code=200, summary="删除模型配置")
async def delete_model(
    model_id: int,
    db: AsyncSession = Depends(get_db),
):
    """删除一个 LLM 模型配置。"""
    deleted = await delete_llm_model(db, model_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="LLM 模型配置不存在")
    logger.info(f"LLM model deleted: id={model_id}")
    return {"success": True}
