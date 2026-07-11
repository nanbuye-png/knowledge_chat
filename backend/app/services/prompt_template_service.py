"""PromptTemplate CRUD service."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from ..models.prompt_template import PromptTemplate
from ..models.prompt_template_version import PromptTemplateVersion
from ..schemas.prompt_template import PromptTemplateCreate, PromptTemplateUpdate
from .prompt_version_service import create_prompt_version


async def create_prompt_template(db: AsyncSession, data: PromptTemplateCreate) -> PromptTemplate:
    """Create a new prompt template with version=1 snapshot."""
    template = PromptTemplate(
        name=data.name,
        prompt_type=data.prompt_type,
        content=data.content,
        version=1,
        enabled=data.enabled,
    )
    db.add(template)
    await db.flush()  # populate template.id before creating version record

    # Create version=1 record
    v1 = PromptTemplateVersion(
        template_id=template.id,
        version=1,
        content=data.content,
    )
    db.add(v1)
    await db.commit()
    await db.refresh(template)
    logger.info(f"PromptTemplate created: id={template.id}, name='{template.name}'")
    return template


async def get_prompt_templates(db: AsyncSession) -> list[PromptTemplate]:
    """Get all prompt templates, ordered by id."""
    result = await db.execute(select(PromptTemplate).order_by(PromptTemplate.id))
    return list(result.scalars().all())


async def get_prompt_template_by_id(db: AsyncSession, template_id: int) -> PromptTemplate | None:
    """Get a single prompt template by id."""
    result = await db.execute(select(PromptTemplate).where(PromptTemplate.id == template_id))
    return result.scalar_one_or_none()


async def update_prompt_template(db: AsyncSession, template_id: int, data: PromptTemplateUpdate) -> PromptTemplate | None:
    """Update an existing prompt template. Auto‑creates a version snapshot when content changes. Returns None if not found."""
    template = await get_prompt_template_by_id(db, template_id)
    if template is None:
        return None

    update_data = data.model_dump(exclude_unset=True)
    new_content = update_data.get("content")

    for key, value in update_data.items():
        setattr(template, key, value)

    # When content changes, create a new version snapshot and sync version
    if new_content is not None:
        await db.flush()  # ensure template changes are visible
        version_record = await create_prompt_version(db, template_id, new_content)
        template.version = version_record.version

    await db.commit()
    await db.refresh(template)
    logger.info(f"PromptTemplate updated: id={template.id}")
    return template


async def delete_prompt_template(db: AsyncSession, template_id: int) -> bool:
    """Delete a prompt template. Returns True if deleted, False if not found."""
    template = await get_prompt_template_by_id(db, template_id)
    if template is None:
        return False

    await db.delete(template)
    await db.commit()
    return True
