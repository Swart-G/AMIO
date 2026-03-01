from fastapi import FastAPI, Depends, HTTPException, status, Header, APIRouter, Query, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode, quote_plus
from urllib.request import Request as UrlRequest, urlopen
from urllib.error import HTTPError, URLError
import asyncio
import contextlib
import json
import logging
import random
import re
import string

from database import engine, Base, get_db
import models
import schemas
import utils
from config import settings
from sqlalchemy.orm import selectinload

logger = logging.getLogger("auth_service")

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
EMAIL_VERIFY_LINK_EXPIRE_HOURS = 24
EMAIL_CHANGE_LINK_EXPIRE_MINUTES = 60


def _build_public_url(path: str, **params: str) -> str:
    base = settings.APP_PUBLIC_URL.rstrip("/")
    query = urlencode({k: v for k, v in params.items() if v is not None})
    return f"{base}{path}{('?' + query) if query else ''}"


def _email_button_html(title: str, button_label: str, url: str, note: str | None = None) -> str:
    note_html = f"<p style='color:#475467;font-size:14px;margin:12px 0 0;'>{note}</p>" if note else ""
    return f"""
<html>
  <body style="margin:0;padding:24px;background:#f4f7fb;font-family:Arial,sans-serif;color:#101828;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
      <tr>
        <td align="center">
          <table role="presentation" width="100%" style="max-width:560px;background:#ffffff;border-radius:16px;padding:28px;">
            <tr>
              <td>
                <h1 style="margin:0 0 12px;font-size:22px;color:#111827;">{title}</h1>
                <p style="margin:0 0 18px;color:#475467;font-size:14px;line-height:1.5;">
                  Нажмите кнопку ниже, чтобы продолжить.
                </p>
                <p style="margin:0 0 16px;">
                  <a href="{url}" style="display:inline-block;background:#2563eb;color:#ffffff;text-decoration:none;padding:12px 16px;border-radius:10px;font-weight:600;">
                    {button_label}
                  </a>
                </p>
                <p style="margin:0;color:#667085;font-size:12px;line-height:1.5;word-break:break-all;">
                  Если кнопка не работает, откройте ссылку вручную: {url}
                </p>
                {note_html}
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>
""".strip()


async def _revoke_user_refresh_tokens(db: AsyncSession, user_id: int):
    result = await db.execute(select(models.RefreshToken).where(models.RefreshToken.user_id == user_id))
    tokens = result.scalars().all()
    for token in tokens:
        token.revoked = True


async def _issue_auth_response(db: AsyncSession, user: models.User, revoke_existing_refresh: bool = False):
    if revoke_existing_refresh:
        await _revoke_user_refresh_tokens(db, user.id)

    access_token = utils.create_access_token({"sub": user.email})
    refresh_token = utils.create_refresh_token({"sub": user.email})

    db_refresh = models.RefreshToken(
        token=utils.hash_refresh_token(refresh_token),
        user_id=user.id,
        expires_at=datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )
    db.add(db_refresh)
    await db.commit()
    await db.refresh(user)

    return {
        "user": user,
        "tokens": {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        },
    }


def _create_registration_verify_token(user: models.User) -> str:
    return utils.create_access_token(
        {"uid": user.id, "email": user.email},
        token_type="email_verify",
        expires_delta=timedelta(hours=EMAIL_VERIFY_LINK_EXPIRE_HOURS),
    )


def _create_change_email_token(user: models.User, new_email: str) -> str:
    return utils.create_access_token(
        {"uid": user.id, "current_email": user.email, "new_email": new_email},
        token_type="email_change",
        expires_delta=timedelta(minutes=EMAIL_CHANGE_LINK_EXPIRE_MINUTES),
    )


async def _send_registration_verification_email(user: models.User):
    token = _create_registration_verify_token(user)
    url = _build_public_url("/auth/verify-email", token=token)
    subject = "Подтверждение регистрации в AMIO"
    body = (
        "Подтвердите регистрацию в AMIO по ссылке:\n"
        f"{url}\n\n"
        f"Ссылка действует {EMAIL_VERIFY_LINK_EXPIRE_HOURS} часов."
    )
    body_html = _email_button_html(
        "Подтверждение регистрации в AMIO",
        "Подтвердить регистрацию",
        url,
        note=f"Ссылка действует {EMAIL_VERIFY_LINK_EXPIRE_HOURS} часов.",
    )
    await utils.send_email(user.email, subject, body, body_html=body_html)


