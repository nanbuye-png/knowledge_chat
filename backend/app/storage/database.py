import os
from pathlib import Path

from loguru import logger
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from ..core.config import settings
from ..models.document import Base
from ..models.user import User  # noqa: F401 - 注册 User 模型用于建表
from ..models.knowledge_base import KnowledgeBase  # noqa: F401 - 注册 KnowledgeBase 模型用于建表
from ..models.conversation import Conversation  # noqa: F401 - 注册 Conversation 模型用于建表
from ..models.message import Message  # noqa: F401 - 注册 Message 模型用于建表
from ..models.document import Document  # noqa: F401 - 迁移所需
from ..models.llm_model import LLMModel  # noqa: F401 - 注册 LLMModel 模型用于建表
from ..models.prompt_template import PromptTemplate  # noqa: F401 - 注册 PromptTemplate 模型用于建表
from ..models.prompt_template_version import PromptTemplateVersion  # noqa: F401 - 注册 PromptTemplateVersion 模型用于建表
from ..models.knowledge_config import KnowledgeConfig  # noqa: F401 - 注册 KnowledgeConfig 模型用于建表
from ..models.llm_usage import LLMUsage  # noqa: F401 - 注册 LLMUsage 模型用于建表
from ..models.permission import Role, Permission, user_roles, role_permissions  # noqa: F401 - RBAC 模型
from ..models.token_blacklist import TokenBlacklist  # noqa: F401 - Token 黑名单模型
from ..models.api_key import ApiKey  # noqa: F401 - API Key 模型


# 根据数据库 URL 创建引擎
if settings.DATABASE_URL.startswith("sqlite"):
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        connect_args={"check_same_thread": False},
    )
else:
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        pool_size=10,
        max_overflow=20,
    )

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    """依赖注入：获取异步数据库会话。"""
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()


async def _run_alembic_upgrade() -> bool:
    """程序化运行 Alembic 迁移。

    返回值：
        True 表示迁移成功执行（或已是最新版本）。
        False 表示 alembic_version 表不存在（首次初始化）。
    """
    from alembic.config import Config as AlembicConfig
    from alembic import command as alembic_command

    # 定位 alembic.ini — 该文件位于 backend/ 目录
    _backend_dir = Path(__file__).resolve().parent.parent.parent
    _alembic_ini = _backend_dir / "alembic.ini"
    _alembic_dir = _backend_dir / "alembic"

    if not _alembic_ini.exists():
        logger.warning("alembic.ini not found, falling back to create_all")
        return False

    alembic_cfg = AlembicConfig(str(_alembic_ini))
    # 确保正确的 script_location 覆盖 ini 中的值
    alembic_cfg.set_main_option("script_location", str(_alembic_dir))

    try:
        alembic_command.upgrade(alembic_cfg, "head")
        logger.info("Alembic 迁移执行成功")
        return True
    except Exception as e:
        logger.warning(f"Alembic 升级失败: {e}")
        return False


async def init_db():
    """启动时初始化数据库。

    生产环境：运行 ``alembic upgrade head``，仅在数据库为空/首次初始化时
    回退到 ``create_all``。

    旧的 ad-hoc 迁移（``_migrate_users_add_email`` 和
    ``_migrate_documents_add_kb_id``）已由初始 Alembic 迁移处理，不再需要。
    """
    _ran_alembic = await _run_alembic_upgrade()

    if not _ran_alembic:
        # 开发环境/首次启动回退：从模型元数据创建表
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("通过 create_all 创建数据库表（回退模式）")

    # 初始化 RBAC 默认角色和权限
    try:
        async with async_session() as session:
            from ..services.auth.rbac_service import RBACService
            await RBACService.init_default_roles(session)
    except Exception as e:
        logger.warning(f"RBAC 初始化失败: {e}")

    logger.info("数据库表就绪")


async def close_db():
    """关闭时释放引擎。"""
    await engine.dispose()
    logger.info("数据库引擎已释放")


