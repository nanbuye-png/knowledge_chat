"""LLM Model CRUD service.

Provider 在落库前统一走 :func:`app.core.config.normalize_provider` 归一
（历史写法 ``agens`` → ``agnes``），与 API 层的校验形成双保险：内部脚本、后台任务等
绕过 Pydantic 的入口写进来的别名也不会再让 Agent 运行期 502。
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import normalize_provider
from ..models.llm_model import LLMModel
from ..schemas.llm_model import LLMModelCreate, LLMModelUpdate


async def create_llm_model(db: AsyncSession, data: LLMModelCreate) -> LLMModel:
    """Create a new LLM model configuration."""
    model = LLMModel(
        name=data.name,
        provider=normalize_provider(data.provider),
        model_name=data.model_name,
        enabled=data.enabled,
    )
    db.add(model)
    await db.commit()
    await db.refresh(model)
    return model


async def get_llm_models(db: AsyncSession) -> list[LLMModel]:
    """Get all LLM model configurations, ordered by id."""
    result = await db.execute(select(LLMModel).order_by(LLMModel.id))
    return list(result.scalars().all())


async def get_llm_model_by_id(db: AsyncSession, model_id: int) -> LLMModel | None:
    """Get a single LLM model configuration by id."""
    result = await db.execute(select(LLMModel).where(LLMModel.id == model_id))
    return result.scalar_one_or_none()


async def update_llm_model(db: AsyncSession, model_id: int, data: LLMModelUpdate) -> LLMModel | None:
    """Update an existing LLM model configuration. Returns None if not found."""
    model = await get_llm_model_by_id(db, model_id)
    if model is None:
        return None

    update_data = data.model_dump(exclude_unset=True)
    if update_data.get("provider"):
        update_data["provider"] = normalize_provider(update_data["provider"])
    for key, value in update_data.items():
        setattr(model, key, value)

    await db.commit()
    await db.refresh(model)
    return model


async def delete_llm_model(db: AsyncSession, model_id: int) -> bool:
    """Delete an LLM model configuration. Returns True if deleted, False if not found."""
    model = await get_llm_model_by_id(db, model_id)
    if model is None:
        return False

    await db.delete(model)
    await db.commit()
    return True