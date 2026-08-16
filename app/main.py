import os
import secrets
from fastapi import FastAPI
from fastapi import Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect, text
from sqlalchemy.exc import OperationalError, ProgrammingError
from app.config import settings
from app.database import engine, Base
from app.services.cart_reminders import start_cart_reminder_scheduler, stop_cart_reminder_scheduler

# Import all models so Base.metadata is populated before create_all
import app.models  # noqa: F401

from app.routers import auth, users, categories, products, cart, orders, reviews, payments, admin, inventory, tasks, manager, product_content, analytics, marketing

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

    if "product_images" in table_names:
        image_columns = {column["name"] for column in inspector.get_columns("product_images")}
        if "variant_tag" not in image_columns:
            try:
                with engine.begin() as connection:
                    connection.execute(text("ALTER TABLE product_images ADD COLUMN variant_tag VARCHAR"))
            except (OperationalError, ProgrammingError) as error:
                if "already exists" not in str(error).lower():
                    raise

    if "orders" in table_names:
        order_columns = {column["name"] for column in inspector.get_columns("orders")}
        if "delivery_mode" not in order_columns:
            try:
                with engine.begin() as connection:
                    connection.execute(text("ALTER TABLE orders ADD COLUMN delivery_mode VARCHAR NOT NULL DEFAULT 'ship'"))
            except (OperationalError, ProgrammingError) as error:
                if "already exists" not in str(error).lower():
                    raise
        if "delivery_note" not in order_columns:
            try:
                with engine.begin() as connection:
                    connection.execute(text("ALTER TABLE orders ADD COLUMN delivery_note VARCHAR"))
            except (OperationalError, ProgrammingError) as error:
                if "already exists" not in str(error).lower():
                    raise
        if "checkout_cart_item_ids" not in order_columns:
            try:
                with engine.begin() as connection:
                    connection.execute(text("ALTER TABLE orders ADD COLUMN checkout_cart_item_ids VARCHAR"))
            except (OperationalError, ProgrammingError) as error:
                if "already exists" not in str(error).lower():
                    raise
        if "stock_reserved" not in order_columns:
            try:
                with engine.begin() as connection:
                    connection.execute(text("ALTER TABLE orders ADD COLUMN stock_reserved BOOLEAN NOT NULL DEFAULT FALSE"))
            except (OperationalError, ProgrammingError) as error:
                if "already exists" not in str(error).lower():
                    raise
        order_pricing_columns = {
            "subtotal_amount": "NUMERIC(10, 2)",
            "discount_percentage": "NUMERIC(5, 2) NOT NULL DEFAULT 0",
            "discount_amount": "NUMERIC(10, 2) NOT NULL DEFAULT 0",
            "tax_rate": "NUMERIC(6, 4) NOT NULL DEFAULT 0",
            "tax_amount": "NUMERIC(10, 2) NOT NULL DEFAULT 0",
            "shipping_fee": "NUMERIC(10, 2) NOT NULL DEFAULT 0",
        }
        for column_name, column_type in order_pricing_columns.items():
            if column_name not in order_columns:
                try:
                    with engine.begin() as connection:
                        connection.execute(text(f"ALTER TABLE orders ADD COLUMN {column_name} {column_type}"))
                except (OperationalError, ProgrammingError) as error:
                    if "already exists" not in str(error).lower():
                        raise

    if "marketing_banners" in table_names:
        marketing_columns = {column["name"] for column in inspector.get_columns("marketing_banners")}
        if "global_discount_percentage" not in marketing_columns:
            try:
                with engine.begin() as connection:
                    connection.execute(text("ALTER TABLE marketing_banners ADD COLUMN global_discount_percentage NUMERIC(5, 2) NOT NULL DEFAULT 0"))
            except (OperationalError, ProgrammingError) as error:
                if "already exists" not in str(error).lower():
                    raise

    if "newsletter_subscribers" in table_names:
        subscriber_columns = {column["name"] for column in inspector.get_columns("newsletter_subscribers")}
        if "business_type" not in subscriber_columns:
            try:
                with engine.begin() as connection:
                    connection.execute(text("ALTER TABLE newsletter_subscribers ADD COLUMN business_type VARCHAR NOT NULL DEFAULT 'shopowner'"))
            except (OperationalError, ProgrammingError) as error:
                if "already exists" not in str(error).lower() and "duplicate column" not in str(error).lower():
                    raise

    if "carts" in table_names:
        cart_columns = {column["name"] for column in inspector.get_columns("carts")}
        if "last_reminder_at" not in cart_columns:
            try:
                with engine.begin() as connection:
                    connection.execute(text("ALTER TABLE carts ADD COLUMN last_reminder_at TIMESTAMP WITH TIME ZONE NULL"))
            except (OperationalError, ProgrammingError) as error:
                if "already exists" not in str(error).lower():
                    raise

    if "cart_items" in table_names:
        cart_item_columns = {column["name"] for column in inspector.get_columns("cart_items")}
        if "selected_attributes" not in cart_item_columns:
            try:
                with engine.begin() as connection:
                    connection.execute(text("ALTER TABLE cart_items ADD COLUMN selected_attributes JSON"))
            except (OperationalError, ProgrammingError) as error:
                if "already exists" not in str(error).lower():
                    raise

    if "order_items" in table_names:
        order_item_columns = {column["name"] for column in inspector.get_columns("order_items")}
        if "selected_attributes" not in order_item_columns:
            try:
                with engine.begin() as connection:
                    connection.execute(text("ALTER TABLE order_items ADD COLUMN selected_attributes JSON"))
            except (OperationalError, ProgrammingError) as error:
                if "already exists" not in str(error).lower():
                    raise

    if "products" not in table_names:
        return

    product_columns = {column["name"] for column in inspector.get_columns("products")}
    text_cols = {
        "main_note": "TEXT",
        "key_features": "TEXT",
        "whats_included": "TEXT",
        "important_notes": "TEXT",
        "additional_information": "TEXT",
    }
    for col_name, col_type in text_cols.items():
        if col_name not in product_columns:
            try:
                with engine.begin() as connection:
                    connection.execute(text(f"ALTER TABLE products ADD COLUMN {col_name} {col_type}"))
            except (OperationalError, ProgrammingError) as error:
                if "already exists" not in str(error).lower():
                    raise


