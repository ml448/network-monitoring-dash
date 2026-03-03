from pydantic import BaseModel, EmailStr, Field, field_validator
import re


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=100)

    @field_validator('password')
    @classmethod
    def validate_password(cls, pw: str) -> str:
        if not re.search(r'[A-Z]', pw):
            raise ValueError('Password must contain at least one uppercase letter')
        if not re.search(r'[a-z]', pw):
            raise ValueError('Password must contain at least one lowercase letter')
        if not re.search(r'\d', pw):
            raise ValueError('Password must contain at least one digit')
        return pw
    
    @field_validator('username')
    @classmethod
    def check_username(cls, usr: str) -> str:
        if not re.fullmatch(r'[a-zA-Z0-9_-]+', usr):
            raise ValueError('Username can only contain letters, numbers, underscores, and hyphens')
        return usr

class Token(BaseModel):
    """Schema for JWT token response."""
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    """Schema for decoded JWT payload."""
    username: str | None = None


class UserResponse(BaseModel):
    """Schema for user data in responses (no password!)."""
    id: int
    username: str
    email: str
    is_active: bool

    model_config = {"from_attributes": True}
