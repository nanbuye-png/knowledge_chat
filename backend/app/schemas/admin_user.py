from pydantic import BaseModel


class AdminUserResponse(BaseModel):
    """管理员视角的用户详情，包含安全与审计字段。"""
    id: int
    username: str
    email: str | None = None
    role: str
    is_system_account: bool = False
    is_active: bool
    last_activity_at: str | None = None
    last_login_at: str | None = None
    failed_login_count: int = 0
    locked_until: str | None = None
    deleted_at: str | None = None
    created_at: str | None = None