"""PromptTemplate CRUD service."""
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from ..core.prompt_cache import prompt_cache
from ..models.prompt_template import PromptTemplate
from ..models.prompt_template_version import PromptTemplateVersion
from ..schemas.prompt_template import PromptTemplateCreate, PromptTemplateUpdate, PromptTemplateResponse


async def create_prompt_template(db: AsyncSession, data: PromptTemplateCreate) -> PromptTemplate:
    """Create a new prompt template with an initial version snapshot."""
    template = PromptTemplate(
        name=data.name,
        prompt_type=data.prompt_type,
        content=data.content,
        version=data.version,
        enabled=data.enabled,
        is_active=data.is_active,
    )
    db.add(template)
    await db.flush()  # populate template.id before creating version record

    # Create initial version record (is_active=True for the first version)
    v1 = PromptTemplateVersion(
        template_id=template.id,
        version=data.version,
        content=data.content,
        is_active=True,
    )
    db.add(v1)
    await db.commit()
    await db.refresh(template)
    logger.info(f"PromptTemplate created: id={template.id}, name='{template.name}'")

    response = PromptTemplateResponse(**template.to_dict())
    await prompt_cache.set(template.name, response)

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
    """Update an existing prompt template.

    When *content* changes a **new** :class:`PromptTemplateVersion` is
    created with ``is_active=True`` while the previously active version is
    deactivated.  The ``version`` field is always system‑managed — any
    ``version`` value passed by the caller is ignored.
    """
    template = await get_prompt_template_by_id(db, template_id)
    if template is None:
        return None

    update_data = data.model_dump(exclude_unset=True)
    new_content = update_data.pop("content", None)
    update_data.pop("version", None)  # system-managed, never accept from caller

    # Apply non-content, non-version fields directly
    for key, value in update_data.items():
        setattr(template, key, value)

    if new_content is not None:
        current_version = template.version

        # Deactivate the currently active version(s)
        await db.execute(
            update(PromptTemplateVersion)
            .where(
                PromptTemplateVersion.template_id == template_id,
                PromptTemplateVersion.is_active == True,
            )
            .values(is_active=False)
        )

        # Create a new version snapshot (auto-increment)
        next_version = current_version + 1
        version_record = PromptTemplateVersion(
            template_id=template_id,
            version=next_version,
            content=new_content,
            is_active=True,
        )
        db.add(version_record)

        # Sync parent template
        template.content = new_content
        template.version = next_version

    await db.commit()
    await db.refresh(template)
    logger.info(f"PromptTemplate updated: id={template.id}")

    response = PromptTemplateResponse(**template.to_dict())
    await prompt_cache.set(template.name, response)

    return template


async def delete_prompt_template(db: AsyncSession, template_id: int) -> bool:
    """Delete a prompt template. Returns True if deleted, False if not found."""
    template = await get_prompt_template_by_id(db, template_id)
    if template is None:
        return False

    name = template.name  # capture before deletion for cache invalidation

    await db.delete(template)
    await db.commit()

    await prompt_cache.delete(name)

    return True
