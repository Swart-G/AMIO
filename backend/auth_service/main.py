from fastapi import FastAPI, Depends, HTTPException, status, Header, APIRouter
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timedelta
import contextlib
import random
import string

from database import engine, Base, get_db
import models
import schemas
import utils
from config import settings
from sqlalchemy.orm import selectinload

@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield

app = FastAPI(title="Auth Service", lifespan=lifespan)

def generate_verification_code(length=6):
    return ''.join(random.choices(string.digits, k=length))

async def get_current_user(authorization: str = Header(...), db: AsyncSession = Depends(get_db)):
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authentication scheme")
    
    token = authorization.split(" ")[1]
    payload = utils.decode_token(token)
    
    if payload is None or payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    user_email = payload.get("sub")
    if user_email is None:
        raise HTTPException(status_code=401, detail="Invalid token payload")
        
    result = await db.execute(select(models.User).where(models.User.email == user_email))
    user = result.scalars().first()
    
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user

auth_router = APIRouter(prefix="/api/auth", tags=["auth"])

@auth_router.post("/register", response_model=schemas.RegisterResponse, status_code=201)
async def register(user_data: schemas.UserCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(models.User).where(models.User.email == user_data.email))
    existing_user = result.scalars().first()
    if existing_user:
        raise HTTPException(status_code=409, detail="Email already registered")

    code = generate_verification_code()
    
    hashed_pw = utils.get_password_hash(user_data.password)
    new_user = models.User(
        email=user_data.email, 
        password_hash=hashed_pw, 
        name=user_data.name,
        verification_code=code,
        is_active=False
    )
    db.add(new_user)
    await db.commit()

    try:
        await utils.send_email(
            user_data.email,
            "Verification Code",
            f"Your verification code is: {code}"
        )
    except Exception as e:
        print(f"Failed to send email: {e}")

    return {
        "message": "User registered successfully. Check your email for verification code.",
        "email": user_data.email
    }

@auth_router.post("/verify", response_model=schemas.AuthResponse)
async def verify_email(req: schemas.VerifyRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(models.User).where(models.User.email == req.email))
    user = result.scalars().first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.is_active:
         raise HTTPException(status_code=400, detail="User already active")

    if user.verification_code != req.code:
        raise HTTPException(status_code=400, detail="Invalid verification code")

    user.is_active = True
    user.verification_code = None
    
    access_token = utils.create_access_token({"sub": user.email})
    refresh_token = utils.create_refresh_token({"sub": user.email})

    db_refresh = models.RefreshToken(
        token=utils.hash_refresh_token(refresh_token),
        user_id=user.id,
        expires_at=datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    )
    db.add(db_refresh)
    
    await db.commit()
    await db.refresh(user)

    return {
        "user": user,
        "tokens": {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        }
    }

@auth_router.post("/login", response_model=schemas.AuthResponse)
async def login(creds: schemas.LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(models.User).where(models.User.email == creds.email))
    user = result.scalars().first()

    if not user or not utils.verify_password(creds.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account not activated. Please verify your email.")

    access_token = utils.create_access_token({"sub": user.email})
    refresh_token = utils.create_refresh_token({"sub": user.email})

    db_refresh = models.RefreshToken(
        token=utils.hash_refresh_token(refresh_token),
        user_id=user.id,
        expires_at=datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    )
    db.add(db_refresh)
    await db.commit()

    return {
        "user": user,
        "tokens": {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        }
    }

@auth_router.get("/me", response_model=schemas.UserResponse)
async def read_users_me(current_user: models.User = Depends(get_current_user)):
    return current_user

@auth_router.post("/refresh", response_model=schemas.TokenData)
async def refresh_token(request: schemas.RefreshRequest, db: AsyncSession = Depends(get_db)):
    hashed_token = utils.hash_refresh_token(request.refresh_token)
    result = await db.execute(
        select(models.RefreshToken)
        .options(selectinload(models.RefreshToken.user))
        .where(models.RefreshToken.token == hashed_token)
    )
    stored_token = result.scalars().first()

    if not stored_token:
        legacy = await db.execute(
            select(models.RefreshToken)
            .options(selectinload(models.RefreshToken.user))
            .where(models.RefreshToken.token == request.refresh_token)
        )
        stored_token = legacy.scalars().first()

    if not stored_token or stored_token.revoked:
        raise HTTPException(status_code=401, detail="Refresh token revoked or invalid")
    
    if stored_token.expires_at < datetime.utcnow():
        raise HTTPException(status_code=401, detail="Refresh token expired")

    payload = utils.decode_token(request.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token")

    token_sub = payload.get("sub")
    user = stored_token.user
    if not user:
        user_result = await db.execute(select(models.User).where(models.User.id == stored_token.user_id))
        user = user_result.scalars().first()

    if not user or user.email != token_sub:
        raise HTTPException(status_code=401, detail="Token subject mismatch")

    stored_token.revoked = True
    
    new_access = utils.create_access_token({"sub": payload["sub"]})
    new_refresh = utils.create_refresh_token({"sub": payload["sub"]})
    
    new_db_token = models.RefreshToken(
        token=utils.hash_refresh_token(new_refresh),
        user_id=stored_token.user_id,
        expires_at=datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    )
    db.add(new_db_token)
    await db.commit()

    return {
        "access_token": new_access,
        "refresh_token": new_refresh,
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    }

@auth_router.post("/logout")
async def logout(request: schemas.LogoutRequest, db: AsyncSession = Depends(get_db)):
    hashed_token = utils.hash_refresh_token(request.refresh_token)
    result = await db.execute(select(models.RefreshToken).where(models.RefreshToken.token == hashed_token))
    stored_token = result.scalars().first()
    if not stored_token:
        legacy = await db.execute(select(models.RefreshToken).where(models.RefreshToken.token == request.refresh_token))
        stored_token = legacy.scalars().first()
    
    if stored_token:
        stored_token.revoked = True
        await db.commit()
    
    return {"message": "Logged out"}

@auth_router.post("/forgot-password")
async def forgot_password(request: schemas.ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(models.User).where(models.User.email == request.email))
    user = result.scalars().first()
    
    if user:
        reset_token = utils.create_access_token({"sub": user.email}, token_type="reset")
        try:
            await utils.send_email(
                user.email, 
                "Password Reset Request", 
                f"Your reset token is: {reset_token}"
            )
        except Exception as e:
            print(f"Email failed: {e}")
            
    return {"message": "If this email exists, a reset link has been sent"}

@auth_router.post("/reset-password")
async def reset_password(request: schemas.ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    payload = utils.decode_token(request.token)
    if not payload:
        raise HTTPException(status_code=400, detail="Invalid token")
    
    if payload.get("type") != "reset":
        raise HTTPException(status_code=400, detail="Invalid token type")
    
    email = payload.get("sub")
    result = await db.execute(select(models.User).where(models.User.email == email))
    user = result.scalars().first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    user.password_hash = utils.get_password_hash(request.new_password)
    await db.commit()
    
    return {"message": "Password has been reset"}

@auth_router.post("/change-password")
async def change_password(request: schemas.ChangePasswordRequest, 
                          current_user: models.User = Depends(get_current_user), 
                          db: AsyncSession = Depends(get_db)):
    
    if not utils.verify_password(request.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Incorrect current password")
        
    current_user.password_hash = utils.get_password_hash(request.new_password)
    await db.commit()
    
    return {"message": "Password has been changed"}

app.include_router(auth_router)