async def _send_change_email_confirmation_email(target_email: str, user: models.User):
    token = _create_change_email_token(user, target_email)
    url = _build_public_url("/auth/change-email", token=token)
    subject = "Подтверждение смены email в AMIO"
    body = (
        "Подтвердите смену email в AMIO по ссылке:\n"
        f"{url}\n\n"
        f"Новый email: {target_email}\n"
        f"Ссылка действует {EMAIL_CHANGE_LINK_EXPIRE_MINUTES} минут."
    )
    body_html = _email_button_html(
        "Подтверждение смены email в AMIO",
        "Подтвердить новый email",
        url,
        note=f"Новый email: {target_email}. Ссылка действует {EMAIL_CHANGE_LINK_EXPIRE_MINUTES} минут.",
    )
    await utils.send_email(target_email, subject, body, body_html=body_html)

MARKETPLACE_ALIASES = {
    "wildberries": "wb",
    "wb": "wb",
    "ozon": "ozon",
    "yandex_market": "ym",
    "yandexmarket": "ym",
    "ymarket": "ym",
    "ym": "ym",
    "yandex": "ym",
}
ALLOWED_STATUSES = {"ok", "unavailable", "parse_error", "network_error", "unsupported_url"}


def utcnow() -> datetime:
    return datetime.utcnow()


def floor_hour_utc(dt: Optional[datetime] = None) -> datetime:
    value = dt or utcnow()
    return value.replace(minute=0, second=0, microsecond=0)


def floor_day_utc(dt: Optional[datetime] = None) -> datetime:
    value = dt or utcnow()
    return value.replace(hour=0, minute=0, second=0, microsecond=0)


def normalize_marketplace(value: str) -> str:
    key = (value or "").strip().lower()
    normalized = MARKETPLACE_ALIASES.get(key)
    if not normalized:
        raise HTTPException(status_code=400, detail="Unsupported marketplace")
    return normalized


def _cleanup_url(url: str) -> str:
    if not isinstance(url, str) or not url.strip():
        raise HTTPException(status_code=400, detail="Invalid product URL")
    return url.strip()


def canonicalize_product_url(url: str, marketplace: str) -> str:
    raw = _cleanup_url(url)
    parts = urlsplit(raw)
    scheme = parts.scheme or "https"
    netloc = parts.netloc.lower().strip()
    path = (parts.path or "/").rstrip("/") or "/"

    if marketplace == "wb":
        match = re.search(r"/catalog/(\d+)/detail\.aspx", path, flags=re.IGNORECASE)
        if not match:
            match = re.search(r"/catalog/(\d+)", path, flags=re.IGNORECASE)
        if match:
            nm_id = match.group(1)
            return f"https://www.wildberries.ru/catalog/{nm_id}/detail.aspx"
        return urlunsplit(("https", netloc or "www.wildberries.ru", path, "", ""))

    if marketplace == "ozon":
        query_pairs = [(k, v) for (k, v) in parse_qsl(parts.query, keep_blank_values=False) if k.lower() in {"asb", "at"}]
        query = urlencode(query_pairs) if query_pairs else ""
        return urlunsplit(("https", netloc or "www.ozon.ru", path, query, ""))

    if marketplace == "ym":
        query_pairs = [
            (k, v)
            for (k, v) in parse_qsl(parts.query, keep_blank_values=False)
            if k.lower() in {"sku", "nid", "hid"}
        ]
        query = urlencode(query_pairs) if query_pairs else ""
        return urlunsplit(("https", netloc or "market.yandex.ru", path, query, ""))

    return urlunsplit((scheme, netloc, path, parts.query, ""))


