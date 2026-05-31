import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from jose import JWTError
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.config import settings
from app.database import get_db
from app.models.user import User, UserRole
from app.schemas.user import (
    EmailVerifyResponse,
    GoogleAuthRequest,
    PasswordResetResponse,
    RegisterResponse,
    ResendVerificationRequest,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    Token,
    UserCreate,
    UserResponse,
    RefreshTokenRequest,
)
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    create_email_verification_token,
    decode_email_verification_token,
    cookie_settings,
    csrf_cookie_settings,
    decode_token,
    generate_csrf_token,
)
from app.core.dependencies import get_current_user
from app.core.rate_limit import auth_rate_limiter, get_request_identifier
from app.core.captcha import verify_recaptcha
from app.core import email as email_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])
MIN_PASSWORD_LENGTH = 8


def _record_failed_login(user: User, db: Session) -> None:
    user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
    if user.failed_login_attempts >= settings.AUTH_LOCKOUT_MAX_ATTEMPTS:
        user.lockout_until = datetime.now(timezone.utc) + timedelta(minutes=settings.AUTH_LOCKOUT_MINUTES)
        user.failed_login_attempts = 0
    db.commit()


def _clear_login_failures(user: User, db: Session) -> None:
    user.failed_login_attempts = 0
    user.lockout_until = None
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()


def _issue_session(user: User, response: Response) -> dict:
    access_token = create_access_token({"sub": str(user.id), "rv": user.token_version})
    refresh_token = create_refresh_token({"sub": str(user.id), "rv": user.token_version})
    csrf_token = generate_csrf_token()
    response.set_cookie(value=access_token, **cookie_settings())
    response.set_cookie(value=refresh_token, **cookie_settings(refresh=True))
    response.set_cookie(value=csrf_token, **csrf_cookie_settings())
    return {"token_type": "bearer", "user": user}


# ── Register ──────────────────────────────────────────────────────────────────

