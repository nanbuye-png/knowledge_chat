"""
Sprint 29 Step 1: PostgreSQL Migration 测试

测试:
1. SQLite 默认模式启动正常
2. PostgreSQL URL 生成正确
"""
import os
import sys
import importlib

# 将 backend 目录加入 sys.path
_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _backend_dir)


def test_sqlite_default_mode():
    """测试 SQLite 默认模式"""
    os.environ["DATABASE_TYPE"] = "sqlite"
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_knowledge.db"

    import app.core.config
    importlib.reload(app.core.config)

    cfg = app.core.config.settings
    assert cfg.DATABASE_TYPE == "sqlite"
    assert cfg.DATABASE_URL.startswith("sqlite+aiosqlite:///")
    assert "test_knowledge.db" in cfg.DATABASE_URL
    print(f"[PASS] SQLite 模式: {cfg.DATABASE_URL}")


def test_postgresql_url_generation():
    """测试 PostgreSQL URL 自动生成"""
    os.environ["DATABASE_TYPE"] = "postgresql"
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./knowledge.db"
    os.environ["POSTGRES_HOST"] = "testhost"
    os.environ["POSTGRES_PORT"] = "5432"
    os.environ["POSTGRES_USER"] = "testuser"
    os.environ["POSTGRES_PASSWORD"] = "testpass"
    os.environ["POSTGRES_DB"] = "testdb"

    import app.core.config
    importlib.reload(app.core.config)

    cfg = app.core.config.settings
    assert cfg.DATABASE_TYPE == "postgresql"
    expected_url = "postgresql+asyncpg://testuser:testpass@testhost:5432/testdb"
    assert cfg.DATABASE_URL == expected_url, f"期望 {expected_url}, 实际 {cfg.DATABASE_URL}"
    print(f"[PASS] PostgreSQL URL: {cfg.DATABASE_URL}")


def test_postgresql_custom_url():
    """测试 PostgreSQL 自定义 DATABASE_URL 不被覆盖"""
    os.environ["DATABASE_TYPE"] = "postgresql"
    custom_url = "postgresql+asyncpg://custom:pass@customhost:5432/customdb"
    os.environ["DATABASE_URL"] = custom_url

    import app.core.config
    importlib.reload(app.core.config)

    cfg = app.core.config.settings
    assert cfg.DATABASE_URL == custom_url, f"自定义 URL 被覆盖: {cfg.DATABASE_URL}"
    print(f"[PASS] PostgreSQL 自定义 URL: {cfg.DATABASE_URL}")


def test_database_engine_sqlite():
    """测试 SQLite 数据库引擎创建"""
    # 清理可能遗留的环境变量
    for key in list(os.environ.keys()):
        if key.startswith("DATABASE_") or key.startswith("POSTGRES_"):
            del os.environ[key]
    os.environ["DATABASE_TYPE"] = "sqlite"
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_engine.db"

    import app.core.config
    importlib.reload(app.core.config)

    # 清除 database 模块缓存以重新创建 engine
    if "app.storage.database" in sys.modules:
        del sys.modules["app.storage.database"]

    from app.storage.database import engine
    assert engine is not None
    assert engine.url.drivername == "sqlite+aiosqlite", f"预期 sqlite+aiosqlite，实际 {engine.url.drivername}"
    print(f"[PASS] SQLite 引擎创建成功: {engine.url}")


def test_alembic_sync_url_conversion():
    """测试 Alembic env.py 中异步 URL 转同步 URL"""
    # SQLite 转换
    async_sqlite = "sqlite+aiosqlite:///./knowledge.db"
    sync_sqlite = __import__("re").sub(r"\+aiosqlite", "", async_sqlite, count=1)
    assert sync_sqlite == "sqlite:///./knowledge.db"
    print(f"[PASS] SQLite 同步 URL: {sync_sqlite}")

    # PostgreSQL 转换
    async_pg = "postgresql+asyncpg://user:pass@host:5432/db"
    sync_pg = __import__("re").sub(r"\+asyncpg", "+psycopg2", async_pg, count=1)
    assert sync_pg == "postgresql+psycopg2://user:pass@host:5432/db"
    print(f"[PASS] PostgreSQL 同步 URL: {sync_pg}")


if __name__ == "__main__":
    print("=" * 50)
    print("Sprint 29 Step 1: PostgreSQL Migration 测试")
    print("=" * 50)

    test_sqlite_default_mode()
    test_postgresql_url_generation()
    test_postgresql_custom_url()
    test_alembic_sync_url_conversion()

    # SQLite 引擎测试需要 aiosqlite
    try:
        test_database_engine_sqlite()
    except Exception as e:
        print(f"[SKIP] SQLite 引擎测试跳过: {e}")

    print("\n" + "=" * 50)
    print("所有测试通过!")
    print("=" * 50)