ensure_runtime_schema_updates()

app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    description="Backend API for a furniture e-commerce store (shelves, cupboards, shop interiors, etc.)",
    docs_url="/docs" if settings.ENABLE_DOCS else None,
    redoc_url="/redoc" if settings.ENABLE_DOCS else None,
    openapi_url="/openapi.json" if settings.ENABLE_DOCS else None,
)


@app.on_event("startup")
async def start_background_services():
    start_cart_reminder_scheduler(app)


@app.on_event("shutdown")
async def stop_background_services():
    await stop_cart_reminder_scheduler(app)

app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.TRUSTED_HOSTS or ["localhost"])

CSRF_EXEMPT_PATHS = {
    "/",
    "/health",
    "/api/v1/auth/login",
    "/api/v1/auth/register",
    "/api/v1/auth/google",
    "/api/v1/auth/refresh",
    "/api/v1/auth/forgot-password",
    "/api/v1/auth/reset-password",
    "/api/v1/analytics/visit",
    "/api/v1/analytics/product-view",
    "/api/v1/marketing/subscribe",
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
    if not request.url.path.startswith("/uploads/catalogue/"):
        response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Cache-Control"] = "no-store"
    if request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response

# CORS is registered last so it ends up outermost in the middleware stack
# (Starlette's add_middleware prepends, so the last-registered middleware runs
# first on the way in / last on the way out) — this ensures CORS headers are
# attached even to responses short-circuited by enforce_csrf or other middleware.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve uploaded files as static assets
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")

# Register routers
API = "/api/v1"
app.include_router(auth.router,       prefix=API)
app.include_router(users.router,      prefix=API)
app.include_router(categories.router, prefix=API)
app.include_router(products.router,   prefix=API)
app.include_router(product_content.router, prefix=API)
app.include_router(analytics.router,  prefix=API)
app.include_router(marketing.router,  prefix=API)
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
