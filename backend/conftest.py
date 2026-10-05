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
def no_rate_limits(monkeypatch):
    """关闭限流（0 = 不限流）并清空进程内计数，供"不是测限流"的用例使用。

    两个坑都是实测踩出来的：

    1. 限流键基于 IP / token 摘要，同一次 pytest 进程里的计数是**共享**的：
       任何一个用例打满 ``RATE_LIMIT_LOGIN``（默认 5/分钟）都会让后续用例被
       429 误伤（实测整包跑 ``test_knowledge_access_control`` 全红，
       单文件跑却全绿）。
    2. ``app.core.rate_limit`` 用的是 ``from ..core.config import settings``
       拿到的**自己的模块级引用**；若先前有用例 reload 过 ``app.core.config``，
       两处就不是同一个对象，只改配置模块的 settings 不生效。
    """
    from app.core import config as config_module
    from app.core import rate_limit as rate_limit_module
    from app.services.security.rate_limiter import rate_limiter

    for target in (config_module.settings, rate_limit_module.settings):
        monkeypatch.setattr(target, "RATE_LIMIT_LOGIN", 0)
        monkeypatch.setattr(target, "RATE_LIMIT_CHAT", 0)
        monkeypatch.setattr(target, "RATE_LIMIT_UPLOAD", 0)

    rate_limiter.clear()
    yield
    rate_limiter.clear()


@pytest.fixture
def client(temp_db, monkeypatch):
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

    It also rebinds every ``app.*`` module's ``async_session`` factory to the
    temp DB: the streaming endpoints deliberately manage their own session
    (``async with async_session() as db:``) instead of using ``Depends(get_db)``,
    so overriding ``get_db`` alone leaves them talking to the real engine.
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

    # ---- 自带 session 的代码路径也必须进临时库 ----
    # ``/api/chat/stream`` 与 ``/api/knowledge/query/stream`` 不用 Depends(get_db)，
    # 而是 ``async with async_session() as db:``（services/retrieval_pipeline.py、
    # services/knowledge/runtime_config.py 等同理）。只覆盖 get_db 时它们仍然打真实
    # 引擎：CI 上 DATABASE_URL=sqlite+aiosqlite:///./test.db 是空库 →
    # ``sqlite3.OperationalError: no such table: users``；本机因为默认指向开发库
    # （已有表）而看不出来。
    #
    # 注意这里按**类型**判断而不是按对象身份：``test_db_migration`` /
    # ``test_connection_pool`` 会 ``importlib.reload(app.storage.database)``，
    # reload 后各 API 模块手里仍是 reload 前的旧工厂对象 —— 只认当前那一个的话，
    # 这些模块会被静默漏掉（实测：单跑 test_rate_limit_unified 绿、整包跑红）。
    from sqlalchemy.ext.asyncio import async_sessionmaker

    for module in list(sys.modules.values()):
        if not getattr(module, "__name__", "").startswith("app."):
            continue
        if isinstance(getattr(module, "async_session", None), async_sessionmaker):
            monkeypatch.setattr(module, "async_session", temp_db.session)

    test_client = TestClient(app)
    try:
        yield test_client
    finally:
        for dependency in db_dependencies:
            app.dependency_overrides.pop(dependency, None)
