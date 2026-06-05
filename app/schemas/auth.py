"""
Authentication schemas for login/token requests and responses.
"""

from pydantic import BaseModel
from typing import Optional


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class UserResponse(BaseModel):
    id: int
    username: str
    full_name: str
    role: str
    is_active: bool

    model_config = {"from_attributes": True}
