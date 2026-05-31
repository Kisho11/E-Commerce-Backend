import os
import secrets
from fastapi import FastAPI
from fastapi import Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect, text
from sqlalchemy.exc import OperationalError
from app.config import settings
from app.database import engine, Base

# Import all models so Base.metadata is populated before create_all
import app.models  # noqa: F401

from app.routers import auth, users, categories, products, cart, orders, reviews, payments, admin, inventory, tasks, manager

# Create all tables on startup
Base.metadata.create_all(bind=engine)


def ensure_runtime_schema_updates():
    inspector = inspect(engine)
    table_names = inspector.get_table_names()

    if "users" in table_names:
        user_columns = {column["name"] for column in inspector.get_columns("users")}
        if "token_version" not in user_columns:
            try:
                with engine.begin() as connection:
                    connection.execute(text("ALTER TABLE users ADD COLUMN token_version INTEGER NOT NULL DEFAULT 0"))
            except OperationalError as error:
                if "duplicate column name" not in str(error).lower():
                    raise
        if "failed_login_attempts" not in user_columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE users ADD COLUMN failed_login_attempts INTEGER NOT NULL DEFAULT 0"))
        if "lockout_until" not in user_columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE users ADD COLUMN lockout_until TIMESTAMP NULL"))
        if "last_login_at" not in user_columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE users ADD COLUMN last_login_at TIMESTAMP NULL"))
        if "is_email_verified" not in user_columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE users ADD COLUMN is_email_verified BOOLEAN NOT NULL DEFAULT FALSE"))
        if "must_reset_password" not in user_columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE users ADD COLUMN must_reset_password BOOLEAN NOT NULL DEFAULT FALSE"))

    if "admin_audit_logs" in table_names:
        with engine.begin() as connection:
            row = connection.execute(text(
                "SELECT confdeltype FROM pg_constraint "
                "WHERE conname = 'admin_audit_logs_target_user_id_fkey'"
            )).fetchone()
            if row and row[0] != 'n':
                connection.execute(text(
                    "ALTER TABLE admin_audit_logs DROP CONSTRAINT admin_audit_logs_target_user_id_fkey"
                ))
                connection.execute(text(
                    "ALTER TABLE admin_audit_logs ADD CONSTRAINT admin_audit_logs_target_user_id_fkey "
                    "FOREIGN KEY (target_user_id) REFERENCES users(id) ON DELETE SET NULL"
                ))

    if "products" not in table_names:
        return

    product_columns = {column["name"] for column in inspector.get_columns("products")}
    if "additional_information" not in product_columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE products ADD COLUMN additional_information JSON"))


ensure_runtime_schema_updates()

app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    description="Backend API for a furniture e-commerce store (shelves, cupboards, shop interiors, etc.)",
    docs_url="/docs" if settings.ENABLE_DOCS else None,
    redoc_url="/redoc" if settings.ENABLE_DOCS else None,
    openapi_url="/openapi.json" if settings.ENABLE_DOCS else None,
)

app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.TRUSTED_HOSTS or ["localhost"])

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

CSRF_EXEMPT_PATHS = {
    "/",
    "/health",
    "/api/v1/auth/login",
    "/api/v1/auth/register",
    "/api/v1/auth/forgot-password",
    "/api/v1/auth/reset-password",
    "/api/v1/payments/webhook",
}


@app.middleware("http")
async def enforce_csrf(request: Request, call_next):
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and request.url.path not in CSRF_EXEMPT_PATHS:
        authorization = request.headers.get("Authorization", "")
        using_bearer_token = authorization.lower().startswith("bearer ")
        has_auth_cookie = bool(
            request.cookies.get(settings.ACCESS_TOKEN_COOKIE_NAME)
            or request.cookies.get(settings.REFRESH_TOKEN_COOKIE_NAME)
        )
        if has_auth_cookie and not using_bearer_token:
            csrf_cookie = request.cookies.get(settings.CSRF_COOKIE_NAME)
            csrf_header = request.headers.get(settings.CSRF_HEADER_NAME)
            if not csrf_cookie or not csrf_header or not secrets.compare_digest(csrf_cookie, csrf_header):
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={"detail": "CSRF validation failed"},
                )
    return await call_next(request)


@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Cache-Control"] = "no-store"
    if request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response

# Serve uploaded files as static assets
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")

# Register routers
API = "/api/v1"
app.include_router(auth.router,       prefix=API)
app.include_router(users.router,      prefix=API)
app.include_router(categories.router, prefix=API)
app.include_router(products.router,   prefix=API)
app.include_router(cart.router,       prefix=API)
app.include_router(orders.router,     prefix=API)
app.include_router(reviews.router,    prefix=API)
app.include_router(payments.router,   prefix=API)
app.include_router(admin.router,      prefix=API)
app.include_router(inventory.router,  prefix=API)
app.include_router(tasks.router,      prefix=API)
app.include_router(manager.router,    prefix=API)


@app.get("/", tags=["Root"])
def root():
    payload = {"message": "Furniture Store API"}
    if settings.ENABLE_DOCS:
        payload["docs"] = "/docs"
    return JSONResponse(payload)


@app.get("/health", tags=["Root"])
def health():
    return {"status": "healthy"}
