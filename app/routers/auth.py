import json
import secrets as _secrets
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi import Form
from jose import JWTError
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.config import settings
from app.database import get_db
from app.models.user import User
from app.schemas.user import (
    UserCreate,
    UserResponse,
    Token,
    RefreshTokenRequest,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    PasswordResetResponse,
    SetPasswordRequest,
)
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    cookie_settings,
    csrf_cookie_settings,
    decode_token,
    generate_csrf_token,
)
from app.core.dependencies import get_current_user
from app.core.rate_limit import auth_rate_limiter, get_request_identifier
from app.utils.email import send_verification_email, send_manager_invite_email, send_password_reset_email


class GoogleAuthRequest(BaseModel):
    credential: str


def _verify_google_token(credential: str, client_id: str) -> dict:
    url = f"https://oauth2.googleapis.com/tokeninfo?id_token={urllib.parse.quote(credential)}"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError:
        raise ValueError("Invalid Google token")
    if data.get("aud") != client_id:
        raise ValueError("Token audience mismatch")
    return data

router = APIRouter(prefix="/auth", tags=["Authentication"])
MIN_PASSWORD_LENGTH = 8


class LoginForm:
    def __init__(
        self,
        username: str = Form(...),
        password: str = Form(...),
        scope: str = Form(default=""),
        client_id: Optional[str] = Form(default=None),
        client_secret: Optional[str] = Form(default=None),
    ):
        self.username = username
        self.password = password
        self.scope = scope
        self.client_id = client_id
        self.client_secret = client_secret


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


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(request: Request, user_data: UserCreate, db: Session = Depends(get_db)):
    normalized_email = user_data.email.lower()
    if db.query(User).filter(User.email == normalized_email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        email=normalized_email,
        hashed_password=hash_password(user_data.password),
        full_name=user_data.full_name,
        phone=user_data.phone,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    try:
        token = create_access_token(
            {"sub": str(user.id), "purpose": "email_verification"},
            expires_delta=timedelta(hours=settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS),
        )
        send_verification_email(user.email, user.full_name, token)
    except Exception:
        pass

    return user


@router.post("/google", response_model=Token)
def google_auth(
    response: Response,
    body: GoogleAuthRequest,
    db: Session = Depends(get_db),
):
    if not settings.GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=503, detail="Google authentication is not configured")

    try:
        profile = _verify_google_token(body.credential, settings.GOOGLE_CLIENT_ID)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid Google credential")

    email = profile.get("email", "").lower().strip()
    if not email or not profile.get("email_verified"):
        raise HTTPException(status_code=400, detail="Google account email is missing or unverified")

    user = db.query(User).filter(User.email == email).first()

    if user:
        if not user.is_active:
            raise HTTPException(status_code=400, detail="Account is inactive")
        if not user.is_email_verified:
            user.is_email_verified = True
    else:
        user = User(
            email=email,
            hashed_password=hash_password(_secrets.token_hex(32)),
            full_name=profile.get("name") or email.split("@")[0],
            is_email_verified=True,
        )
        db.add(user)

    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)

    access_token = create_access_token({"sub": str(user.id), "rv": user.token_version})
    refresh_token_val = create_refresh_token({"sub": str(user.id), "rv": user.token_version})
    csrf_token = generate_csrf_token()
    response.set_cookie(value=access_token, **cookie_settings())
    response.set_cookie(value=refresh_token_val, **cookie_settings(refresh=True))
    response.set_cookie(value=csrf_token, **csrf_cookie_settings())

    return {"token_type": "bearer", "user": user}


@router.get("/verify-email", tags=["Authentication"])
def verify_email(token: str, db: Session = Depends(get_db)):
    try:
        payload = decode_token(token)
    except (JWTError, Exception):
        raise HTTPException(status_code=400, detail="Invalid or expired verification link")

    if payload.get("purpose") != "email_verification":
        raise HTTPException(status_code=400, detail="Invalid verification token")

    user = db.query(User).filter(User.id == int(payload.get("sub"))).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.is_email_verified:
        return {"message": "Email already verified", "already_verified": True}

    user.is_email_verified = True
    db.commit()
    return {"message": "Email verified successfully", "already_verified": False}


@router.post("/resend-verification", tags=["Authentication"])
def resend_verification(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    if current_user.is_email_verified:
        raise HTTPException(status_code=400, detail="Email is already verified")

    try:
        token = create_access_token(
            {"sub": str(current_user.id), "purpose": "email_verification"},
            expires_delta=timedelta(hours=settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS),
        )
        send_verification_email(current_user.email, current_user.full_name, token)
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to send verification email")

    return {"message": "Verification email sent"}


@router.get("/manager-activate", response_model=Token)
def manager_activate(token: str, response: Response, db: Session = Depends(get_db)):
    try:
        payload = decode_token(token)
    except (JWTError, Exception):
        raise HTTPException(status_code=400, detail="Invalid or expired activation link")

    if payload.get("purpose") != "manager_invite":
        raise HTTPException(status_code=400, detail="Invalid activation token")

    user = db.query(User).filter(User.id == int(payload.get("sub"))).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=404, detail="Manager account not found or inactive")

    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)

    access_token = create_access_token({"sub": str(user.id), "rv": user.token_version})
    refresh_token_val = create_refresh_token({"sub": str(user.id), "rv": user.token_version})
    csrf_token = generate_csrf_token()
    response.set_cookie(value=access_token, **cookie_settings())
    response.set_cookie(value=refresh_token_val, **cookie_settings(refresh=True))
    response.set_cookie(value=csrf_token, **csrf_cookie_settings())

    return {"token_type": "bearer", "user": user}


