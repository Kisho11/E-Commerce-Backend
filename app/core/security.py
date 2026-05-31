from datetime import datetime, timedelta, timezone
from typing import Optional
import secrets
import bcrypt
from jose import JWTError, jwt
from app.config import settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    if not hashed_password or hashed_password.startswith("!"):
        return False
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except ValueError:
        return False


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    expire = now + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire, "iat": now, "nbf": now, "type": "access"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    expire = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "iat": now, "nbf": now, "type": "refresh"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> dict:
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    if not payload.get("sub"):
        raise JWTError("Missing subject")
    if payload.get("type") not in {"access", "refresh"}:
        raise JWTError("Invalid token type")
    return payload


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def create_email_verification_token(user_id: int) -> str:
    from app.config import settings as _settings
    expires = timedelta(hours=_settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS)
    data = {"sub": str(user_id), "purpose": "email_verification"}
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    to_encode.update({"exp": now + expires, "iat": now, "nbf": now, "type": "access"})
    return jwt.encode(to_encode, _settings.SECRET_KEY, algorithm=_settings.ALGORITHM)


def decode_email_verification_token(token: str) -> dict:
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    if payload.get("purpose") != "email_verification":
        raise JWTError("Invalid token purpose")
    return payload


def cookie_settings(*, refresh: bool = False) -> dict:
    return {
        "key": settings.REFRESH_TOKEN_COOKIE_NAME if refresh else settings.ACCESS_TOKEN_COOKIE_NAME,
        "httponly": True,
        "secure": settings.COOKIE_SECURE,
        "samesite": settings.COOKIE_SAMESITE,
        "path": "/api/v1/auth" if refresh else "/",
    }


def csrf_cookie_settings() -> dict:
    return {
        "key": settings.CSRF_COOKIE_NAME,
        "httponly": False,
        "secure": settings.COOKIE_SECURE,
        "samesite": settings.COOKIE_SAMESITE,
        "path": "/",
    }
