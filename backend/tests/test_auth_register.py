"""Tests for 注册接口（POST /api/auth/register）行为与错误契约。

重点覆盖导致"注册不了，只显示请求失败"的几个真实原因：

1. 后端密码策略（12 位 + 大小写 + 数字 + 特殊字符）不满足时返回 400，
   且错误体是统一的 ``{"code", "message"}``（前端必须解析 ``message``）。
2. 用户名 / 邮箱重复时返回 409（而不是唯一索引冲突导致的 500）。
3. 密码以 bcrypt 哈希落库，不存明文。

Run: cd backend && ..\\.venv\\Scripts\\python.exe -m pytest tests/test_auth_register.py -v
"""

import sys
from pathlib import Path

sys.path.insert(0, ".")

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.auth import router as auth_router
from app.core.exceptions import http_exception_handler
from app.models.user import User
from app.storage.database import get_db


VALID_PASSWORD = "Str0ng@Passw0rd"


# ============================================================================
# Test 1 — 注册成功
# ============================================================================

class TestRegisterSuccess:
    """注册成功路径。"""

    def test_valid_registration_returns_user(self, tmp_path):
        """合法用户名 + 强密码 → 200，返回用户信息且不含密码字段。"""
        status_code, body = register(tmp_path, "ok.db", {
            "username": "newuser",
            "email": "newuser@example.com",
            "password": VALID_PASSWORD,
        })

        assert status_code == 200
        assert body["username"] == "newuser"
        assert body["email"] == "newuser@example.com"
        assert body["role"] == "USER"
        assert "password" not in body
        assert "password_hash" not in body

    def test_email_is_optional(self, tmp_path):
        """不传邮箱 → 200，email 为 None。"""
        status_code, body = register(tmp_path, "no_email.db", {
            "username": "noemail",
            "password": VALID_PASSWORD,
        })

        assert status_code == 200
        assert body["email"] is None

    def test_password_is_stored_hashed(self, tmp_path):
        """密码必须以 bcrypt 哈希落库，不得保存明文。"""
        stored_hash = register_and_fetch_hash(tmp_path, "hash.db", "hashuser")

        assert stored_hash != VALID_PASSWORD
        assert stored_hash.startswith("$2")


# ============================================================================
# Test 2 — 错误契约（前端 client.ts 依赖）
# ============================================================================

class TestRegisterErrorContract:
    """错误响应必须遵循 ``{"code", "message"}`` 契约。"""

    def test_weak_password_returns_400_with_message(self, tmp_path):
        """弱密码（如 6 位纯数字）→ 400，message 说明具体原因。"""
        status_code, body = register(tmp_path, "weak.db", {
            "username": "weakuser",
            "password": "123456",
        })

        assert status_code == 400
        assert body["code"] == "HTTP_ERROR"
        assert "密码长度至少需要 12 位" in body["message"]
        assert "密码必须包含至少一个大写字母" in body["message"]
        # 契约中不含 detail 字段，前端若只读 detail 就只能显示"请求失败"
        assert "detail" not in body

    def test_duplicate_username_returns_409(self, tmp_path):
        """用户名重复 → 409 + 可读提示。"""
        payload = {"username": "dupuser", "password": VALID_PASSWORD}
        status_code, body = register_many(tmp_path, "dup_user.db", [payload, payload])[1]

        assert status_code == 409
        assert body["code"] == "HTTP_ERROR"
        assert body["message"] == "用户名已存在"

    def test_duplicate_email_returns_409(self, tmp_path):
        """邮箱重复 → 409（唯一索引冲突不能冒泡成 500）。"""
        first = {"username": "mail1", "email": "same@example.com", "password": VALID_PASSWORD}
        second = {"username": "mail2", "email": "same@example.com", "password": VALID_PASSWORD}
        status_code, body = register_many(tmp_path, "dup_email.db", [first, second])[1]

        assert status_code == 409
        assert body["message"] == "邮箱已被注册"

    def test_username_too_short_returns_422(self, tmp_path):
        """用户名短于 3 位被 pydantic 拦截 → 422（detail 数组，前端需兼容）。"""
        status_code, body = register(tmp_path, "short_name.db", {
            "username": "ab",
            "password": VALID_PASSWORD,
        })

        assert status_code == 422
        assert isinstance(body["detail"], list)


# ============================================================================
# Helpers
# ============================================================================

async def _make_client(tmp_path: Path, db_name: str):
    """构建测试应用：独立 SQLite 文件 + 覆盖 get_db 依赖。"""
    db_url = f"sqlite+aiosqlite:///{(tmp_path / db_name).as_posix()}"
    engine = create_async_engine(db_url, connect_args={"check_same_thread": False})
    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        # 仅创建注册接口所需的 users 表。
        # 全量 Base.metadata.create_all 会因 UserSession 索引重复定义而失败
        # （docs/INTERVIEW_GUIDE.md 已记录：index ix_user_sessions_user_id already exists）
        await conn.run_sync(lambda sync_conn: User.__table__.create(sync_conn))

    async def _override_get_db():
        async with session_maker() as session:
            yield session

    app = FastAPI()
    # 与 app.main 保持一致：HTTPException → {"code": "HTTP_ERROR", "message": ...}
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.include_router(auth_router)
    app.dependency_overrides[get_db] = _override_get_db

    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")
    return client, engine, session_maker


def register(tmp_path, db_name, payload):
    """提交一次注册请求，返回 (status_code, body)。"""
    return register_many(tmp_path, db_name, [payload])[0]


def register_many(tmp_path, db_name, payloads):
    """在同一数据库上依次提交多个注册请求，返回 [(status_code, body), ...]。"""
    async def _run():
        client, engine, _ = await _make_client(tmp_path, db_name)
        try:
            results = []
            for payload in payloads:
                response = await client.post("/api/auth/register", json=payload)
                results.append((response.status_code, response.json()))
            return results
        finally:
            await client.aclose()
            await engine.dispose()

    return asyncio_run(_run())


def register_and_fetch_hash(tmp_path, db_name, username):
    """注册后直接从数据库读取 password_hash。"""
    async def _run():
        client, engine, session_maker = await _make_client(tmp_path, db_name)
        try:
            response = await client.post("/api/auth/register", json={
                "username": username,
                "password": VALID_PASSWORD,
            })
            assert response.status_code == 200, response.text

            async with session_maker() as session:
                result = await session.execute(select(User).where(User.username == username))
                user = result.scalar_one()
                return user.password_hash
        finally:
            await client.aclose()
            await engine.dispose()

    return asyncio_run(_run())


def asyncio_run(coro):
    import asyncio
    return asyncio.run(coro)

