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
# 审计 §6.1-5：这里原来是**手写清单**，新增模型（api_keys）忘了加进来，
# autogenerate 于是产出空迁移（只有 ``pass``）却被 stamp 成 head —— 结果
# 「迁移都跑过了，表还是没有」，直到调用 /api/api-keys 才炸。
# 现在与 tests/conftest.py 一样遍历 app/models/*.py 自动导入，新增模型
# 不需要再改这个文件（tests/test_api_keys_migration.py 会守住这条）。
import importlib  # noqa: E402
import pkgutil  # noqa: E402

import app.models as _models_pkg  # noqa: E402
from app.models.document import Base  # noqa: E402

for _module_info in pkgutil.iter_modules(_models_pkg.__path__):
    if _module_info.name != "__init__":
        importlib.import_module(f"app.models.{_module_info.name}")

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
# sqlite+aiosqlite:///./knowledge.db → sqlite:///./knowledge.db
# postgresql+asyncpg://user:pass@host/db → postgresql+psycopg2://user:pass@host/db
_sync_url = _db_url
_sync_url = re.sub(r'\+aiosqlite', '', _sync_url, count=1)
_sync_url = re.sub(r'\+asyncpg', '+psycopg2', _sync_url, count=1)

# Use render_as_batch for SQLite (needed for ALTER operations)
_db_type = settings.DATABASE_TYPE
_sqlite_mode = _db_type == "sqlite"


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