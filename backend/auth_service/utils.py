import datetime
import asyncio
import smtplib
import logging
import json
from email.utils import parseaddr
from passlib.context import CryptContext
from jose import jwt, JWTError
from email.message import EmailMessage
import aiosmtplib
from config import settings
import hashlib
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
logger = logging.getLogger("auth_service.email")

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, token_type: str = "access", expires_delta: datetime.timedelta | None = None):
    to_encode = data.copy()
    expire = datetime.datetime.utcnow() + (
        expires_delta if expires_delta is not None else datetime.timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire, "type": token_type})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

def create_refresh_token(data: dict):
    to_encode = data.copy()
    expire = datetime.datetime.utcnow() + datetime.timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

def decode_token(token: str):
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError:
        return None

async def send_email(email_to: str, subject: str, body: str, body_html: str | None = None):
    provider = (settings.EMAIL_PROVIDER or "smtp").strip().lower()
    if provider == "brevo_api":
        await _send_email_via_brevo_api(
            email_to=email_to,
            subject=subject,
            body_text=body,
            body_html=body_html,
        )
        return
    if provider == "resend_api":
        await _send_email_via_resend_api(
            email_to=email_to,
            subject=subject,
            body_text=body,
            body_html=body_html,
        )
        return

    message = EmailMessage()
    message["From"] = settings.EMAILS_FROM_EMAIL
    message["To"] = email_to
    message["Subject"] = subject
    message.set_content(body)
    if body_html:
        message.add_alternative(body_html, subtype="html")
    targets = _build_smtp_targets(settings.SMTP_SERVER, int(settings.SMTP_PORT))
    delays_seconds = [0.8, 2.0, 5.0]
    last_error = None

    for attempt in range(len(delays_seconds) + 1):
        for host, port, use_tls in targets:
            try:
                await _send_email_async_primary(message, host, port, use_tls)
                if attempt > 0 or (host, port) != (settings.SMTP_SERVER, int(settings.SMTP_PORT)):
                    logger.warning(
                        "Email sent after retry/fallback via %s:%s (attempt=%s)",
                        host,
                        port,
                        attempt + 1,
                    )
                return
            except Exception as primary_exc:
                last_error = primary_exc
                logger.warning(
                    "Primary SMTP attempt failed via %s:%s (attempt=%s): %s",
                    host,
                    port,
                    attempt + 1,
                    primary_exc,
                )
                try:
                    await asyncio.to_thread(_send_email_sync_fallback, message, host, port, use_tls)
                    logger.warning(
                        "Email sent via sync SMTP fallback %s:%s (attempt=%s)",
                        host,
                        port,
                        attempt + 1,
                    )
                    return
                except Exception as fallback_exc:
                    last_error = fallback_exc
                    logger.warning(
                        "Sync SMTP fallback failed via %s:%s (attempt=%s): %s",
                        host,
                        port,
                        attempt + 1,
                        fallback_exc,
                    )
        if attempt < len(delays_seconds):
            await asyncio.sleep(delays_seconds[attempt])

    if last_error:
        raise last_error
    raise RuntimeError("SMTP send failed without error details")


async def _send_email_via_brevo_api(email_to: str, subject: str, body_text: str, body_html: str | None = None):
    api_key = (settings.BREVO_API_KEY or "").strip()
    if not api_key:
        raise RuntimeError("BREVO_API_KEY is not configured")

    sender_name, sender_email = parseaddr(settings.EMAILS_FROM_EMAIL or "")
    sender_email = (sender_email or "").strip()
    if not sender_email:
        raise RuntimeError("EMAILS_FROM_EMAIL must contain a valid sender email")

    payload = {
        "sender": {
            "email": sender_email,
            "name": (sender_name or sender_email),
        },
        "to": [{"email": email_to}],
        "subject": subject,
        "textContent": body_text or "",
        "htmlContent": body_html or None,
    }
    if payload["htmlContent"] is None:
        payload.pop("htmlContent", None)

    await asyncio.to_thread(_brevo_send_sync, payload, api_key)


def _brevo_send_sync(payload: dict, api_key: str):
    data = json.dumps(payload).encode("utf-8")
    request = Request(
        settings.BREVO_API_URL,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "api-key": api_key,
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=30) as response:
            _ = response.read()
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Brevo API error HTTP {exc.code}: {raw or exc.reason}") from exc
    except URLError as exc:
        raise RuntimeError(f"Brevo API connection failed: {exc}") from exc


async def _send_email_via_resend_api(email_to: str, subject: str, body_text: str, body_html: str | None = None):
    api_key = (settings.RESEND_API_KEY or "").strip()
    if not api_key:
        raise RuntimeError("RESEND_API_KEY is not configured")

    sender_name, sender_email = parseaddr(settings.EMAILS_FROM_EMAIL or "")
    sender_email = (sender_email or "").strip()
    if not sender_email:
        raise RuntimeError("EMAILS_FROM_EMAIL must contain a valid sender email")

    from_value = f"{sender_name} <{sender_email}>" if sender_name else sender_email
    payload = {
        "from": from_value,
        "to": [email_to],
        "subject": subject,
        "text": body_text or "",
        "html": body_html or None,
    }
    if payload["html"] is None:
        payload.pop("html", None)

    await asyncio.to_thread(_resend_send_sync, payload, api_key)


def _resend_send_sync(payload: dict, api_key: str):
    data = json.dumps(payload).encode("utf-8")
    request = Request(
        settings.RESEND_API_URL,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "AMIO-AuthService/1.0 (+https://amio-shop.ru)",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=30) as response:
            _ = response.read()
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Resend API error HTTP {exc.code}: {raw or exc.reason}") from exc
    except URLError as exc:
        raise RuntimeError(f"Resend API connection failed: {exc}") from exc


def _build_smtp_targets(host: str, port: int):
    targets: list[tuple[str, int, bool]] = []

    def add_target(h: str, p: int):
        use_tls = p == 465
        target = (h, p, use_tls)
        if target not in targets:
            targets.append(target)

    add_target(host, port)

    # Try common submission alternatives for better resilience across providers.
    if port != 587:
        add_target(host, 587)
    if port != 465:
        add_target(host, 465)
    if port != 2525:
        add_target(host, 2525)

    return targets


async def _send_email_async_primary(message: EmailMessage, host: str, port: int, use_tls: bool):
    await aiosmtplib.send(
        message,
        hostname=host,
        port=port,
        username=settings.SMTP_USER,
        password=settings.SMTP_PASSWORD,
        use_tls=use_tls,
        start_tls=(False if use_tls else True),
        timeout=30,
    )


def _send_email_sync_fallback(message: EmailMessage, host: str, port: int, use_tls: bool):
    if use_tls:
        client = smtplib.SMTP_SSL(host, port, timeout=30)
    else:
        client = smtplib.SMTP(host, port, timeout=30)
    try:
        client.ehlo()
        if not use_tls:
            client.starttls()
            client.ehlo()
        client.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        client.send_message(message)
    finally:
        try:
            client.quit()
        except Exception:
            client.close()
