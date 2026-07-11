"""PromptTemplateVersion service — version history & rollback logic."""
from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.prompt_template import PromptTemplate
from ..models.prompt_template_version import PromptTemplateVersion


async def get_prompt_versions(
    db: AsyncSession, template_id: int
) -> list[PromptTemplateVersion]:
    """Return all version snapshots for a template, ordered by version ascending.

    Args:
        db: An active async SQLAlchemy session.
        template_id: The parent template's id.

    Returns:
        A list of :class:`PromptTemplateVersion` records (may be empty).
    """
    stmt = (
        select(PromptTemplateVersion)
        .where(PromptTemplateVersion.template_id == template_id)
        .order_by(PromptTemplateVersion.version)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def _get_max_version(db: AsyncSession, template_id: int) -> int:
    """Return the highest version number for the given template, or 0 if none."""
    stmt = select(func.max(PromptTemplateVersion.version)).where(
        PromptTemplateVersion.template_id == template_id
    )
    result = await db.execute(stmt)
    max_ver = result.scalar()
    return max_ver or 0


async def create_prompt_version(
    db: AsyncSession, template_id: int, content: str
) -> PromptTemplateVersion:
    """Create a new immutable version snapshot for a template.

    Auto‑increments the version number based on existing records.

    Args:
        db: An active async SQLAlchemy session.
        template_id: The parent template's id.
        content: The content to store in this version.

    Returns:
        The newly created :class:`PromptTemplateVersion`.
    """
    next_version = await _get_max_version(db, template_id) + 1
    version_record = PromptTemplateVersion(
        template_id=template_id,
        version=next_version,
        content=content,
    )
    db.add(version_record)
    await db.flush()
    logger.info(
        f"PromptTemplateVersion created: template_id={template_id}, version={next_version}"
    )
    return version_record


async def rollback_prompt_version(
    db: AsyncSession, template_id: int, target_version: int
) -> PromptTemplate | None:
    """Rollback a prompt template to a previous version's content.

    Creates a **new** version snapshot containing the content from
    *target_version* and updates the parent template's ``content`` and
    ``version`` fields.  No historical versions are deleted.

    Args:
        db: An active async SQLAlchemy session.
        template_id: The parent template's id.
        target_version: The version number to rollback to.

    Returns:
        The updated :class:`PromptTemplate`, or ``None`` if the
        target version or template does not exist.
    """
    # 1. Look up the target version record
    stmt = (
        select(PromptTemplateVersion)
        .where(
            PromptTemplateVersion.template_id == template_id,
            PromptTemplateVersion.version == target_version,
        )
    )
    result = await db.execute(stmt)
    target_record = result.scalar_one_or_none()
    if target_record is None:
        logger.warning(
            f"Rollback failed: version {target_version} not found for template {template_id}"
        )
        return None

    # 2. Look up the parent template
    template = await db.get(PromptTemplate, template_id)
    if template is None:
        logger.warning(f"Rollback failed: template {template_id} not found")
        return None

    # 3. Create a new version with the old content
    next_version = await _get_max_version(db, template_id) + 1
    new_version = PromptTemplateVersion(
        template_id=template_id,
        version=next_version,
        content=target_record.content,
    )
    db.add(new_version)

    # 4. Update the parent template to point to the rolled-back content
    template.content = target_record.content
    template.version = next_version

    await db.commit()
    await db.refresh(template)
    logger.info(
        f"Rollback: template_id={template_id} -> version {next_version} "
        f"(content from v{target_version})"
    )
    return template