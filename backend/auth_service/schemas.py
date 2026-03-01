from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional, List

class UserBase(BaseModel):
    email: EmailStr
    name: Optional[str] = None

class UserCreate(UserBase):
    password: str

class UserResponse(UserBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True

class TokenData(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int

class AuthResponse(BaseModel):
    user: UserResponse
    tokens: TokenData

class RegisterResponse(BaseModel):
    message: str
    email: EmailStr

class VerifyRequest(BaseModel):
    email: EmailStr
    code: str

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class RefreshRequest(BaseModel):
    refresh_token: str

class LogoutRequest(BaseModel):
    refresh_token: str

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

class TokenConfirmRequest(BaseModel):
    token: str

class ResendVerificationRequest(BaseModel):
    email: EmailStr

class ChangeEmailRequest(BaseModel):
    new_email: EmailStr
    current_password: str

class DeleteProfileRequest(BaseModel):
    current_password: str
    confirmation_text: str

class MessageResponse(BaseModel):
    message: str


class FavoriteCreateRequest(BaseModel):
    marketplace: str
    url: str
    name: Optional[str] = None
    img_url: Optional[str] = None
    price: Optional[str] = None


class FavoriteResponse(BaseModel):
    id: int
    marketplace: str
    product_url_original: str
    product_url_canonical: str
    product_name: Optional[str] = None
    img_url: Optional[str] = None
    last_price_amount_rub: Optional[int] = None
    last_price_text: Optional[str] = None
    last_success_price_at: Optional[datetime] = None
    last_refresh_attempt_at: Optional[datetime] = None
    last_refresh_status: str
    last_refresh_error: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class FavoriteDeleteResponse(BaseModel):
    message: str


class FavoriteKeyResponse(BaseModel):
    id: int
    marketplace: str
    product_url_canonical: str
    product_url_original: Optional[str] = None


class FavoriteKeysListResponse(BaseModel):
    items: List[FavoriteKeyResponse]


class FavoritePricePoint(BaseModel):
    ts: datetime
    price_amount_rub: Optional[int] = None
    status: Optional[str] = None


class FavoriteListItem(FavoriteResponse):
    sparkline_30d: List[Optional[int]]
    sparkline_points_30d: List[FavoritePricePoint]
    change_30d_percent: Optional[float] = None


class FavoriteListResponse(BaseModel):
    count: int
    items: List[FavoriteListItem]
    offset: int
    limit: int
    total: int
    has_more: bool


class FavoriteForceUpdateItem(BaseModel):
    id: int
    marketplace: str
    product_name: Optional[str] = None
    status: str
    last_price_amount_rub: Optional[int] = None
    last_price_text: Optional[str] = None
    last_success_price_at: Optional[datetime] = None
    last_refresh_attempt_at: Optional[datetime] = None
    error: Optional[str] = None


class FavoriteForceUpdateResponse(BaseModel):
    count: int
    updated: int
    ok: int
    failed: int
    items: List[FavoriteForceUpdateItem]
