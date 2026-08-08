import re
import secrets
import string
import unicodedata
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import distinct, func
from typing import List, Optional
from app.database import get_db
from app.models.user import User, UserRole
from app.models.address import Address
from app.models.cart import Cart
from app.models.order import Order, OrderItem, OrderStatus, PaymentStatus
from app.models.product import Product
from app.models.analytics import ProductView, SiteVisit
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
    total_users = (
        db.query(func.count(User.id))
        .filter(User.role == UserRole.user, ~User.email.ilike("deleted-%@deleted.local"))
        .scalar()
    )
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

class CustomerAddressUpdate(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None


class CustomerUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    is_active: Optional[bool] = None
    address: Optional[CustomerAddressUpdate] = None


def _format_customer_response(user: User, order_count=0, total_spent=0, last_order_date=None, address: Optional[Address] = None):
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "phone": user.phone,
        "is_active": user.is_active,
        "created_at": user.created_at,
        "order_count": int(order_count or 0),
        "total_spent": float(total_spent or 0),
        "last_order_date": last_order_date,
        "address": (
            {
                "id": address.id,
                "full_name": address.full_name,
                "phone": address.phone,
                "address_line1": address.address_line1,
                "address_line2": address.address_line2,
                "city": address.city,
                "state": address.state,
                "postal_code": address.postal_code,
                "country": address.country,
                "is_default": address.is_default,
            }
            if address
            else None
        ),
    }


def _get_customer_summary(db: Session, customer_id: int):
    row = (
        db.query(
            User,
            func.count(Order.id).label("order_count"),
            func.coalesce(func.sum(Order.total_amount), 0).label("total_spent"),
            func.max(Order.created_at).label("last_order_date"),
        )
        .outerjoin(Order, Order.user_id == User.id)
        .filter(User.id == customer_id, User.role == UserRole.user)
        .group_by(User.id)
        .first()
    )
    if not row:
        return None
    user, order_count, total_spent, last_order_date = row
    address = (
        db.query(Address)
        .filter(Address.user_id == user.id)
        .order_by(Address.is_default.desc(), Address.created_at.desc())
        .first()
    )
    return _format_customer_response(user, order_count, total_spent, last_order_date, address)


def _anonymize_customer_account(db: Session, user: User):
    deleted_at = datetime.now(timezone.utc)
    anonymized_email = f"deleted-customer-{user.id}-{int(deleted_at.timestamp())}@deleted.local"

    cart = db.query(Cart).filter(Cart.user_id == user.id).first()
    if cart:
        db.delete(cart)

    db.query(Review).filter(Review.user_id == user.id).delete(synchronize_session=False)

    for address in db.query(Address).filter(Address.user_id == user.id).all():
        address.full_name = "Deleted Customer"
        address.phone = "Deleted"
        address.address_line1 = "Deleted address"
        address.address_line2 = None
        address.city = "Deleted"
        address.state = "Deleted"
        address.postal_code = "Deleted"
        address.country = "Deleted"
        address.is_default = False

    user.email = anonymized_email
    user.full_name = "Deleted Customer"
    user.phone = None
    user.hashed_password = hash_password(secrets.token_urlsafe(32))
    user.is_active = False
    user.is_email_verified = False
    user.must_reset_password = False
    user.token_version += 1


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
        .filter(User.role == UserRole.user, ~User.email.ilike("deleted-%@deleted.local"))
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
    user_ids = [user.id for user, *_ in rows]
    address_rows = (
        db.query(Address)
        .filter(Address.user_id.in_(user_ids))
        .order_by(Address.is_default.desc(), Address.created_at.desc())
        .all()
        if user_ids
        else []
    )
    address_by_user_id = {}
    for address in address_rows:
        address_by_user_id.setdefault(address.user_id, address)

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
            "address": (
                {
                    "id": address_by_user_id[user.id].id,
                    "full_name": address_by_user_id[user.id].full_name,
                    "phone": address_by_user_id[user.id].phone,
                    "address_line1": address_by_user_id[user.id].address_line1,
                    "address_line2": address_by_user_id[user.id].address_line2,
                    "city": address_by_user_id[user.id].city,
                    "state": address_by_user_id[user.id].state,
                    "postal_code": address_by_user_id[user.id].postal_code,
                    "country": address_by_user_id[user.id].country,
                    "is_default": address_by_user_id[user.id].is_default,
                }
                if user.id in address_by_user_id
                else None
            ),
        }
        for user, order_count, total_spent, last_order_date in rows
    ]

    return {"items": items, "total": total, "page": page, "per_page": per_page}


