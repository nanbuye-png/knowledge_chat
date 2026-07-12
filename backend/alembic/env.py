import re
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import create_engine, pool

from alembic import context

# ---- Ensure backend root (3 levels up from alembic/ -> backend/) is on sys.path ----
_backend_root = Path(__file__).resolve().parent.parent
if str(_backend_root) not in sys.path:
    sys.path.insert(0, str(_backend_root))

# ---- Load settings (must happen before importing models to avoid circular imports) ----
from app.core.config import settings  # noqa: E402

# ---- Import all models so Alembic can detect them ----
from app.models.document import Base  # noqa: E402
from app.models.user import User  # noqa: E402, F401
from app.models.knowledge_base import KnowledgeBase  # noqa: E402, F401
from app.models.document import Document  # noqa: E402, F401
from app.models.conversation import Conversation  # noqa: E402, F401
from app.models.message import Message  # noqa: E402, F401
from app.models.llm_model import LLMModel  # noqa: E402, F401
from app.models.prompt_template import PromptTemplate  # noqa: E402, F401
from app.models.prompt_template_version import PromptTemplateVersion  # noqa: E402, F401
from app.models.llm_usage import LLMUsage  # noqa: E402, F401
from app.models.knowledge_config import KnowledgeConfig  # noqa: E402, F401

# ---- Alembic Config object ----
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ---- Target metadata for autogenerate ----
target_metadata = Base.metadata

# ---- Dynamic database URL from project settings ----
_db_url = settings.DATABASE_URL

# Convert async URL to sync URL for Alembic (which uses a sync engine)
# e.g. sqlite+aiosqlite:///./knowledge.db → sqlite:///./knowledge.db
_sync_url = re.sub(r'\+aiosqlite', '', _db_url, count=1)

# Use render_as_batch for SQLite (needed for ALTER operations)
_sqlite_mode = _db_url.startswith("sqlite")


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    context.configure(
        url=_sync_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode with a sync engine."""
    connectable = create_engine(
        _sync_url,
        echo=False,
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=_sqlite_mode,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()