@router.post("/set-password", response_model=PasswordResetResponse)
def set_password(
    body: SetPasswordRequest,
    response: Response,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not current_user.must_reset_password:
        raise HTTPException(status_code=400, detail="Password reset is not required for this account")

    current_user.hashed_password = hash_password(body.new_password)
    current_user.must_reset_password = False
    current_user.token_version += 1
    db.commit()

    new_access_token = create_access_token({"sub": str(current_user.id), "rv": current_user.token_version})
    new_refresh_token = create_refresh_token({"sub": str(current_user.id), "rv": current_user.token_version})
    new_csrf_token = generate_csrf_token()
    response.set_cookie(value=new_access_token, **cookie_settings())
    response.set_cookie(value=new_refresh_token, **cookie_settings(refresh=True))
    response.set_cookie(value=new_csrf_token, **csrf_cookie_settings())

    return {"message": "Password updated successfully"}


@router.post("/login", response_model=Token)
def login(
    request: Request,
    response: Response,
    form_data: LoginForm = Depends(),
    db: Session = Depends(get_db),
):
    auth_rate_limiter.check(get_request_identifier(request, f"login:{form_data.username.lower()}"))
    user = db.query(User).filter(User.email == form_data.username.lower()).first()
    if user and user.lockout_until and user.lockout_until > datetime.now(timezone.utc):
        raise HTTPException(status_code=423, detail="Account temporarily locked. Please try again later.")
    if not user or not verify_password(form_data.password, user.hashed_password):
        if user:
            _record_failed_login(user, db)
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Account is inactive")
    _clear_login_failures(user, db)

    access_token = create_access_token({"sub": str(user.id), "rv": user.token_version})
    refresh_token = create_refresh_token({"sub": str(user.id), "rv": user.token_version})
    csrf_token = generate_csrf_token()
    response.set_cookie(value=access_token, **cookie_settings())
    response.set_cookie(value=refresh_token, **cookie_settings(refresh=True))
    response.set_cookie(value=csrf_token, **csrf_cookie_settings())

    return {
        "token_type": "bearer",
        "user": user,
    }


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
        access_token = create_access_token({"sub": str(user.id), "rv": user.token_version})
        next_refresh_token = create_refresh_token({"sub": str(user.id), "rv": user.token_version})
        csrf_token = generate_csrf_token()
        response.set_cookie(value=access_token, **cookie_settings())
        response.set_cookie(value=next_refresh_token, **cookie_settings(refresh=True))
        response.set_cookie(value=csrf_token, **csrf_cookie_settings())
        return {
            "token_type": "bearer",
            "user": user,
        }
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


@router.post("/forgot-password", response_model=PasswordResetResponse)
def forgot_password(
    request: Request,
    body: ForgotPasswordRequest,
    db: Session = Depends(get_db),
):
    auth_rate_limiter.check(get_request_identifier(request, f"forgot-password:{body.email.lower()}"))
    user = db.query(User).filter(User.email == body.email.lower()).first()
    if not user or not user.is_active:
        return {
            "message": "If an account exists for this email, a password reset link has been prepared.",
        }

    reset_token = create_access_token(
        {"sub": str(user.id), "purpose": "password_reset", "rv": user.token_version},
        expires_delta=timedelta(minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES),
    )
    try:
        send_password_reset_email(user.email, user.full_name, reset_token)
    except Exception:
        pass
    response = {
        "message": "If an account exists for this email, a password reset link has been sent.",
    }
    if settings.EXPOSE_PASSWORD_RESET_TOKEN:
        response["reset_token"] = reset_token
    return response


@router.post("/reset-password", response_model=Token)
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
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired reset token")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired reset token")

    if payload.get("type") != "access" or payload.get("purpose") != "password_reset":
        raise HTTPException(status_code=401, detail="Invalid reset token")

    user = db.query(User).filter(User.id == int(payload.get("sub"))).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=404, detail="User not found or inactive")

    if user.token_version != int(payload.get("rv", -1)):
        raise HTTPException(status_code=401, detail="Invalid or expired reset token")

    user.hashed_password = hash_password(body.new_password)
    user.token_version += 1
    db.commit()
    db.refresh(user)

    new_access_token = create_access_token({"sub": str(user.id), "rv": user.token_version})
    new_refresh_token = create_refresh_token({"sub": str(user.id), "rv": user.token_version})
    new_csrf_token = generate_csrf_token()
    response.set_cookie(value=new_access_token, **cookie_settings())
    response.set_cookie(value=new_refresh_token, **cookie_settings(refresh=True))
    response.set_cookie(value=new_csrf_token, **csrf_cookie_settings())

    return {"token_type": "bearer", "user": user}


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
