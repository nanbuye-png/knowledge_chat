"""迁移链回归测试 —— 审计 §6.1-5（api_keys 空桩）。

审计原文：
    5) [数据-实测] 迁移 ``d5660fbbb75e`` 是空桩 → 全新部署后 ``api_keys`` 表
       不存在（开发库实测 26 张表，无 ``api_keys``）

根因不是"忘了写 DDL"，而是 ``alembic/env.py`` **手写模型导入清单**：新增的
``ApiKey`` 没被导入 → autogenerate 比对不出来 → 生成只有 ``pass`` 的迁移，
却照样被 stamp 成 head。于是「迁移都跑过了，表还是没有」，直到有人调用
``/api/api-keys`` 才 500。

本文件从**全新数据库**起跑整条迁移链（子进程 + 临时 SQLite，绝不碰开发库）：

1. ``api_keys`` 表必须真的被建出来（列定义、唯一约束、索引都要对）；
2. ``alembic check`` 必须报 "No new upgrade operations detected." —— 这条同时
   守住"新增模型不用改 env.py"：再有人漏导入模型，check 立刻会多出 create_table；
3. 迁移建表后 ``create_all`` 兜底路径必须仍然可重入（历史踩过
   "index already exists"）。
"""

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

_BACKEND_DIR = Path(__file__).resolve().parent.parent


def _alembic_env(db_path: Path) -> dict:
    """指向临时库的环境变量：缺一个参数就会写到开发库 backend/knowledge.db。"""
    env = os.environ.copy()
    env["DATABASE_TYPE"] = "sqlite"
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    env["ENVIRONMENT"] = "testing"
    return env


def _run_alembic(db_path: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=_BACKEND_DIR,
        env=_alembic_env(db_path),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
    )


def _full_metadata():
    """导入 ``app/models`` 下全部模块，返回完整 metadata（与 conftest 同法）。"""
    import importlib
    import pkgutil

    import app.models as models_pkg
    from app.models.document import Base

    for module_info in pkgutil.iter_modules(models_pkg.__path__):
        if module_info.name != "__init__":
            importlib.import_module(f"app.models.{module_info.name}")
    return Base.metadata


def _head_revision() -> str:
    """从 alembic 脚本目录取当前 head（仓库只应有单一 head）。"""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(Config(str(_BACKEND_DIR / "alembic.ini")))
    heads = script.get_heads()
    assert len(heads) == 1, f"迁移链出现多个 head：{heads}"
    return heads[0]


def _upgrade_head(db_path: Path) -> None:
    result = _run_alembic(db_path, "upgrade", "head")
    assert result.returncode == 0, f"alembic upgrade head 失败：\n{result.stdout}\n{result.stderr}"


class TestApiKeysMigration:
    def test_fresh_database_gets_api_keys_table(self, tmp_path):
        """全新库跑完迁移链后，api_keys 必须与模型一致（审计 §6.1-5）。"""
        db_path = tmp_path / "fresh.db"
        _upgrade_head(db_path)

        con = sqlite3.connect(db_path)
        try:
            tables = {
                name for name, kind in con.execute("select name, type from sqlite_master")
                if kind == "table"
            }
            assert "api_keys" in tables, f"迁移后仍缺 api_keys 表：{sorted(tables)}"

            columns = {row[1]: row for row in con.execute("PRAGMA table_info(api_keys)")}
            assert list(columns) == [
                "id",
                "user_id",
                "name",
                "key_hash",
                "key_prefix",
                "last_used_at",
                "expires_at",
                "is_active",
                "created_at",
            ]
            assert columns["user_id"][3] == 1, "user_id 必须 NOT NULL"
            assert columns["is_active"][3] == 1, "is_active 必须 NOT NULL"
            # 默认值的字面形态交给 test_migrated_schema_matches_create_all 逐列比对，
            # 这里只看"确实有默认值"（SQLite 会把 DEFAULT '1' 原样回报）。
            assert columns["is_active"][4], "is_active 必须有 server_default"

            indexes = {
                name for name, kind in con.execute("select name, type from sqlite_master")
                if kind == "index" and name.startswith("ix_api_keys")
            }
            assert indexes == {"ix_api_keys_user_id", "ix_api_keys_key_hash"}, indexes

            version = list(con.execute("select version_num from alembic_version"))
            assert version == [(_head_revision(),)], version
        finally:
            con.close()
        print(f"[PASS] 全新库迁移后 api_keys 表/索引齐全，head={_head_revision()}")

    def test_migrated_schema_matches_create_all(self, tmp_path):
        """迁移建出来的 api_keys 必须与模型 create_all 的产物**逐列一致**。

        这是防漂移的核心断言：模型改了列（类型/可空/默认值）而迁移没跟上时，
        这里会直接报出差异，而不是等到线上查不到列才被发现。
        """
        migrated = tmp_path / "migrated.db"
        _upgrade_head(migrated)

        from sqlalchemy import create_engine

        expected = tmp_path / "create_all.db"
        engine = create_engine(f"sqlite:///{expected.as_posix()}")
        try:
            _full_metadata().create_all(engine)
        finally:
            engine.dispose()

        def _columns(path):
            con = sqlite3.connect(path)
            try:
                return {
                    row[1]: (row[2], row[3], row[4])
                    for row in con.execute("PRAGMA table_info(api_keys)")
                }
            finally:
                con.close()

        migrated_columns = _columns(migrated)
        expected_columns = _columns(expected)
        assert migrated_columns == expected_columns, (
            "迁移与模型的 api_keys 列定义不一致：\n"
            f"迁移={migrated_columns}\n模型={expected_columns}"
        )
        print(f"[PASS] 迁移与 create_all 的 api_keys 列定义一致（{len(migrated_columns)} 列）")

    def test_alembic_check_reports_no_drift(self, tmp_path):
        """迁移链必须与模型元数据完全一致（模型漏导入会立刻暴露）。

        ``alembic check`` 是"元数据 vs 数据库"的差异检测：只要再出现一次
        「模型加了、env.py 没导入」，输出里就会多出 create_table 操作。
        """
        metadata = _full_metadata()
        assert "api_keys" in metadata.tables, "模型元数据里应有 api_keys（否则本测试无意义）"

        db_path = tmp_path / "drift.db"
        _upgrade_head(db_path)

        result = _run_alembic(db_path, "check")
        assert result.returncode == 0, (
            "迁移链与模型存在漂移（模型是否忘了被 alembic/env.py 收集？）：\n"
            f"{result.stdout}\n{result.stderr}"
        )
        assert "No new upgrade operations detected" in result.stdout
        print("[PASS] alembic check: No new upgrade operations detected")

    def test_create_all_fallback_still_works_after_migration(self, tmp_path):
        """create_all 兜底路径必须可重入（历史缺陷：重复索引 index already exists）。"""
        db_path = tmp_path / "fallback.db"
        _upgrade_head(db_path)

        from sqlalchemy import create_engine

        engine = create_engine(f"sqlite:///{db_path.as_posix()}")
        try:
            # checkfirst=True：迁移已建好的表/索引应当被跳过，而不是抛
            # "index ix_... already exists"
            _full_metadata().create_all(engine)
        finally:
            engine.dispose()
        print("[PASS] 迁移后 create_all 兜底无冲突")


if __name__ == "__main__":  # pragma: no cover - 便于手工单跑
    sys.exit(pytest.main([__file__, "-v"]))
