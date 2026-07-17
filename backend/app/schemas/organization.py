"""Organization Pydantic Schema。"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class OrganizationCreate(BaseModel):
    """创建组织请求。"""
    name: str = Field(..., min_length=1, max_length=255, description="组织名称")
    slug: str = Field(..., min_length=1, max_length=100, description="组织唯一标识")
    description: Optional[str] = Field(None, max_length=500, description="组织描述")


class OrganizationUpdate(BaseModel):
    """更新组织请求。"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    slug: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    is_active: Optional[bool] = None


class OrganizationResponse(BaseModel):
    """组织响应。"""
    id: int
    name: str
    slug: str
    description: Optional[str] = None
    is_active: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class OrganizationMemberResponse(BaseModel):
    """组织成员响应。"""
    id: int
    organization_id: int
    user_id: int
    role: str
    joined_at: Optional[datetime] = None
    is_active: bool

    model_config = {"from_attributes": True}


class OrganizationMemberAdd(BaseModel):
    """添加成员请求。"""
    user_id: int = Field(..., description="用户 ID")
    role: str = Field("MEMBER", pattern="^(OWNER|ADMIN|MEMBER)$", description="角色")


class OrganizationMemberUpdateRole(BaseModel):
    """更新成员角色请求。"""
    role: str = Field(..., pattern="^(OWNER|ADMIN|MEMBER)$", description="新角色")


class OrganizationListResponse(BaseModel):
    """组织列表响应。"""
    items: list[OrganizationResponse]
    total: int