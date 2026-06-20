import re
import secrets
import string
import unicodedata
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from app.database import get_db
from app.models.user import User, UserRole
from app.models.order import Order, OrderStatus, PaymentStatus
from app.models.product import Product
from app.models.industry import Industry
from app.models.inventory import Inventory
from app.models.review import Review
from app.schemas.user import UserResponse, ManagerCreate, ManagerUpdate, ManagerResponse
from app.core.dependencies import get_current_admin
from app.core.security import hash_password, create_access_token
from app.core.audit import log_admin_action
from app.config import settings
from app.utils.email import send_manager_invite_email


def _slugify(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).lower().strip()
    s = re.sub(r"[^\w\s-]", "", s, flags=re.ASCII)
    return re.sub(r"[\s_]+", "-", s).strip("-")


def _make_unique_industry_slug(name: str, db: Session, exclude_id: Optional[int] = None) -> str:
    base_slug = _slugify(name)
    slug = base_slug
    counter = 1
    while True:
        query = db.query(Industry).filter(Industry.slug == slug)
        if exclude_id:
            query = query.filter(Industry.id != exclude_id)
        if not query.first():
            return slug
        slug = f"{base_slug}-{counter}"
        counter += 1

router = APIRouter(prefix="/admin", tags=["Admin"])


# ── Dashboard ────────────────────────────────────────────────────────────────

@router.get("/dashboard")
def get_dashboard(db: Session = Depends(get_db), admin=Depends(get_current_admin)):
    total_users = db.query(func.count(User.id)).filter(User.role == UserRole.user).scalar()
    total_customers = total_users
    total_orders = db.query(func.count(Order.id)).scalar()
    total_revenue = (
        db.query(func.sum(Order.total_amount))
        .filter(Order.payment_status == PaymentStatus.paid)
        .scalar() or 0
    )
    available_products = db.query(func.count(Product.id)).filter(Product.is_active == True).scalar()
    pending_orders = (
        db.query(func.count(Order.id)).filter(Order.status == OrderStatus.pending).scalar()
    )
    low_stock_count = (
        db.query(func.count(Inventory.id))
        .filter(Inventory.on_hand <= Inventory.reorder_level, Inventory.on_hand > 0)
        .scalar()
    )
    pending_reviews = (
        db.query(func.count(Review.id)).filter(Review.is_verified == False).scalar()
    )

    return {
        "total_users": total_users,
        "total_customers": total_customers,
        "total_orders": total_orders,
        "total_revenue": float(total_revenue),
        "available_products": available_products,
        "pending_orders": pending_orders,
        "low_stock_count": low_stock_count,
        "pending_reviews": pending_reviews,
    }


# ── Users ────────────────────────────────────────────────────────────────────