def parse_price_to_int(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        ivalue = int(round(float(value)))
        return ivalue if ivalue > 0 else None
    text = str(value).strip()
    if not text:
        return None
    digits = re.findall(r"\d+", text.replace("\xa0", " "))
    if not digits:
        return None
    try:
        return int("".join(digits))
    except ValueError:
        return None


def _do_http_json_post(url: str, payload: Dict[str, Any], timeout: int) -> Dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    req = UrlRequest(
        url,
        data=data,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=timeout) as response:
        raw = response.read().decode("utf-8", errors="ignore")
    return json.loads(raw or "{}")


def _do_http_json_get(url: str, timeout: int) -> Dict[str, Any]:
    req = UrlRequest(
        url,
        headers={"Accept": "application/json"},
        method="GET",
    )
    with urlopen(req, timeout=timeout) as response:
        raw = response.read().decode("utf-8", errors="ignore")
    return json.loads(raw or "{}")


async def fetch_marketplace_price_exact(marketplace: str, url: str) -> Dict[str, Any]:
    endpoint = f"{settings.MARKETPLACE_SERVICE_URL.rstrip('/')}/api/product-price"
    payload = {"marketplace": marketplace, "url": url}
    try:
        data = await asyncio.to_thread(
            _do_http_json_post,
            endpoint,
            payload,
            int(settings.FAVORITES_MARKETPLACE_TIMEOUT_SECONDS),
        )
    except HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", errors="ignore")
        except Exception:
            body = ""
        logger.warning("Marketplace HTTP error %s for exact price: %s", exc.code, body[:300])
        raise HTTPException(status_code=502, detail="Marketplace exact price request failed")
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        logger.warning("Marketplace exact price error: %s", exc)
        raise HTTPException(status_code=502, detail="Marketplace exact price request failed")

    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail="Invalid marketplace response")
    return data


async def fetch_marketplace_search(query: str, limit: int = 24) -> Dict[str, Any]:
    endpoint = (
        f"{settings.MARKETPLACE_SERVICE_URL.rstrip('/')}/api/products"
        f"?q={quote_plus((query or '').strip())}&limit={max(1, min(int(limit), 50))}&offset=0"
    )
    try:
        data = await asyncio.to_thread(
            _do_http_json_get,
            endpoint,
            int(settings.FAVORITES_MARKETPLACE_TIMEOUT_SECONDS),
        )
    except HTTPError as exc:
        logger.warning("Marketplace search HTTP error %s", exc.code)
        raise HTTPException(status_code=502, detail="Marketplace search request failed")
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        logger.warning("Marketplace search error: %s", exc)
        raise HTTPException(status_code=502, detail="Marketplace search request failed")

    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail="Invalid marketplace search response")
    return data


def _normalize_name_for_match(value: Optional[str]) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip().casefold())
    return re.sub(r"[^\wа-яё]+", " ", text, flags=re.IGNORECASE).strip()


def _search_match_score(target_marketplace: str, target_url: str, target_name: str, item: Dict[str, Any]) -> int:
    try:
        item_market = normalize_marketplace(str(item.get("marketplace") or ""))
    except HTTPException:
        return -1
    if item_market != target_marketplace:
        return -1

    item_url = str(item.get("url") or item.get("product_url") or "").strip()
    if not item_url:
        return -1
    try:
        item_canonical = canonicalize_product_url(item_url, item_market)
    except Exception:
        item_canonical = item_url

    score = 0
    if item_canonical == target_url:
        score += 100

    item_name = _normalize_name_for_match(item.get("name") or item.get("title"))
    if target_name and item_name:
        if item_name == target_name:
            score += 40
        elif target_name in item_name or item_name in target_name:
            score += 20

        target_tokens = set(target_name.split())
        item_tokens = set(item_name.split())
        if target_tokens and item_tokens:
            overlap = len(target_tokens & item_tokens)
            score += min(overlap, 10)

    return score


def _status_from_result(data: Optional[Dict[str, Any]]) -> str:
    status_value = str((data or {}).get("status") or "").strip().lower() or "parse_error"
    return status_value if status_value in ALLOWED_STATUSES else "parse_error"


