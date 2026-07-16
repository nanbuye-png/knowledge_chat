from enum import Enum


class UserRole(str, Enum):
    """用户角色枚举，所有角色统一引用此定义。"""
    ROOT = "ROOT"
    ADMIN = "ADMIN"
    USER = "USER"

    @classmethod
    def has_permission(cls, role: str, required_role: str) -> bool:
        """检查角色是否满足所需权限等级。
        
        等级: ROOT > ADMIN > USER
        """
        role_order = {cls.ROOT: 3, cls.ADMIN: 2, cls.USER: 1}
        return role_order.get(role, 0) >= role_order.get(required_role, 0)