@router.get("/users", response_model=List[UserResponse])
def get_all_users(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    return (
        db.query(User)
        .order_by(User.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )


@router.put("/users/{user_id}/toggle-active", response_model=UserResponse)
def toggle_user_active(user_id: int, db: Session = Depends(get_db), admin=Depends(get_current_admin)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="You cannot deactivate your own account")
    user.is_active = not user.is_active
    log_admin_action(
        db,
        admin_user_id=admin.id,
        action="toggle_user_active",
        target_user_id=user.id,
        details=f"is_active={user.is_active}",
    )
    db.commit()
    db.refresh(user)
    return user


@router.put("/users/{user_id}/make-admin", response_model=UserResponse)
def make_admin(user_id: int, db: Session = Depends(get_db), admin=Depends(get_current_admin)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive users cannot be promoted")
    user.role = UserRole.admin
    log_admin_action(
        db,
        admin_user_id=admin.id,
        action="make_admin",
        target_user_id=user.id,
        details="Promoted user to admin",
    )
    db.commit()
    db.refresh(user)
    return user


# ── Managers ─────────────────────────────────────────────────────────────────

@router.get("/managers", response_model=List[UserResponse])
def list_managers(db: Session = Depends(get_db), admin=Depends(get_current_admin)):
    return db.query(User).filter(User.role == UserRole.manager).order_by(User.created_at.desc()).all()


@router.post("/managers", response_model=ManagerResponse, status_code=201)
def create_manager(body: ManagerCreate, db: Session = Depends(get_db), admin=Depends(get_current_admin)):
    normalized_email = body.email.lower()
    if db.query(User).filter(User.email == normalized_email).first():
        raise HTTPException(status_code=409, detail="Email already registered")

    alphabet = string.ascii_letters + string.digits + string.punctuation
    temp_password = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(14))

    user = User(
        email=normalized_email,
        full_name=body.full_name,
        phone=body.phone,
        role=UserRole.manager,
        hashed_password=hash_password(temp_password),
        must_reset_password=True,
        is_email_verified=True,
    )
    db.add(user)
    db.flush()
    log_admin_action(
        db,
        admin_user_id=admin.id,
        action="create_manager",
        target_user_id=user.id,
        details=f"Created manager account for {normalized_email}",
    )
    db.commit()
    db.refresh(user)

    try:
        invite_token = create_access_token(
            {"sub": str(user.id), "purpose": "manager_invite"},
            expires_delta=timedelta(hours=settings.MANAGER_INVITE_TOKEN_EXPIRE_HOURS),
        )
        send_manager_invite_email(user.email, user.full_name, temp_password, invite_token)
    except Exception as e:
        print(f"[INVITE EMAIL ERROR] {type(e).__name__}: {e}")

    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "phone": user.phone,
        "role": user.role,
        "is_active": user.is_active,
        "is_email_verified": user.is_email_verified,
        "must_reset_password": user.must_reset_password,
        "created_at": user.created_at,
        "temporary_password": temp_password,
    }


@router.put("/managers/{manager_id}", response_model=UserResponse)
def update_manager(
    manager_id: int,
    body: ManagerUpdate,
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    manager = db.query(User).filter(User.id == manager_id, User.role == UserRole.manager).first()
    if not manager:
        raise HTTPException(status_code=404, detail="Manager not found")
    updates = body.model_dump(exclude_unset=True)
    if "email" in updates:
        updates["email"] = updates["email"].lower()
        existing = db.query(User).filter(User.email == updates["email"], User.id != manager_id).first()
        if existing:
            raise HTTPException(status_code=409, detail="Email already registered")
    for field, value in updates.items():
        setattr(manager, field, value)
    log_admin_action(
        db,
        admin_user_id=admin.id,
        action="update_manager",
        target_user_id=manager.id,
        details=f"Updated fields: {', '.join(sorted(updates.keys()))}",
    )
    db.commit()
    db.refresh(manager)
    return manager


@router.delete("/managers/{manager_id}", status_code=204)
def delete_manager(manager_id: int, db: Session = Depends(get_db), admin=Depends(get_current_admin)):
    manager = db.query(User).filter(User.id == manager_id, User.role == UserRole.manager).first()
    if not manager:
        raise HTTPException(status_code=404, detail="Manager not found")
    log_admin_action(
        db,
        admin_user_id=admin.id,
        action="delete_manager",
        target_user_id=manager.id,
        details=f"Deleted manager {manager.email}",
    )
    db.flush()
    db.delete(manager)
    db.commit()


# ── Customers ─────────────────────────────────────────────────────────────────

@router.get("/customers")
def list_customers(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    min_orders: Optional[int] = Query(None, ge=0),
    sort_by: str = Query("created_at"),
    sort_dir: str = Query("desc"),
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    q = (
        db.query(
            User,
            func.count(Order.id).label("order_count"),
            func.coalesce(func.sum(Order.total_amount), 0).label("total_spent"),
            func.max(Order.created_at).label("last_order_date"),
        )
        .outerjoin(Order, Order.user_id == User.id)
        .filter(User.role == UserRole.user)
        .group_by(User.id)
    )

    if search:
        term = f"%{search}%"
        q = q.filter(User.full_name.ilike(term) | User.email.ilike(term))

    if min_orders is not None:
        q = q.having(func.count(Order.id) >= min_orders)

    total = q.count()

    sort_col_map = {
        "name": User.full_name,
        "email": User.email,
        "created_at": User.created_at,
    }
    sort_col = sort_col_map.get(sort_by, User.created_at)
    if sort_dir == "asc":
        q = q.order_by(sort_col.asc())
    else:
        q = q.order_by(sort_col.desc())

    rows = q.offset((page - 1) * per_page).limit(per_page).all()

    items = [
        {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "phone": user.phone,
            "is_active": user.is_active,
            "created_at": user.created_at,
            "order_count": order_count,
            "total_spent": float(total_spent),
            "last_order_date": last_order_date,
        }
        for user, order_count, total_spent, last_order_date in rows
    ]

    return {"items": items, "total": total, "page": page, "per_page": per_page}


@router.get("/customers/{customer_id}/orders")
def get_customer_orders(
    customer_id: int,
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    user = db.query(User).filter(User.id == customer_id, User.role == UserRole.user).first()
    if not user:
        raise HTTPException(status_code=404, detail="Customer not found")
    orders = (
        db.query(Order)
        .filter(Order.user_id == customer_id)
        .order_by(Order.created_at.desc())
        .all()
    )
    return {
        "customer": {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
        },
        "orders": [
            {
                "id": o.id,
                "status": o.status,
                "payment_status": o.payment_status,
                "total_amount": float(o.total_amount),
                "created_at": o.created_at,
            }
            for o in orders
        ],
    }


# ── Reports ──────────────────────────────────────────────────────────────────

@router.get("/reports/sales")
def sales_report(
    period: str = Query("month", pattern="^(week|month|year)$"),
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    if period == "week":
        start = now - timedelta(days=7)
    elif period == "year":
        start = now - timedelta(days=365)
    else:
        start = now - timedelta(days=30)

    paid_orders = (
        db.query(Order)
        .filter(Order.payment_status == PaymentStatus.paid, Order.created_at >= start)
        .all()
    )

    total_revenue = sum(float(o.total_amount) for o in paid_orders)
    total_orders = len(paid_orders)
    avg_order_value = total_revenue / total_orders if total_orders else 0

    return {
        "period": period,
        "start_date": start.isoformat(),
        "total_revenue": total_revenue,
        "total_orders": total_orders,
        "avg_order_value": avg_order_value,
    }


@router.get("/reports/top-categories")
def top_categories_report(
    limit: int = Query(5, ge=1, le=20),
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    from app.models.order import OrderItem
    from app.models.product import product_categories
    from app.models.category import Category

    rows = (
        db.query(
            Category.name,
            func.count(OrderItem.id).label("order_count"),
            func.sum(OrderItem.quantity).label("units_sold"),
            func.sum(OrderItem.unit_price * OrderItem.quantity).label("revenue"),
        )
        .join(product_categories, product_categories.c.category_id == Category.id)
        .join(Product, Product.id == product_categories.c.product_id)
        .join(OrderItem, OrderItem.product_id == Product.id)
        .group_by(Category.id, Category.name)
        .order_by(func.sum(OrderItem.quantity).desc())
        .limit(limit)
        .all()
    )

    return [
        {
            "category": name,
            "order_count": order_count,
            "units_sold": int(units_sold or 0),
            "revenue": float(revenue or 0),
        }
        for name, order_count, units_sold, revenue in rows
    ]


# ── Industries ────────────────────────────────────────────────────────────────

class IndustryIn(BaseModel):
    name: str
    is_active: bool = True


@router.get("/industries")
def list_industries(
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    return db.query(Industry).order_by(Industry.name).all()


@router.post("/industries", status_code=201)
def create_industry(body: IndustryIn, db: Session = Depends(get_db), admin=Depends(get_current_admin)):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Name cannot be empty")
    if db.query(Industry).filter(func.lower(Industry.name) == name.lower()).first():
        raise HTTPException(status_code=409, detail="Industry already exists")
    slug = _make_unique_industry_slug(name, db)
    industry = Industry(name=name, slug=slug, is_active=body.is_active)
    db.add(industry)
    db.commit()
    db.refresh(industry)
    return industry


@router.put("/industries/{industry_id}")
def update_industry(
    industry_id: int,
    body: IndustryIn,
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    industry = db.query(Industry).filter(Industry.id == industry_id).first()
    if not industry:
        raise HTTPException(status_code=404, detail="Industry not found")
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Name cannot be empty")
    conflict = (
        db.query(Industry)
        .filter(func.lower(Industry.name) == name.lower(), Industry.id != industry_id)
        .first()
    )
    if conflict:
        raise HTTPException(status_code=409, detail="Industry name already in use")
    industry.name = name
    industry.slug = _make_unique_industry_slug(name, db, exclude_id=industry_id)
    industry.is_active = body.is_active
    db.commit()
    db.refresh(industry)
    return industry


@router.delete("/industries/{industry_id}", status_code=204)
def delete_industry(
    industry_id: int,
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    industry = db.query(Industry).filter(Industry.id == industry_id).first()
    if not industry:
        raise HTTPException(status_code=404, detail="Industry not found")
    db.delete(industry)
    db.commit()