async def fetch_marketplace_price_with_fallback(
    marketplace: str,
    url: str,
    product_name: Optional[str] = None,
) -> Dict[str, Any]:
    exact_result: Dict[str, Any]
    try:
        exact_result = await fetch_marketplace_price_exact(marketplace, url)
    except HTTPException:
        exact_result = {
            "marketplace": marketplace,
            "url": url,
            "canonical_url": canonicalize_product_url(url, marketplace),
            "name": product_name,
            "price_amount_rub": None,
            "price_text": None,
            "status": "network_error",
        }

    exact_status = _status_from_result(exact_result)
    if exact_status == "ok":
        return exact_result

    search_query = str(product_name or exact_result.get("name") or "").strip()
    if not search_query:
        return exact_result

    try:
        search_data = await fetch_marketplace_search(search_query, limit=24)
    except HTTPException:
        return exact_result

    items = search_data.get("items")
    if not isinstance(items, list) or not items:
        return exact_result

    try:
        target_canonical = canonicalize_product_url(url, marketplace)
    except Exception:
        target_canonical = url
    target_name = _normalize_name_for_match(search_query)

    best_item: Optional[Dict[str, Any]] = None
    best_score = -1
    for item in items:
        if not isinstance(item, dict):
            continue
        score = _search_match_score(marketplace, target_canonical, target_name, item)
        if score > best_score:
            best_score = score
            best_item = item

    if not best_item or best_score < 20:
        return exact_result

    item_url = str(best_item.get("url") or best_item.get("product_url") or url).strip() or url
    try:
        canonical_url = canonicalize_product_url(item_url, marketplace)
    except Exception:
        canonical_url = item_url

    price_text = best_item.get("price")
    if price_text is not None:
        price_text = str(price_text)
    price_amount = parse_price_to_int(price_text)

    if price_amount is None and not price_text:
        return exact_result

    return {
        "marketplace": marketplace,
        "url": item_url,
        "canonical_url": canonical_url,
        "name": str(best_item.get("name") or best_item.get("title") or search_query).strip() or search_query,
        "price_amount_rub": price_amount,
        "price_text": price_text or (str(price_amount) if price_amount is not None else None),
        "status": "ok",
    }


async def upsert_price_history_snapshot(
    db: AsyncSession,
    favorite_id: int,
    bucket_hour: datetime,
    price_amount_rub: Optional[int],
    price_text: Optional[str],
    snapshot_status: str,
    captured_at: Optional[datetime] = None,
) -> models.FavoritePriceHistory:
    result = await db.execute(
        select(models.FavoritePriceHistory).where(
            models.FavoritePriceHistory.favorite_id == favorite_id,
            models.FavoritePriceHistory.bucket_hour_utc == bucket_hour,
        )
    )
    row = result.scalars().first()
    if not row:
        row = models.FavoritePriceHistory(
            favorite_id=favorite_id,
            bucket_hour_utc=bucket_hour,
        )
        db.add(row)

    row.price_amount_rub = price_amount_rub
    row.price_text = price_text
    row.status = snapshot_status if snapshot_status in ALLOWED_STATUSES else "parse_error"
    row.captured_at = captured_at or utcnow()
    return row


def favorite_to_response_dict(favorite: models.FavoriteProduct) -> Dict[str, Any]:
    return {
        "id": favorite.id,
        "marketplace": favorite.marketplace,
        "product_url_original": favorite.product_url_original,
        "product_url_canonical": favorite.product_url_canonical,
        "product_name": favorite.product_name,
        "img_url": favorite.img_url,
        "last_price_amount_rub": favorite.last_price_amount_rub,
        "last_price_text": favorite.last_price_text,
        "last_success_price_at": favorite.last_success_price_at,
        "last_refresh_attempt_at": favorite.last_refresh_attempt_at,
        "last_refresh_status": favorite.last_refresh_status,
        "last_refresh_error": favorite.last_refresh_error,
        "created_at": favorite.created_at,
        "updated_at": favorite.updated_at,
    }

