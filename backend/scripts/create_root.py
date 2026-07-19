"""
系统 ROOT 用户初始化脚本。

用法：
    python scripts/create_root.py

要求环境变量：
    ROOT_PASSWORD - ROOT 用户密码（必填）
    DATABASE_URL - 数据库连接 URL（可选，默认使用 .env 中的配置）

安全要求：
    - 密码必须通过环境变量传入，禁止硬编码
    - 已存在 ROOT 用户时禁止重复创建
"""
import os
import sys
import asyncio

# 确保能正确导入项目模块
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import select

from app.core.config import settings
from app.core.roles import UserRole
from app.models.user import User
from app.auth.security import hash_password
from app.storage.database import async_session, init_db


async def create_root_user():
    """创建 ROOT 用户。"""
    # 读取 ROOT_PASSWORD 环境变量
    root_password = os.environ.get("ROOT_PASSWORD")
    if not root_password:
        print("ERROR: 环境变量 ROOT_PASSWORD 未设置。")
        print("请设置 ROOT_PASSWORD 环境变量后再运行。")
        print("示例: set ROOT_PASSWORD=your_secure_password && python scripts/create_root.py")
        sys.exit(1)

    if len(root_password) < 8:
        print("ERROR: ROOT_PASSWORD 长度不能少于 8 位。")
        sys.exit(1)

    # 确保数据库表存在
    print("初始化数据库表...")
    await init_db()

    print("连接数据库...")
    async with async_session() as db:
        # 检查是否已存在 ROOT 用户
        result = await db.execute(
            select(User).where(User.role == UserRole.ROOT, User.deleted_at.is_(None))
        )
        existing_roots = result.scalars().all()

        if existing_roots:
            print("ERROR: ROOT account already exists")
            print(f"已存在 {len(existing_roots)} 个 ROOT 账号:")
            for r in existing_roots:
                print(f"  - {r.username} (id={r.id}, is_system_account={r.is_system_account})")
            print("\n禁止重复创建 ROOT。如果密码需要重置，请在数据库中手动更新。")
            sys.exit(1)

        # 创建 ROOT 用户
        root_user = User(
            username="root",
            role=UserRole.ROOT,
            password_hash=hash_password(root_password),
            is_system_account=True,
            is_active=True,
        )
        db.add(root_user)
        await db.commit()
        await db.refresh(root_user)

        print(f"\n✅ ROOT 用户创建成功！")
        print(f"   用户名:        root")
        print(f"   角色:          {root_user.role}")
        print(f"   系统账号:      {root_user.is_system_account}")
        print(f"   ID:            {root_user.id}")
        print(f"\n⚠️  请妥善保管 ROOT 密码。")


if __name__ == "__main__":
    asyncio.run(create_root_user())