@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
def register(user_data: UserCreate, db: Session = Depends(get_db)):
    if not verify_recaptcha(user_data.recaptcha_token):
        raise HTTPException(status_code=400, detail="reCAPTCHA verification failed. Please try again.")

    normalized_email = user_data.email.lower()
    if db.query(User).filter(User.email == normalized_email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        email=normalized_email,
        hashed_password=hash_password(user_data.password),
        full_name=user_data.full_name,
        phone=user_data.phone,
        is_email_verified=False,
        auth_provider="password",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_email_verification_token(user.id)
    user.email_verification_token = token
    db.commit()

    try:
        email_service.send_email_verification(user.email, user.full_name, token)
    except Exception:
        logger.exception("Failed to send verification email to %s", user.email)

    return RegisterResponse(
        message="Account created! Please check your email to verify your account before signing in.",
        email_verification_required=True,
    )


# ── Verify Email ──────────────────────────────────────────────────────────────

@router.get("/verify-email", response_model=EmailVerifyResponse)
def verify_email(token: str, db: Session = Depends(get_db)):
    try:
        payload = decode_email_verification_token(token)
    except JWTError:
        raise HTTPException(status_code=400, detail="Invalid or expired verification link.")

    user = db.query(User).filter(User.id == int(payload.get("sub"))).first()
    if not user:
        raise HTTPException(status_code=404, detail="Account not found.")
    if user.is_email_verified:
        return EmailVerifyResponse(message="Email already verified. You can sign in.")
    if user.email_verification_token != token:
        raise HTTPException(status_code=400, detail="Verification link has already been used or expired.")

    user.is_email_verified = True
    user.email_verification_token = None
    db.commit()
    return EmailVerifyResponse(message="Email verified successfully! You can now sign in.")


# ── Resend Verification ───────────────────────────────────────────────────────

@router.post("/resend-verification", response_model=EmailVerifyResponse)
def resend_verification(
    request: Request,
    body: ResendVerificationRequest,
    db: Session = Depends(get_db),
):
    auth_rate_limiter.check(get_request_identifier(request, "resend-verification"))
    _MSG = "If an unverified account exists for this email, a new verification link has been sent."
    user = db.query(User).filter(User.email == body.email.lower()).first()
    if not user or user.is_email_verified or user.auth_provider != "password":
        return EmailVerifyResponse(message=_MSG)

    token = create_email_verification_token(user.id)
    user.email_verification_token = token
    db.commit()

    try:
        email_service.send_email_verification(user.email, user.full_name, token)
    except Exception:
        logger.exception("Failed to resend verification email to %s", user.email)

    return EmailVerifyResponse(message=_MSG)


# ── Login ─────────────────────────────────────────────────────────────────────

@router.post("/login", response_model=Token)
def login(
    request: Request,
    response: Response,
    username: str = Form(...),
    password: str = Form(...),
    recaptcha_token: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    auth_rate_limiter.check(get_request_identifier(request, "login"))

    if not verify_recaptcha(recaptcha_token):
        raise HTTPException(status_code=400, detail="reCAPTCHA verification failed. Please try again.")

    user = db.execute(
        select(User).where(User.email == username.lower()).with_for_update()
    ).scalar_one_or_none()

    if user and user.lockout_until and user.lockout_until > datetime.now(timezone.utc):
        raise HTTPException(status_code=423, detail="Account temporarily locked. Please try again later.")

    if not user or not verify_password(password, user.hashed_password):
        if user:
            _record_failed_login(user, db)
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    if not user.is_active:
        raise HTTPException(status_code=400, detail="Account is inactive")

    if not user.is_email_verified and user.auth_provider == "password":
        raise HTTPException(
            status_code=403,
            detail="Please verify your email address before signing in. Check your inbox for a verification link.",
        )

    _clear_login_failures(user, db)
    return _issue_session(user, response)


# ── Refresh ───────────────────────────────────────────────────────────────────

@router.post("/refresh", response_model=Token)
def refresh_token(
    request: Request,
    response: Response,
    body: Optional[RefreshTokenRequest] = None,
    db: Session = Depends(get_db),
):
    auth_rate_limiter.check(get_request_identifier(request, "refresh"))
    try:
        refresh_token_value = (body.refresh_token if body else None) or request.cookies.get(settings.REFRESH_TOKEN_COOKIE_NAME)
        if not refresh_token_value:
            raise HTTPException(status_code=401, detail="Refresh token required")
        payload = decode_token(refresh_token_value)
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user = db.query(User).filter(User.id == int(payload.get("sub"))).first()
        if not user or not user.is_active:
            raise HTTPException(status_code=401, detail="User not found or inactive")
        if user.token_version != int(payload.get("rv", -1)):
            raise HTTPException(status_code=401, detail="Refresh token revoked")
        return _issue_session(user, response)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


# ── Forgot Password ───────────────────────────────────────────────────────────

@router.post("/forgot-password", response_model=PasswordResetResponse)
def forgot_password(
    request: Request,
    body: ForgotPasswordRequest,
    db: Session = Depends(get_db),
):
    auth_rate_limiter.check(get_request_identifier(request, "forgot-password"))
    _RESET_MSG = "If an account exists for this email, a password reset link has been sent."
    user = db.query(User).filter(User.email == body.email.lower()).first()
    if not user or not user.is_active or user.auth_provider != "password":
        return {"message": _RESET_MSG}

    reset_token = create_access_token(
        {"sub": str(user.id), "purpose": "password_reset"},
        expires_delta=timedelta(minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES),
    )

    try:
        email_service.send_password_reset(user.email, user.full_name, reset_token)
    except Exception:
        logger.exception("Failed to send password reset email to %s", user.email)

    return {"message": _RESET_MSG}


# ── Reset Password ────────────────────────────────────────────────────────────

@router.post("/reset-password", response_model=PasswordResetResponse)
def reset_password(
    request: Request,
    response: Response,
    body: ResetPasswordRequest,
    db: Session = Depends(get_db),
):
    auth_rate_limiter.check(get_request_identifier(request, "reset-password"))
    if len(body.new_password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"Password must be at least {MIN_PASSWORD_LENGTH} characters long",
        )

    try:
        payload = decode_token(body.reset_token)
    except (JWTError, Exception):
        raise HTTPException(status_code=401, detail="Invalid or expired reset token")

    if payload.get("type") != "access" or payload.get("purpose") != "password_reset":
        raise HTTPException(status_code=401, detail="Invalid reset token")

    user = db.query(User).filter(User.id == int(payload.get("sub"))).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=404, detail="User not found or inactive")

    user.hashed_password = hash_password(body.new_password)
    user.token_version += 1
    db.commit()
    response.delete_cookie(settings.ACCESS_TOKEN_COOKIE_NAME, path="/")
    response.delete_cookie(settings.REFRESH_TOKEN_COOKIE_NAME, path="/api/v1/auth")
    response.delete_cookie(settings.CSRF_COOKIE_NAME, path="/")

    return {"message": "Password updated successfully. You can now sign in with your new password."}


# ── Google OAuth ──────────────────────────────────────────────────────────────

@router.post("/google", response_model=Token)
def google_auth(
    body: GoogleAuthRequest,
    response: Response,
    db: Session = Depends(get_db),
):
    if not settings.GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=501, detail="Google authentication is not configured.")

    try:
        res = httpx.get(
            "https://oauth2.googleapis.com/tokeninfo",
            params={"id_token": body.id_token},
            timeout=8.0,
        )
        if res.status_code != 200:
            raise HTTPException(status_code=401, detail="Google token validation failed.")
        profile = res.json()
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Could not verify Google token.")

    if profile.get("aud") != settings.GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=401, detail="Google token audience mismatch.")
    if profile.get("email_verified") not in (True, "true"):
        raise HTTPException(status_code=400, detail="Google account email is not verified.")

    google_email = profile.get("email", "").lower()
    google_name = profile.get("name") or profile.get("given_name") or "Google User"

    user = db.query(User).filter(User.email == google_email).first()

    if user is None:
        if body.mode == "signin":
            raise HTTPException(
                status_code=404,
                detail="No account found for this Google email. Please sign up first.",
            )
        user = User(
            email=google_email,
            hashed_password="!oauth:google",
            full_name=google_name,
            is_email_verified=True,
            auth_provider="google",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        if not user.is_active:
            raise HTTPException(status_code=400, detail="Account is inactive.")
        if not user.is_email_verified:
            user.is_email_verified = True
            db.commit()

    return _issue_session(user, response)


# ── Logout ────────────────────────────────────────────────────────────────────

@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    current_user.token_version += 1
    db.commit()
    response.delete_cookie(settings.ACCESS_TOKEN_COOKIE_NAME, path="/")
    response.delete_cookie(settings.REFRESH_TOKEN_COOKIE_NAME, path="/api/v1/auth")
    response.delete_cookie(settings.CSRF_COOKIE_NAME, path="/")