async def build_favorite_list_item(db: AsyncSession, favorite: models.FavoriteProduct) -> Dict[str, Any]:
    base = favorite_to_response_dict(favorite)
    end_day = floor_day_utc()
    start_day = end_day - timedelta(days=29)
    next_day = end_day + timedelta(days=1)

    rows_result = await db.execute(
        select(models.FavoritePriceHistory).where(
            models.FavoritePriceHistory.favorite_id == favorite.id,
            models.FavoritePriceHistory.bucket_hour_utc >= start_day,
            models.FavoritePriceHistory.bucket_hour_utc < next_day,
        )
    )
    rows = rows_result.scalars().all()
    latest_by_day: Dict[datetime, models.FavoritePriceHistory] = {}
    for row in rows:
        day_bucket = floor_day_utc(row.bucket_hour_utc)
        existing = latest_by_day.get(day_bucket)
        if existing is None or row.bucket_hour_utc > existing.bucket_hour_utc:
            latest_by_day[day_bucket] = row

    sparkline_values: List[Optional[int]] = []
    sparkline_points: List[Dict[str, Any]] = []
    for idx in range(30):
        day_bucket = start_day + timedelta(days=idx)
        row = latest_by_day.get(day_bucket)
        value = row.price_amount_rub if row and row.price_amount_rub is not None else None
        sparkline_values.append(value)
        sparkline_points.append(
            {
                "ts": row.bucket_hour_utc if row else day_bucket,
                "price_amount_rub": value,
                "status": row.status if row else None,
            }
        )

    change_30d_percent: Optional[float] = None
    non_null_window_values = [value for value in sparkline_values if value is not None]
    if len(non_null_window_values) >= 2:
        base_value = non_null_window_values[0]
        latest_value = non_null_window_values[-1]
        if base_value and base_value > 0:
            change_30d_percent = round(((latest_value - base_value) / base_value) * 100, 2)

    base.update(
        {
            "sparkline_30d": sparkline_values,
            "sparkline_points_30d": sparkline_points,
            "change_30d_percent": change_30d_percent,
        }
    )
    return base

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
        await _send_registration_verification_email(new_user)
    except Exception as e:
        print(f"Failed to send email: {e}")

    return {
        "message": "User registered successfully. Check your email for a confirmation link.",
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
    return await _issue_auth_response(db, user)


@auth_router.post("/verify-email-link", response_model=schemas.AuthResponse)
async def verify_email_link(request: schemas.TokenConfirmRequest, db: AsyncSession = Depends(get_db)):
    payload = utils.decode_token(request.token)
    if not payload:
        raise HTTPException(status_code=400, detail="Invalid or expired token")
    if payload.get("type") != "email_verify":
        raise HTTPException(status_code=400, detail="Invalid token type")

    user_id = payload.get("uid")
    email = payload.get("email")
    if not user_id or not email:
        raise HTTPException(status_code=400, detail="Invalid token payload")

    result = await db.execute(select(models.User).where(models.User.id == user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.email != email:
        raise HTTPException(status_code=400, detail="Token subject mismatch")

    if not user.is_active:
        user.is_active = True
        user.verification_code = None

    return await _issue_auth_response(db, user)


@auth_router.post("/resend-verification-link", response_model=schemas.MessageResponse)
async def resend_verification_link(request: schemas.ResendVerificationRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(models.User).where(models.User.email == request.email))
    user = result.scalars().first()
    if user and not user.is_active:
        try:
            await _send_registration_verification_email(user)
        except Exception as e:
            print(f"Failed to resend verification email: {e}")
    return {"message": "If this account exists and is not verified, a confirmation link has been sent"}

@auth_router.post("/login", response_model=schemas.AuthResponse)
async def login(creds: schemas.LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(models.User).where(models.User.email == creds.email))
    user = result.scalars().first()

    if not user or not utils.verify_password(creds.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account not activated. Please verify your email.")
    return await _issue_auth_response(db, user)

@auth_router.get("/me", response_model=schemas.UserResponse)
async def read_users_me(current_user: models.User = Depends(get_current_user)):
    return current_user


@auth_router.post("/favorites", response_model=schemas.FavoriteResponse, status_code=201)
async def add_favorite(
    payload: schemas.FavoriteCreateRequest,
    current_user: models.User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    marketplace = normalize_marketplace(payload.marketplace)
    original_url = _cleanup_url(payload.url)
    now = utcnow()

    exact_result = await fetch_marketplace_price_with_fallback(
        marketplace,
        original_url,
        product_name=payload.name,
    )
    exact_status = _status_from_result(exact_result)

    canonical_url = str(exact_result.get("canonical_url") or "").strip()
    if not canonical_url:
        canonical_url = canonicalize_product_url(original_url, marketplace)

    exact_marketplace = str(exact_result.get("marketplace") or marketplace).strip().lower()
    if exact_marketplace in MARKETPLACE_ALIASES:
        marketplace = MARKETPLACE_ALIASES[exact_marketplace]

    price_amount = exact_result.get("price_amount_rub")
    if price_amount is None:
        price_amount = parse_price_to_int(exact_result.get("price_text"))
    if price_amount is None:
        price_amount = parse_price_to_int(payload.price)
    else:
        try:
            price_amount = int(price_amount)
        except Exception:
            price_amount = parse_price_to_int(price_amount)

    price_text = exact_result.get("price_text")
    if price_text is not None:
        price_text = str(price_text)
    if not price_text and price_amount is not None:
        price_text = str(price_amount)
    if not price_text and payload.price:
        price_text = payload.price

    name = str(exact_result.get("name") or "").strip() or (payload.name or None)
    img_url = payload.img_url

    result = await db.execute(
        select(models.FavoriteProduct).where(
            models.FavoriteProduct.user_id == current_user.id,
            models.FavoriteProduct.marketplace == marketplace,
            models.FavoriteProduct.product_url_canonical == canonical_url,
        )
    )
    favorite = result.scalars().first()
    created = False
    if not favorite:
        favorite = models.FavoriteProduct(
            user_id=current_user.id,
            marketplace=marketplace,
            product_url_original=original_url,
            product_url_canonical=canonical_url,
            created_at=now,
            updated_at=now,
        )
        db.add(favorite)
        created = True

    favorite.product_url_original = original_url
    favorite.product_url_canonical = canonical_url
    favorite.marketplace = marketplace
    favorite.product_name = name or favorite.product_name
    favorite.img_url = img_url or favorite.img_url
    favorite.last_refresh_attempt_at = now
    favorite.last_refresh_status = exact_status
    favorite.last_refresh_error = None if exact_status == "ok" else exact_status
    favorite.next_refresh_at = now + timedelta(hours=1)
    favorite.updated_at = now

    if exact_status == "ok" and price_amount is not None:
        favorite.last_price_amount_rub = price_amount
        favorite.last_price_text = price_text
        favorite.last_success_price_at = now
    else:
        # Keep a visible starting price from the search card even if exact parsing failed.
        if favorite.last_price_amount_rub is None and price_amount is not None:
            favorite.last_price_amount_rub = price_amount
        if (favorite.last_price_text is None or not str(favorite.last_price_text).strip()) and price_text:
            favorite.last_price_text = price_text

    await db.flush()
    if created and favorite.last_price_amount_rub is not None:
        current_bucket = floor_hour_utc(now)
        for idx in range(25):
            bucket = current_bucket - timedelta(hours=(24 - idx))
            await upsert_price_history_snapshot(
                db=db,
                favorite_id=favorite.id,
                bucket_hour=bucket,
                price_amount_rub=favorite.last_price_amount_rub,
                price_text=favorite.last_price_text or price_text,
                snapshot_status=exact_status,
                captured_at=now,
            )
    else:
        await upsert_price_history_snapshot(
            db=db,
            favorite_id=favorite.id,
            bucket_hour=floor_hour_utc(now),
            price_amount_rub=favorite.last_price_amount_rub,
            price_text=favorite.last_price_text or price_text,
            snapshot_status=exact_status,
            captured_at=now,
        )
    await db.commit()
    await db.refresh(favorite)
    return favorite_to_response_dict(favorite)


@auth_router.get("/favorites/keys", response_model=schemas.FavoriteKeysListResponse)
async def get_favorite_keys(
    current_user: models.User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(models.FavoriteProduct).where(
            models.FavoriteProduct.user_id == current_user.id
        )
    )
    rows = result.scalars().all()
    items = [
        {
            "id": row.id,
            "marketplace": row.marketplace,
            "product_url_canonical": row.product_url_canonical,
            "product_url_original": row.product_url_original,
        }
        for row in rows
    ]
    return {"items": items}


@auth_router.get("/favorites", response_model=schemas.FavoriteListResponse)
async def list_favorites(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: models.User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    total_result = await db.execute(
        select(func.count(models.FavoriteProduct.id)).where(
            models.FavoriteProduct.user_id == current_user.id
        )
    )
    total = int(total_result.scalar() or 0)

    if offset >= total:
        return {
            "count": 0,
            "items": [],
            "offset": offset,
            "limit": limit,
            "total": total,
            "has_more": False,
        }

    result = await db.execute(
        select(models.FavoriteProduct).where(
            models.FavoriteProduct.user_id == current_user.id
        ).order_by(models.FavoriteProduct.created_at.desc()).offset(offset).limit(limit)
    )
    favorites = result.scalars().all()

    items: List[Dict[str, Any]] = []
    for favorite in favorites:
        items.append(await build_favorite_list_item(db, favorite))

    return {
        "count": len(items),
        "items": items,
        "offset": offset,
        "limit": limit,
        "total": total,
        "has_more": (offset + len(items)) < total,
    }


@auth_router.post("/favorites/force-update", response_model=schemas.FavoriteForceUpdateResponse)
async def force_update_favorites(
    limit: int = Query(100, ge=1, le=500),
    current_user: models.User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(models.FavoriteProduct).where(
            models.FavoriteProduct.user_id == current_user.id
        ).order_by(models.FavoriteProduct.created_at.desc()).limit(limit)
    )
    favorites = result.scalars().all()

    if not favorites:
        return {"count": 0, "updated": 0, "ok": 0, "failed": 0, "items": []}

    response_items: List[Dict[str, Any]] = []
    ok_count = 0
    failed_count = 0

    for favorite in favorites:
        now = utcnow()
        favorite.last_refresh_attempt_at = now
        try:
            exact = await fetch_marketplace_price_with_fallback(
                favorite.marketplace,
                favorite.product_url_original,
                product_name=favorite.product_name,
            )
            exact_status = _status_from_result(exact)

            canonical = str(exact.get("canonical_url") or "").strip()
            if canonical:
                favorite.product_url_canonical = canonical

            name = str(exact.get("name") or "").strip()
            if name:
                favorite.product_name = name

            price_amount = exact.get("price_amount_rub")
            if price_amount is not None:
                try:
                    price_amount = int(price_amount)
                except Exception:
                    price_amount = parse_price_to_int(price_amount)
            else:
                price_amount = parse_price_to_int(exact.get("price_text"))

            price_text = exact.get("price_text")
            if price_text is not None:
                price_text = str(price_text)

            favorite.last_refresh_status = exact_status
            favorite.last_refresh_error = None if exact_status == "ok" else exact_status

            snapshot_price_amount = favorite.last_price_amount_rub
            snapshot_price_text = favorite.last_price_text or price_text
            if exact_status == "ok" and price_amount is not None:
                favorite.last_price_amount_rub = price_amount
                favorite.last_price_text = price_text or str(price_amount)
                favorite.last_success_price_at = now
                snapshot_price_amount = favorite.last_price_amount_rub
                snapshot_price_text = favorite.last_price_text
                ok_count += 1
            else:
                failed_count += 1

            favorite.next_refresh_at = now + timedelta(hours=1)
            favorite.updated_at = now

            await upsert_price_history_snapshot(
                db=db,
                favorite_id=favorite.id,
                bucket_hour=floor_hour_utc(now),
                price_amount_rub=snapshot_price_amount,
                price_text=snapshot_price_text,
                snapshot_status=exact_status,
                captured_at=now,
            )
        except Exception as exc:
            logger.exception("Force update failed for favorite %s: %s", favorite.id, exc)
            favorite.last_refresh_status = "network_error"
            favorite.last_refresh_error = "network_error"
            favorite.last_refresh_attempt_at = now
            favorite.next_refresh_at = now + timedelta(hours=1)
            favorite.updated_at = now
            await upsert_price_history_snapshot(
                db=db,
                favorite_id=favorite.id,
                bucket_hour=floor_hour_utc(now),
                price_amount_rub=favorite.last_price_amount_rub,
                price_text=favorite.last_price_text,
                snapshot_status="network_error",
                captured_at=now,
            )
            failed_count += 1

        response_items.append(
            {
                "id": favorite.id,
                "marketplace": favorite.marketplace,
                "product_name": favorite.product_name,
                "status": favorite.last_refresh_status,
                "last_price_amount_rub": favorite.last_price_amount_rub,
                "last_price_text": favorite.last_price_text,
                "last_success_price_at": favorite.last_success_price_at,
                "last_refresh_attempt_at": favorite.last_refresh_attempt_at,
                "error": favorite.last_refresh_error,
            }
        )

    await db.commit()

    return {
        "count": len(response_items),
        "updated": len(response_items),
        "ok": ok_count,
        "failed": failed_count,
        "items": response_items,
    }


@auth_router.delete("/favorites/{favorite_id}", response_model=schemas.FavoriteDeleteResponse)
async def delete_favorite(
    favorite_id: int,
    current_user: models.User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(models.FavoriteProduct).where(
            models.FavoriteProduct.id == favorite_id,
            models.FavoriteProduct.user_id == current_user.id,
        )
    )
    favorite = result.scalars().first()
    if not favorite:
        raise HTTPException(status_code=404, detail="Favorite not found")

    await db.delete(favorite)
    await db.commit()
    return {"message": "Favorite deleted"}

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

@auth_router.post("/change-email/request", response_model=schemas.MessageResponse)
async def request_change_email(
    request: schemas.ChangeEmailRequest,
    current_user: models.User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    new_email = request.new_email.strip().lower()
    current_email = (current_user.email or "").strip().lower()

    if new_email == current_email:
        raise HTTPException(status_code=400, detail="New email must be different")
    if not utils.verify_password(request.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Incorrect current password")

    result = await db.execute(select(models.User).where(models.User.email == new_email))
    existing_user = result.scalars().first()
    if existing_user:
        raise HTTPException(status_code=409, detail="Email already registered")

    try:
        await _send_change_email_confirmation_email(new_email, current_user)
    except Exception as e:
        print(f"Failed to send change-email confirmation: {e}")

    return {"message": "Confirmation link sent to new email"}


@auth_router.post("/change-email/confirm", response_model=schemas.AuthResponse)
async def confirm_change_email(request: schemas.TokenConfirmRequest, db: AsyncSession = Depends(get_db)):
    payload = utils.decode_token(request.token)
    if not payload:
        raise HTTPException(status_code=400, detail="Invalid or expired token")
    if payload.get("type") != "email_change":
        raise HTTPException(status_code=400, detail="Invalid token type")

    user_id = payload.get("uid")
    current_email = str(payload.get("current_email") or "").strip().lower()
    new_email = str(payload.get("new_email") or "").strip().lower()
    if not user_id or not current_email or not new_email:
        raise HTTPException(status_code=400, detail="Invalid token payload")

    result = await db.execute(select(models.User).where(models.User.id == user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user_email_normalized = (user.email or "").strip().lower()
    if user_email_normalized != current_email:
        if user_email_normalized == new_email:
            return await _issue_auth_response(db, user, revoke_existing_refresh=True)
        raise HTTPException(status_code=400, detail="Email change token is no longer valid")

    email_check = await db.execute(select(models.User).where(models.User.email == new_email))
    taken_user = email_check.scalars().first()
    if taken_user and taken_user.id != user.id:
        raise HTTPException(status_code=409, detail="Email already registered")

    user.email = new_email
    return await _issue_auth_response(db, user, revoke_existing_refresh=True)


@auth_router.post("/change-password", response_model=schemas.MessageResponse)
async def change_password(request: schemas.ChangePasswordRequest, 
                          current_user: models.User = Depends(get_current_user), 
                          db: AsyncSession = Depends(get_db)):
    if request.current_password == request.new_password:
        raise HTTPException(status_code=400, detail="New password must be different")
    if not utils.verify_password(request.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Incorrect current password")

    current_user.password_hash = utils.get_password_hash(request.new_password)
    await _revoke_user_refresh_tokens(db, current_user.id)
    await db.commit()

    return {"message": "Password has been changed"}


@auth_router.delete("/me", response_model=schemas.MessageResponse)
async def delete_profile(
    request: schemas.DeleteProfileRequest = Body(...),
    current_user: models.User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not utils.verify_password(request.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Incorrect current password")
    if (request.confirmation_text or "").strip().upper() != "DELETE":
        raise HTTPException(status_code=400, detail="Invalid confirmation text")

    await db.execute(delete(models.RefreshToken).where(models.RefreshToken.user_id == current_user.id))
    await db.delete(current_user)
    await db.commit()
    return {"message": "Profile deleted"}

app.include_router(auth_router)
