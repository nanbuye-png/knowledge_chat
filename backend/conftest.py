"""Shared pytest fixtures for the backend test suite (P0-5).

Why this file exists
--------------------
Before P0-5 the suite had **no** ``conftest.py`` / ``pytest.ini`` /
``pyproject.toml`` and every DB-touching test replaced the session with
``AsyncMock`` — so no SQL ever ran and real-database defects (missing
``api_keys`` table, naive/aware datetime, duplicate indexes) stayed
invisible while the suite reported "green" (audit §8).

This file provides:

* ``temp_db`` — a **real** SQLite database (temp file, NullPool) with the
  full schema created from the model metadata.
* ``client``  — a ``TestClient`` with the ``get_db`` dependency overridden
  to the temp DB, **without** running the app lifespan (so tests never
  touch the developer database, the vector store or download models).

Importing every model module is done here (and only here) so that
``Base.metadata`` is complete — ``alembic/env.py`` only imports a subset,
which is why autogenerate produced an empty migration for ``api_keys``.
"""
from __future__ import annotations

import asyncio
import importlib
import sys
from pathlib import Path

import pytest

_BACKEND_DIR = Path(__file__).resolve().parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

# ---- 导入全部模型，保证 Base.metadata 完整 ----
for _model_file in sorted((_BACKEND_DIR / "app" / "models").glob("*.py")):
    if _model_file.stem != "__init__":
        importlib.import_module(f"app.models.{_model_file.stem}")


class TempDatabase:
    """临时 SQLite 数据库（真实 SQL 往返，便于暴露真实缺陷）。"""

    def __init__(self, url: str):
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
        from sqlalchemy.pool import NullPool

        self.url = url
        # NullPool：每个 asyncio.run() 使用独立事件循环，连接不能跨循环复用
        self.engine = create_async_engine(
            url,
            echo=False,
            poolclass=NullPool,
            connect_args={"check_same_thread": False},
        )
        self._session_factory = async_sessionmaker(
            self.engine, expire_on_commit=False
        )

    def session(self):
        """Return a new AsyncSession bound to this temp database."""
        return self._session_factory()

    async def create_schema(self) -> None:
        from app.models.document import Base

        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def dispose(self) -> None:
        await self.engine.dispose()


@pytest.fixture
def temp_db(tmp_path) -> TempDatabase:
    """Provision a temporary SQLite database with the full schema."""
    url = "sqlite+aiosqlite:///" + (tmp_path / "test.db").as_posix()
    db = TempDatabase(url)
    asyncio.run(db.create_schema())
    try:
        yield db
    finally:
        asyncio.run(db.dispose())


@pytest.fixture
def client(temp_db):
    """HTTP client with ``get_db`` pointed at the temp DB.

    The lifespan is intentionally **not** executed: it would initialise the
    developer database, the vector store and load the embedding model.
    Route wiring and dependency resolution are still fully exercised.

    Why every route module's ``get_db`` is overridden
    -------------------------------------------------
    Some test modules call ``importlib.reload(app.storage.database)``
    (``test_db_migration`` / ``test_connection_pool``) to rebuild the engine.
    After a reload, ``app.storage.database.get_db`` is a **new function
    object**, while the API modules still hold the old one captured at import
    time —— overriding only the freshly imported object silently has no
    effect and the requests hit the real developer database
    (observed: ``backend/knowledge.db`` gained test users/documents).
    So we override the function object that each route module actually
    references, plus the current one for good measure.
    """
    import importlib
    import pkgutil

    from fastapi.testclient import TestClient

    import app.api as api_pkg
    from app.main import app
    from app.storage.database import get_db

    async def _override_get_db():
        async with temp_db.session() as session:
            yield session

    db_dependencies = {get_db}
    for module_info in pkgutil.iter_modules(api_pkg.__path__):
        try:
            module = importlib.import_module(f"app.api.{module_info.name}")
        except Exception:  # noqa: BLE001 - 某个子模块导入失败不应影响其余覆盖
            continue
        dependency = getattr(module, "get_db", None)
        if dependency is not None:
            db_dependencies.add(dependency)

    for dependency in db_dependencies:
        app.dependency_overrides[dependency] = _override_get_db

    test_client = TestClient(app)
    try:
        yield test_client
    finally:
        for dependency in db_dependencies:
            app.dependency_overrides.pop(dependency, None)
