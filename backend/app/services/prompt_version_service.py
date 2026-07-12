"""PromptTemplateVersion service — version history & rollback logic."""
from loguru import logger
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.exceptions import ResourceNotFoundError
from ..core.prompt_cache import prompt_cache
from ..models.prompt_template import PromptTemplate
from ..models.prompt_template_version import PromptTemplateVersion
from ..schemas.prompt_template import PromptTemplateResponse


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


# ---------------------------------------------------------------------------
# PromptVersionService — activation‑switch rollback (no new versions created)
# ---------------------------------------------------------------------------


class PromptVersionService:
    """Service for prompt version history queries and activation‑switch rollback.

    Unlike the legacy module‑level ``rollback_prompt_version``, this class
    implements rollback by reactivating an existing version snapshot **without**
    creating a new version record.
    """

    async def rollback_prompt_version(
        self,
        db: AsyncSession,
        template_id: int,
        version: int,
    ) -> PromptTemplate:
        """Rollback to a previous version by switching the ``is_active`` flag.

        1. Look up the parent :class:`PromptTemplate`.
        2. Look up the target :class:`PromptTemplateVersion`.
        3. Deactivate **all** currently active versions for this template.
        4. Activate the target version.
        5. Sync the parent template's ``content`` and ``version``.
        6. Commit in a single transaction.
        7. Update :data:`~app.core.prompt_cache.prompt_cache`.

        Raises:
            ResourceNotFoundError: If the template or target version does not exist.
        """
        # 1. Resolve the parent prompt template
        template = await db.get(PromptTemplate, template_id)
        if template is None:
            raise ResourceNotFoundError(resource="PromptTemplate", identifier=template_id)

        # 2. Resolve the target version record
        target_stmt = (
            select(PromptTemplateVersion)
            .where(
                PromptTemplateVersion.template_id == template_id,
                PromptTemplateVersion.version == version,
            )
        )
        result = await db.execute(target_stmt)
        target_record = result.scalar_one_or_none()
        if target_record is None:
            raise ResourceNotFoundError(
                resource="PromptTemplateVersion",
                identifier=f"template_id={template_id}, version={version}",
            )

        # 3. Deactivate every currently active version for this template
        await db.execute(
            update(PromptTemplateVersion)
            .where(
                PromptTemplateVersion.template_id == template_id,
                PromptTemplateVersion.is_active == True,
            )
            .values(is_active=False)
        )

        # 4. Activate the target version
        target_record.is_active = True

        # 5. Sync the parent PromptTemplate
        template.content = target_record.content
        template.version = target_record.version

        # 6. Commit
        await db.commit()
        await db.refresh(template)

        logger.info(
            f"Rollback (activation-switch): template_id={template_id} "
            f"-> version {version}"
        )

        # 7. Sync cache
        response = PromptTemplateResponse(**template.to_dict())
        await prompt_cache.set(template.name, response)

        return template
