import os
import uuid
import secrets
import hashlib
import smtplib
from datetime import datetime, timedelta
from typing import Optional
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from fastapi import FastAPI, HTTPException, Depends, status, BackgroundTasks
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, EmailStr
from jose import JWTError, jwt
from passlib.context import CryptContext

# --- SQLALCHEMY IMPORTS ---
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

# --- КОНФИГУРАЦИЯ ---
# URL базы данных (берется из env или дефолтный для локального теста)
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://auth_user:secure_pass@localhost:5432/auth_db")

SECRET_KEY = os.getenv("SECRET_KEY", "dev_secret_key_change_in_prod")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7
RESET_TOKEN_EXPIRE_MINUTES = 15

# Настройки Email (если пустые — вывод в консоль)
SMTP_SERVER = os.getenv("SMTP_SERVER", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
EMAILS_FROM_EMAIL = os.getenv("EMAILS_FROM_EMAIL", "noreply@example.com")

# --- НАСТРОЙКА БАЗЫ ДАННЫХ ---
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- МОДЕЛИ SQL (ТАБЛИЦЫ) ---
class UserModel(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=True)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class RefreshTokenModel(Base):
    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True, index=True)
    token = Column(String, unique=True, index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    expires_at = Column(DateTime, nullable=False)

class PasswordResetTokenModel(Base):
    __tablename__ = "password_reset_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    token_hash = Column(String, unique=True, index=True, nullable=False) # Храним только хэш токена
    expires_at = Column(DateTime, nullable=False)
    used = Column(Boolean, default=False)

# Автоматическое создание таблиц при старте
Base.metadata.create_all(bind=engine)

# --- НАСТРОЙКА БЕЗОПАСНОСТИ (ARGON2) ---
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def get_token_hash(token: str) -> str:
    """Быстрый хэш для временных токенов сброса (SHA256)"""
    return hashlib.sha256(token.encode()).hexdigest()

def send_email_background(email_to: str, subject: str, body: str):
    """Отправка email или вывод в консоль, если SMTP не настроен"""
    # Если сервер не настроен — имитируем отправку (пишем в логи Docker)
    if not SMTP_SERVER:
        print(f"\n{'='*20} [MOCK EMAIL] {'='*20}")
        print(f"To: {email_to}")
        print(f"Subject: {subject}")
        print(f"Body:\n{body}")
        print(f"{'='*54}\n")
        return

    try:
        msg = MIMEMultipart()
        msg['From'] = EMAILS_FROM_EMAIL
        msg['To'] = email_to
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(msg)
        server.quit()
    except Exception as e:
        print(f"ERROR: Failed to send email: {e}")

# --- PYDANTIC СХЕМЫ ---
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

class Tokens(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int

class AuthResponse(BaseModel):
    user: UserResponse
    tokens: Tokens

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class RefreshRequest(BaseModel):
    refresh_token: str

class LogoutRequest(BaseModel):
    refresh_token: str

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

# --- ЗАВИСИМОСТИ (Dependency Injection) ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def create_refresh_token(db: Session, user_id: int):
    expire_dt = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    # JTI (unique ID) нужен для возможности отзыва конкретного токена
    to_encode = {"sub": str(user_id), "exp": expire_dt, "type": "refresh", "jti": str(uuid.uuid4())}
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

    db_token = RefreshTokenModel(token=encoded_jwt, user_id=user_id, expires_at=expire_dt)
    db.add(db_token)
    db.commit()
    return encoded_jwt

async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id_str: str = payload.get("sub")
        token_type: str = payload.get("type")

        if user_id_str is None or token_type != "access":
            raise credentials_exception

        user_id = int(user_id_str)
    except (JWTError, ValueError):
        raise credentials_exception

    user = db.query(UserModel).filter(UserModel.id == user_id).first()
    if user is None:
        raise credentials_exception
    return user

# --- API ПРИЛОЖЕНИЕ ---
app = FastAPI(title="Auth Service API")

@app.post("/api/auth/register", response_model=AuthResponse, status_code=201)
async def register(user_in: UserCreate, db: Session = Depends(get_db)):
    # Проверка на существующий email
    if db.query(UserModel).filter(UserModel.email == user_in.email).first():
        raise HTTPException(status_code=409, detail="Email already registered")

    new_user = UserModel(
        email=user_in.email,
        name=user_in.name,
        hashed_password=get_password_hash(user_in.password)
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    access_token = create_access_token(data={"sub": str(new_user.id)})
    refresh_token = create_refresh_token(db, new_user.id)

    return {
        "user": new_user,
        "tokens": {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60
        }
    }

@app.post("/api/auth/login", response_model=AuthResponse)
async def login(login_data: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(UserModel).filter(UserModel.email == login_data.email).first()
    if not user or not verify_password(login_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    access_token = create_access_token(data={"sub": str(user.id)})
    refresh_token = create_refresh_token(db, user.id)

    return {
        "user": user,
        "tokens": {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60
        }
    }

@app.get("/api/auth/me", response_model=UserResponse)
async def read_users_me(current_user: UserModel = Depends(get_current_user)):
    return current_user

@app.post("/api/auth/refresh", response_model=Tokens)
async def refresh_token_endpoint(request: RefreshRequest, db: Session = Depends(get_db)):
    # 1. Ищем токен в БД
    db_token = db.query(RefreshTokenModel).filter(RefreshTokenModel.token == request.refresh_token).first()
    if not db_token:
        raise HTTPException(status_code=401, detail="Refresh token not found (might be revoked)")

    # 2. Проверка срока действия
    if datetime.utcnow() > db_token.expires_at:
        db.delete(db_token)
        db.commit()
        raise HTTPException(status_code=401, detail="Token expired")

    user_id = db_token.user_id

    # 3. Ротация токена (удаляем старый, выдаем новый)
    # Это защищает от кражи refresh-токена: если старый использован дважды, это сигнал атаки.
    db.delete(db_token)
    db.commit()

    new_access = create_access_token(data={"sub": str(user_id)})
    new_refresh = create_refresh_token(db, user_id)

    return {
        "access_token": new_access,
        "refresh_token": new_refresh,
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60
    }

@app.post("/api/auth/logout")
async def logout(request: LogoutRequest, db: Session = Depends(get_db)):
    db.query(RefreshTokenModel).filter(RefreshTokenModel.token == request.refresh_token).delete()
    db.commit()
    return {"message": "Logged out"}

@app.post("/api/auth/change-password")
async def change_password(
        request: ChangePasswordRequest,
        current_user: UserModel = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    if not verify_password(request.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect current password")

    current_user.hashed_password = get_password_hash(request.new_password)
    db.commit()
    return {"message": "Password updated successfully"}

# --- ВОССТАНОВЛЕНИЕ ПАРОЛЯ ---

@app.post("/api/auth/forgot-password")
async def forgot_password(
        request: ForgotPasswordRequest,
        background_tasks: BackgroundTasks,
        db: Session = Depends(get_db)
):
    user = db.query(UserModel).filter(UserModel.email == request.email).first()

    # Возвращаем OK даже если email не найден (security best practice: user enumeration protection)
    if not user:
        return {"message": "If the email exists, a reset link has been sent."}

    # 1. Генерируем случайный токен
    reset_token = secrets.token_urlsafe(32)
    token_hash = get_token_hash(reset_token)
    expires_at = datetime.utcnow() + timedelta(minutes=RESET_TOKEN_EXPIRE_MINUTES)

    # 2. Сохраняем хэш токена в БД
    # Если есть старые неиспользованные токены пользователя, их можно удалять, но здесь упрощено
    db_reset = PasswordResetTokenModel(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=expires_at
    )
    db.add(db_reset)
    db.commit()

    # 3. Отправляем Email (в фоне)
    # В реальном проекте замените frontend-app.com на ваш домен фронтенда
    reset_link = f"http://localhost:3000/reset-password?token={reset_token}"
    email_body = (
        f"Hello {user.name or 'User'},\n\n"
        f"You requested a password reset. Click the link below to set a new password:\n"
        f"{reset_link}\n\n"
        f"This link is valid for {RESET_TOKEN_EXPIRE_MINUTES} minutes.\n"
        f"If you didn't ask for this, simply ignore this email."
    )

    background_tasks.add_task(send_email_background, user.email, "Password Reset Request", email_body)

    return {"message": "If the email exists, a reset link has been sent."}

@app.post("/api/auth/reset-password")
async def reset_password(request: ResetPasswordRequest, db: Session = Depends(get_db)):
    # 1. Ищем токен по хэшу
    token_hash = get_token_hash(request.token)
    reset_record = db.query(PasswordResetTokenModel).filter(
        PasswordResetTokenModel.token_hash == token_hash,
        PasswordResetTokenModel.used == False
    ).first()

    if not reset_record:
        raise HTTPException(status_code=400, detail="Invalid or expired token")

    if datetime.utcnow() > reset_record.expires_at:
        raise HTTPException(status_code=400, detail="Token expired")

    # 2. Находим пользователя
    user = db.query(UserModel).filter(UserModel.id == reset_record.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # 3. Обновляем пароль
    user.hashed_password = get_password_hash(request.new_password)

    # 4. Помечаем токен как использованный
    reset_record.used = True
    db.commit()

    return {"message": "Password has been reset successfully"}


@app.get("/health")
def health():
    return {"status": "ok", "version": "0.4.0"}