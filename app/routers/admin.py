import secrets
import string
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from app.database import get_db
from app.models.user import User, UserRole
from app.models.order import Order, OrderStatus, PaymentStatus
from app.models.product import Product
from app.models.inventory import Inventory
from app.models.review import Review
from app.schemas.user import UserResponse, ManagerCreate, ManagerUpdate
from app.core.dependencies import get_current_admin
from app.core.security import hash_password

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
    user.is_active = not user.is_active
    db.commit()
    db.refresh(user)
    return user


@router.put("/users/{user_id}/make-admin", response_model=UserResponse)
def make_admin(user_id: int, db: Session = Depends(get_db), admin=Depends(get_current_admin)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.role = UserRole.admin
    db.commit()
    db.refresh(user)
    return user


# ── Managers ─────────────────────────────────────────────────────────────────

@router.get("/managers", response_model=List[UserResponse])
def list_managers(db: Session = Depends(get_db), admin=Depends(get_current_admin)):
    return db.query(User).filter(User.role == UserRole.manager).order_by(User.created_at.desc()).all()


@router.post("/managers", response_model=UserResponse, status_code=201)
def create_manager(body: ManagerCreate, db: Session = Depends(get_db), admin=Depends(get_current_admin)):
    if db.query(User).filter(User.email == body.email).first():
        raise HTTPException(status_code=409, detail="Email already registered")
    alphabet = string.ascii_letters + string.digits
    password = body.password or "".join(secrets.choice(alphabet) for _ in range(12))
    user = User(
        email=body.email,
        full_name=body.full_name,
        phone=body.phone,
        role=UserRole.manager,
        hashed_password=hash_password(password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


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
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(manager, field, value)
    db.commit()
    db.refresh(manager)
    return manager


@router.delete("/managers/{manager_id}", status_code=204)
def delete_manager(manager_id: int, db: Session = Depends(get_db), admin=Depends(get_current_admin)):
    manager = db.query(User).filter(User.id == manager_id, User.role == UserRole.manager).first()
    if not manager:
        raise HTTPException(status_code=404, detail="Manager not found")
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