@router.put("/customers/{customer_id}")
def update_customer(
    customer_id: int,
    body: CustomerUpdate,
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    user = db.query(User).filter(User.id == customer_id, User.role == UserRole.user).first()
    if not user:
        raise HTTPException(status_code=404, detail="Customer not found")

    updates = body.model_dump(exclude_unset=True)
    changed_fields = []

    if "email" in updates and updates["email"] is not None:
        email = updates["email"].strip().lower()
        if not email:
            raise HTTPException(status_code=422, detail="Email cannot be empty")
        existing = db.query(User).filter(User.email == email, User.id != customer_id).first()
        if existing:
            raise HTTPException(status_code=409, detail="Email already registered")
        user.email = email
        user.token_version += 1
        changed_fields.append("email")

    if "full_name" in updates and updates["full_name"] is not None:
        full_name = updates["full_name"].strip()
        if not full_name:
            raise HTTPException(status_code=422, detail="Full name cannot be empty")
        user.full_name = full_name
        changed_fields.append("full_name")

    if "phone" in updates:
        user.phone = updates["phone"].strip() if updates["phone"] else None
        changed_fields.append("phone")

    if "is_active" in updates and updates["is_active"] is not None:
        user.is_active = bool(updates["is_active"])
        if not user.is_active:
            user.token_version += 1
        changed_fields.append("is_active")

    if "address" in updates and updates["address"] is not None:
        address_data = updates["address"]
        address = (
            db.query(Address)
            .filter(Address.user_id == user.id)
            .order_by(Address.is_default.desc(), Address.created_at.desc())
            .first()
        )
        address_updates = {key: value for key, value in address_data.items() if value is not None}

        if address_updates:
            if not address:
                required_fields = {
                    "full_name": address_updates.get("full_name") or user.full_name,
                    "phone": address_updates.get("phone") or user.phone,
                    "address_line1": address_updates.get("address_line1"),
                    "city": address_updates.get("city"),
                    "state": address_updates.get("state"),
                    "postal_code": address_updates.get("postal_code"),
                    "country": address_updates.get("country") or "US",
                }
                missing = [key for key, value in required_fields.items() if not value]
                if missing:
                    raise HTTPException(status_code=422, detail=f"Missing address fields: {', '.join(missing)}")
                address = Address(
                    user_id=user.id,
                    full_name=required_fields["full_name"],
                    phone=required_fields["phone"],
                    address_line1=required_fields["address_line1"],
                    address_line2=address_updates.get("address_line2"),
                    city=required_fields["city"],
                    state=required_fields["state"],
                    postal_code=required_fields["postal_code"],
                    country=required_fields["country"],
                    is_default=True,
                )
                db.add(address)
            else:
                for field, value in address_updates.items():
                    setattr(address, field, value.strip() if isinstance(value, str) else value)
                if not address.full_name:
                    address.full_name = user.full_name
                if not address.phone and user.phone:
                    address.phone = user.phone
            changed_fields.append("address")

    if not changed_fields:
        summary = _get_customer_summary(db, customer_id)
        if not summary:
            raise HTTPException(status_code=404, detail="Customer not found")
        return summary

    log_admin_action(
        db,
        admin_user_id=admin.id,
        action="update_customer",
        target_user_id=user.id,
        details=f"Updated fields: {', '.join(sorted(set(changed_fields)))}",
    )
    db.commit()

    summary = _get_customer_summary(db, customer_id)
    if not summary:
        raise HTTPException(status_code=404, detail="Customer not found")
    return summary


@router.delete("/customers/{customer_id}", status_code=204)
def delete_customer(
    customer_id: int,
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    user = db.query(User).filter(User.id == customer_id, User.role == UserRole.user).first()
    if not user:
        raise HTTPException(status_code=404, detail="Customer not found")

    original_email = user.email
    log_admin_action(
        db,
        admin_user_id=admin.id,
        action="delete_customer",
        target_user_id=user.id,
        details=f"Anonymized and deactivated customer {original_email}",
    )
    _anonymize_customer_account(db, user)
    db.commit()


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


@router.get("/reports/most-viewed-products")
def most_viewed_products_report(
    limit: int = Query(10, ge=1, le=20),
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    total_views = func.count(ProductView.id).label("total_views")
    latest_viewed_at = func.max(ProductView.created_at).label("latest_viewed_at")

    rows = (
        db.query(Product.id, Product.name, total_views, latest_viewed_at)
        .join(ProductView, ProductView.product_id == Product.id)
        .filter(Product.is_active == True)
        .group_by(Product.id, Product.name)
        .order_by(total_views.desc(), Product.name.asc())
        .limit(limit)
        .all()
    )

    return [
        {
            "product_id": product_id,
            "product_name": product_name,
            "total_views": int(views or 0),
            "latest_viewed_at": latest_at,
        }
        for product_id, product_name, views, latest_at in rows
    ]


@router.get("/reports/best-selling-products")
def best_selling_products_report(
    limit: int = Query(10, ge=1, le=20),
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    units_sold = func.sum(OrderItem.quantity).label("units_sold")
    revenue = func.sum(OrderItem.unit_price * OrderItem.quantity).label("revenue")

    rows = (
        db.query(Product.id, Product.name, units_sold, revenue)
        .join(OrderItem, OrderItem.product_id == Product.id)
        .join(Order, Order.id == OrderItem.order_id)
        .filter(
            Product.is_active == True,
            Order.payment_status == PaymentStatus.paid,
            Order.status != OrderStatus.cancelled,
        )
        .group_by(Product.id, Product.name)
        .order_by(units_sold.desc(), Product.name.asc())
        .limit(limit)
        .all()
    )

    return [
        {
            "product_id": product_id,
            "product_name": product_name,
            "units_sold": int(sold or 0),
            "revenue": float(total_revenue or 0),
        }
        for product_id, product_name, sold, total_revenue in rows
    ]


@router.get("/reports/visitors")
def visitors_report(
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    now = datetime.now(timezone.utc)

    def stats_for(days: int):
        start = now - timedelta(days=days)
        row = (
            db.query(
                func.count(SiteVisit.id).label("total_visits"),
                func.count(distinct(SiteVisit.visitor_id)).label("unique_visitors"),
                func.count(distinct(SiteVisit.session_id)).label("unique_sessions"),
            )
            .filter(SiteVisit.created_at >= start)
            .first()
        )
        return {
            "days": days,
            "start_date": start.isoformat(),
            "total_visits": int(row.total_visits or 0),
            "unique_visitors": int(row.unique_visitors or 0),
            "unique_sessions": int(row.unique_sessions or 0),
        }

    return {
        "last_7_days": stats_for(7),
        "last_30_days": stats_for(30),
    }


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
