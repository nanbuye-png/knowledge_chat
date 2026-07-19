"""
测试用户初始化脚本。

创建三个测试用户用于开发环境测试：
- root:    ROOT (密码通过环境变量或默认)
- admin:   ADMIN (默认密码 admin123456)
- user01:  USER  (默认密码 user123456)

用法：
    python scripts/seed_test_users.py
"""
import os
import sys
import asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env.example"))

from app.core.roles import UserRole
from app.models.user import User
from app.auth.security import hash_password


TEST_USERS = [
    {
        "username": "root",
        "password": os.environ.get("ROOT_PASSWORD", "root123456"),
        "role": UserRole.ROOT,
        "is_system_account": True,
        "is_active": True,
    },
    {
        "username": "admin",
        "password": "admin123456",
        "role": UserRole.ADMIN,
        "is_active": True,
    },
    {
        "username": "user01",
        "password": "user123456",
        "role": UserRole.USER,
        "is_active": True,
    },
]


async def seed_test_users():
    """创建或更新测试用户。"""
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        from app.core.config import settings
        database_url = settings.DATABASE_URL

    if not database_url:
        print("ERROR: 无法获取 DATABASE_URL。")
        sys.exit(1)

    if database_url.startswith("sqlite"):
        database_url = database_url.replace("sqlite://", "sqlite+aiosqlite://")

    engine = create_async_engine(database_url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as db:
        created = 0
        updated = 0
        skipped = 0

        for user_data in TEST_USERS:
            result = await db.execute(
                select(User).where(User.username == user_data["username"])
            )
            existing = result.scalar_one_or_none()

            if existing:
                if existing.role == user_data["role"]:
                    skipped += 1
                    print(f"⏭️  {existing.username} (role={existing.role}) - 已存在，跳过")
                else:
                    old_role = existing.role
                    existing.role = user_data["role"]
                    existing.password_hash = hash_password(user_data["password"])
                    existing.is_system_account = user_data.get("is_system_account", False)
                    existing.is_active = user_data["is_active"]
                    existing.deleted_at = None
                    await db.commit()
                    updated += 1
                    print(f"🔄 {existing.username}: {old_role} -> {user_data['role']} (已更新)")
            else:
                user = User(
                    username=user_data["username"],
                    role=user_data["role"],
                    password_hash=hash_password(user_data["password"]),
                    is_system_account=user_data.get("is_system_account", False),
                    is_active=user_data["is_active"],
                )
                db.add(user)
                await db.commit()
                await db.refresh(user)
                created += 1
                print(f"✅ {user.username} (role={user.role}) - 已创建")

        print(f"\n📊 摘要: 创建 {created}，更新 {updated}，跳过 {skipped}")


if __name__ == "__main__":
    print("🌱 初始化测试用户...\n")
    asyncio.run(seed_test_users())
    print("\n✨ 完成！")