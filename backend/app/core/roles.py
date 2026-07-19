"""
Backend role definitions.

统一项目角色定义入口。
所有角色相关的字符串引用必须从此模块导入，禁止在多个文件重复写角色字符串。
"""

from .rbac import UserRole

__all__ = ["UserRole"]