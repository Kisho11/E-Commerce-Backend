import os
import secrets
from urllib.parse import urlparse
from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    APP_NAME: str = "Furniture Store API"
    DEBUG: bool = Field(False, validation_alias=AliasChoices("APP_DEBUG", "DEBUG"))

    # Database
    DATABASE_URL: str = "postgresql://postgres:password@localhost:5432/furniture_store"

    # JWT
    SECRET_KEY: str = "change-this-secret-key-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES: int = 15
    TRUST_PROXY_HEADERS: bool = False
    ACCESS_TOKEN_COOKIE_NAME: str = "access_token"
    REFRESH_TOKEN_COOKIE_NAME: str = "refresh_token"
    CSRF_COOKIE_NAME: str = "csrf_token"
    CSRF_HEADER_NAME: str = "X-CSRF-Token"
    COOKIE_SAMESITE: str = "lax"
    COOKIE_SECURE: bool = False

    # Stripe
    STRIPE_SECRET_KEY: str = "sk_test_placeholder"
    STRIPE_WEBHOOK_SECRET: str = ""
    PAYMENT_CURRENCY: str = "gbp"
    CHECKOUT_TAX_RATE: str = "0.10"

    # OpenAI product-content generation
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4.1-mini"

    # Google OAuth
    GOOGLE_CLIENT_ID: str = ""

    # Email
    GMAIL_USER: str = ""
    GMAIL_APP_PASSWORD: str = ""
    EMAIL_FROM_NAME: str = "Elmshelf Store"
    FRONTEND_URL: str = "http://localhost:3000"
    EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS: int = 24
    MANAGER_INVITE_TOKEN_EXPIRE_HOURS: int = 72
    CART_REMINDER_ENABLED: bool = True
    CART_REMINDER_MIN_CART_AGE_DAYS: int = 30
    CART_REMINDER_INTERVAL_DAYS: int = 30
    CART_REMINDER_CHECK_INTERVAL_HOURS: int = 24

    # File Upload
    UPLOAD_DIR: str = "uploads"
    MAX_FILE_SIZE: int = 5 * 1024 * 1024  # 5MB

    # CORS
    ALLOWED_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    TRUSTED_HOSTS: List[str] = ["localhost", "127.0.0.1", "testserver"]
    ENABLE_DOCS: bool = False
    EXPOSE_PASSWORD_RESET_TOKEN: bool = False
    AUTH_RATE_LIMIT_WINDOW_SECONDS: int = 60
    AUTH_RATE_LIMIT_MAX_REQUESTS: int = 5
    AUTH_LOCKOUT_MAX_ATTEMPTS: int = 5
    AUTH_LOCKOUT_MINUTES: int = 15

    @field_validator("DEBUG", mode="before")
    @classmethod
    def parse_debug(cls, value):
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on", "dev", "development", "local"}:
                return True
            if normalized in {"0", "false", "no", "off", "prod", "production", "release"}:
                return False
        return value

    @field_validator("ALLOWED_ORIGINS", "TRUSTED_HOSTS", mode="before")
    @classmethod
    def parse_list_env(cls, value):
        if isinstance(value, str):
            cleaned = value.strip()
            if not cleaned:
                return []
            if cleaned.startswith("[") and cleaned.endswith("]"):
                import json

                return json.loads(cleaned)
            return [item.strip() for item in cleaned.split(",") if item.strip()]
        return value

    @model_validator(mode="after")
    def validate_security_settings(self):
        raw_debug = os.getenv("APP_DEBUG", os.getenv("DEBUG"))
        if raw_debug is not None:
            self.DEBUG = self.parse_debug(raw_debug)

        if self.DEBUG:
            if not self.ENABLE_DOCS:
                self.ENABLE_DOCS = True

        if not self.SECRET_KEY or self.SECRET_KEY == "replace-with-a-long-random-secret-key":
            if self.DEBUG:
                self.SECRET_KEY = secrets.token_urlsafe(48)

        insecure_default_secret = self.SECRET_KEY == "change-this-secret-key-in-production"
        if insecure_default_secret and not self.DEBUG:
            raise ValueError("SECRET_KEY must be changed before running outside DEBUG mode.")

        if len(self.SECRET_KEY) < 32 and not self.DEBUG:
            raise ValueError("SECRET_KEY must be at least 32 characters long outside DEBUG mode.")

        if not self.DEBUG and not self.STRIPE_WEBHOOK_SECRET:
            raise ValueError("STRIPE_WEBHOOK_SECRET must be configured outside DEBUG mode.")

        parsed_database_url = urlparse(self.DATABASE_URL)
        is_local_sqlite = self.DATABASE_URL.startswith("sqlite")
        is_local_postgres = parsed_database_url.hostname in {"localhost", "127.0.0.1"}
        is_local_database = is_local_sqlite or is_local_postgres

        cookie_secure_explicitly_set = os.getenv("COOKIE_SECURE") is not None
        if not self.DEBUG and not cookie_secure_explicitly_set and not is_local_database:
            self.COOKIE_SECURE = True

        return self

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
