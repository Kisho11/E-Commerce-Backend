from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field
from app.models.user import UserRole


class UserBase(BaseModel):
    email: EmailStr
    full_name: str = Field(..., min_length=1, max_length=100)
    phone: Optional[str] = None


class UserCreate(UserBase):
    password: str = Field(..., min_length=8, max_length=128)
    recaptcha_token: Optional[str] = None


class UserUpdate(BaseModel):
    full_name: Optional[str] = Field(None, min_length=1, max_length=100)
    phone: Optional[str] = None


class UserResponse(UserBase):
    id: int
    role: UserRole
    is_active: bool
    is_email_verified: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class RegisterResponse(BaseModel):
    message: str
    email_verification_required: bool = True


class ManagerCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(..., min_length=1, max_length=100)
    phone: Optional[str] = None
    password: Optional[str] = Field(None, min_length=8, max_length=128)


class ManagerUpdate(BaseModel):
    full_name: Optional[str] = Field(None, min_length=1, max_length=100)
    phone: Optional[str] = None
    email: Optional[EmailStr] = None


class ManagerResponse(UserResponse):
    pass


class Token(BaseModel):
    token_type: str = "bearer"
    user: Optional[UserResponse] = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    recaptcha_token: Optional[str] = None


class RefreshTokenRequest(BaseModel):
    refresh_token: Optional[str] = None


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    reset_token: str
    new_password: str = Field(..., min_length=8, max_length=128)


class PasswordResetResponse(BaseModel):
    message: str


class GoogleAuthRequest(BaseModel):
    id_token: str
    mode: str = "signin"


class EmailVerifyResponse(BaseModel):
    message: str


class ResendVerificationRequest(BaseModel):
    email: EmailStr
