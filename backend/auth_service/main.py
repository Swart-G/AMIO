from fastapi import FastAPI, HTTPException, Depends, status, Body
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext
import uuid

# --- КОНФИГУРАЦИЯ ---
SECRET_KEY = "your_super_secret_key_change_this_in_production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 15  # 900 секунд, как в примере
REFRESH_TOKEN_EXPIRE_DAYS = 7

# Имитация базы данных
users_db = {}  # id -> user_dict
users_email_index = {}  # email -> user_id
refresh_tokens_db = set()  # Список валидных refresh токенов
reset_tokens_db = {}  # token -> email (для восстановления пароля)

app = FastAPI(
    title="Amio Shop Auth API",
    description="API аутентификации согласно документации",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Настройка безопасности
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


# --- Pydantic МОДЕЛИ ---

class UserBase(BaseModel):
    email: EmailStr
    name: Optional[str] = None


class UserCreate(UserBase):
    password: str


class UserResponse(UserBase):
    id: int
    created_at: datetime


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


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    return pwd_context.hash(password)


def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    refresh_tokens_db.add(encoded_jwt)
    return encoded_jwt


async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        token_type: str = payload.get("type")
        if email is None or token_type != "access":
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user_id = users_email_index.get(email)
    if user_id is None:
        raise credentials_exception
    return users_db[user_id]


# --- API ЭНДПОИНТЫ ---

# Префикс /api/auth согласно документации
@app.post("/api/auth/register", response_model=AuthResponse, status_code=201)
async def register(user_in: UserCreate):
    if user_in.email in users_email_index:
        raise HTTPException(status_code=409, detail="Email already registered")

    new_id = len(users_db) + 1
    created_at = datetime.utcnow()

    user_obj = {
        "id": new_id,
        "email": user_in.email,
        "name": user_in.name,
        "hashed_password": get_password_hash(user_in.password),
        "created_at": created_at
    }

    users_db[new_id] = user_obj
    users_email_index[user_in.email] = new_id

    access_token = create_access_token(data={"sub": user_obj["email"]})
    refresh_token = create_refresh_token(data={"sub": user_obj["email"]})

    return {
        "user": user_obj,
        "tokens": {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60
        }
    }


@app.post("/api/auth/login", response_model=AuthResponse)
async def login(login_data: LoginRequest):
    user_id = users_email_index.get(login_data.email)
    if not user_id or not verify_password(login_data.password, users_db[user_id]["hashed_password"]):
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    user_obj = users_db[user_id]
    access_token = create_access_token(data={"sub": user_obj["email"]})
    refresh_token = create_refresh_token(data={"sub": user_obj["email"]})

    return {
        "user": user_obj,
        "tokens": {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60
        }
    }


@app.get("/api/auth/me", response_model=UserResponse)
async def read_users_me(current_user: dict = Depends(get_current_user)):
    return current_user


@app.post("/api/auth/refresh", response_model=Tokens)
async def refresh_token_endpoint(request: RefreshRequest):
    if request.refresh_token not in refresh_tokens_db:
        raise HTTPException(status_code=401, detail="Invalid or revoked refresh token")

    try:
        payload = jwt.decode(request.refresh_token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        token_type: str = payload.get("type")
        if email is None or token_type != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token structure")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    # Ротация токенов: удаляем старый, выдаем новый
    refresh_tokens_db.remove(request.refresh_token)
    new_access_token = create_access_token(data={"sub": email})
    new_refresh_token = create_refresh_token(data={"sub": email})

    return {
        "access_token": new_access_token,
        "refresh_token": new_refresh_token,
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60
    }


@app.post("/api/auth/logout")
async def logout(request: LogoutRequest):
    if request.refresh_token in refresh_tokens_db:
        refresh_tokens_db.remove(request.refresh_token)
    return {"message": "Logged out"}


@app.post("/api/auth/forgot-password")
async def forgot_password(request: ForgotPasswordRequest):
    # В реальности здесь нужно генерировать безопасный токен и отправлять email
    # Для примера мы просто генерируем UUID и печатаем его в консоль
    if request.email in users_email_index:
        reset_token = str(uuid.uuid4())
        reset_tokens_db[reset_token] = request.email
        print(f"--- MOCK EMAIL ---")
        print(f"To: {request.email}")
        print(f"Reset Link: http://api.amio-shop.ru/reset?token={reset_token}")
        print(f"------------------")

    # Всегда отвечаем ОК для безопасности (чтобы не перебирали email)
    return {"message": "If this email exists, a reset link has been sent"}


@app.post("/api/auth/reset-password")
async def reset_password(request: ResetPasswordRequest):
    email = reset_tokens_db.get(request.token)
    if not email:
        raise HTTPException(status_code=404, detail="Invalid or expired token")

    user_id = users_email_index.get(email)
    if user_id:
        users_db[user_id]["hashed_password"] = get_password_hash(request.new_password)
        del reset_tokens_db[request.token]  # Токен одноразовый
        return {"message": "Password has been reset"}

    raise HTTPException(status_code=404, detail="User not found")


@app.post("/api/auth/change-password")
async def change_password(request: ChangePasswordRequest, current_user: dict = Depends(get_current_user)):
    if not verify_password(request.current_password, current_user["hashed_password"]):
        raise HTTPException(status_code=400, detail="Incorrect current password")

    user_id = current_user["id"]
    users_db[user_id]["hashed_password"] = get_password_hash(request.new_password)

    return {"message": "Password has been changed"}


@app.get("/health")
def health():
    return {"status": "ok", "version": "0.3.0"}

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
