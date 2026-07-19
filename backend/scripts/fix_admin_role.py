"""
修复 admin 用户角色。

将 admin 从 USER → ADMIN。
仅修改 role 字段，不修改密码或其他字段。
"""
import sys
sys.path.insert(0, ".")

import asyncio
from sqlalchemy import select, update
from app.storage.database import async_session
from app.models.user import User


async def fix_admin_role():
    async with async_session() as db:
        result = await db.execute(
            select(User).where(User.username == "admin")
        )
        admin = result.scalar_one_or_none()

        if not admin:
            print("ERROR: admin 用户不存在。")
            return

        if admin.role == "ADMIN":
            print("admin 角色已经是 ADMIN，无需修改。")
            return

        old_role = admin.role
        admin.role = "ADMIN"
        await db.commit()

        print(f"✅ admin 角色已修复: {old_role} → ADMIN")


if __name__ == "__main__":
    asyncio.run(fix_admin_role())