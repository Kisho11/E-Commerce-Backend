import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.config import settings
from app.database import engine, Base

# Import all models so Base.metadata is populated before create_all
import app.models  # noqa: F401

from app.routers import auth, users, categories, products, cart, orders, reviews, payments, admin

# Create all tables on startup
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    description="Backend API for a furniture e-commerce store (shelves, cupboards, shop interiors, etc.)",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS
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
app.include_router(cart.router,       prefix=API)
app.include_router(orders.router,     prefix=API)
app.include_router(reviews.router,    prefix=API)
app.include_router(payments.router,   prefix=API)
app.include_router(admin.router,      prefix=API)


@app.get("/", tags=["Root"])
def root():
    return {"message": "Furniture Store API", "docs": "/docs"}


@app.get("/health", tags=["Root"])
def health():
    return {"status": "healthy"}
