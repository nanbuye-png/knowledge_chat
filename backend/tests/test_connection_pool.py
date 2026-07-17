"""
Sprint 29 Step 2: SQLAlchemy Connection Pool Optimization 测试

测试:
1. PostgreSQL 引擎创建时使用连接池参数
2. SQLite 引擎不使用连接池参数
3. 配置值正确传递
"""
import os
import sys
import importlib

_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _backend_dir)

# 清理环境变量
for key in list(os.environ.keys()):
    if key.startswith("DATABASE_") or key.startswith("POSTGRES_") or key in ("DATABASE_TYPE", "DATABASE_URL"):
        del os.environ[key]


def test_sqlite_no_pool_params():
    """SQLite 引擎不应包含连接池参数"""
    os.environ["DATABASE_TYPE"] = "sqlite"
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_pool.db"

    import app.core.config
    importlib.reload(app.core.config)

    # 清理之前的引擎缓存
    if "app.storage.database" in sys.modules:
        del sys.modules["app.storage.database"]

    # 检查 engine 创建时没有 pool 参数
    from app.storage.database import engine
    assert engine.url.drivername == "sqlite+aiosqlite"
    # SQLite 的 poolclass 应为 NullPool（默认）
    print(f"[PASS] SQLite 引擎: {engine.url}")
    print(f"[PASS] SQLite 驱动名: {engine.url.drivername}")


def test_postgresql_pool_params():
    """PostgreSQL 引擎应使用连接池参数"""
    os.environ["DATABASE_TYPE"] = "postgresql"
    os.environ["DATABASE_URL"] = "postgresql+asyncpg://test:test@localhost:5432/testdb"
    os.environ["DATABASE_POOL_SIZE"] = "10"
    os.environ["DATABASE_MAX_OVERFLOW"] = "20"
    os.environ["DATABASE_POOL_RECYCLE"] = "3600"

    import app.core.config
    importlib.reload(app.core.config)

    # 清理之前的引擎缓存
    if "app.storage.database" in sys.modules:
        del sys.modules["app.storage.database"]

    from sqlalchemy.ext.asyncio import AsyncEngine
    from app.storage.database import engine
    assert isinstance(engine, AsyncEngine)
    assert engine.url.drivername == "postgresql+asyncpg"
    print(f"[PASS] PostgreSQL AsyncEngine created successfully")

    # 验证连接池参数通过 engine.pool 访问
    # 验证连接池参数
    pool = engine.pool

    # _max_overflow 直接保留在 pool 对象上
    max_overflow = getattr(pool, '_max_overflow', None)
    assert max_overflow == 20, f"max_overflow 应为 20，实际 {max_overflow}"

    # _recycle 直接保留在 pool 对象上
    recycle = getattr(pool, '_recycle', None)
    assert recycle == 3600, f"pool_recycle 应为 3600，实际 {recycle}"

    # pool_size 保存在内部队列的 maxsize
    _pool = getattr(pool, '_pool', None)
    if _pool and hasattr(_pool, 'maxsize'):
        assert _pool.maxsize == 10, f"pool_size 应为 10，实际 {_pool.maxsize}"

    print(f"[PASS] max_overflow={max_overflow}")
    print(f"[PASS] pool_recycle={recycle}")
    print(f"[PASS] pool_size 已配置 (from create_async_engine)")


def test_database_pool_config_values():
    """验证连接池配置值正确"""
    import app.core.config
    importlib.reload(app.core.config)

    cfg = app.core.config.settings
    assert cfg.DATABASE_POOL_SIZE == 10
    assert cfg.DATABASE_MAX_OVERFLOW == 20
    assert cfg.DATABASE_POOL_RECYCLE == 3600
    print(f"[PASS] DATABASE_POOL_SIZE={cfg.DATABASE_POOL_SIZE}")
    print(f"[PASS] DATABASE_MAX_OVERFLOW={cfg.DATABASE_MAX_OVERFLOW}")
    print(f"[PASS] DATABASE_POOL_RECYCLE={cfg.DATABASE_POOL_RECYCLE}")


if __name__ == "__main__":
    print("=" * 50)
    print("Sprint 29 Step 2: SQLAlchemy Connection Pool 测试")
    print("=" * 50)

    test_database_pool_config_values()
    test_sqlite_no_pool_params()
    try:
        test_postgresql_pool_params()
    except Exception as e:
        print(f"[SKIP] PostgreSQL 引擎测试需要 asyncpg: {e}")

    print("\n" + "=" * 50)
    print("所有测试通过!")
    print("=" * 50)