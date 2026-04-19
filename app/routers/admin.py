from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List
from app.database import get_db
from app.models.user import User
from app.models.order import Order, OrderStatus, PaymentStatus
from app.models.product import Product
from app.schemas.user import UserResponse
from app.core.dependencies import get_current_admin

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/dashboard")
def get_dashboard(db: Session = Depends(get_db), admin=Depends(get_current_admin)):
    total_users = db.query(func.count(User.id)).scalar()
    total_orders = db.query(func.count(Order.id)).scalar()
    total_revenue = (
        db.query(func.sum(Order.total_amount))
        .filter(Order.payment_status == PaymentStatus.paid)
        .scalar()
        or 0
    )
    total_products = (
        db.query(func.count(Product.id)).filter(Product.is_active == True).scalar()
    )
    pending_orders = (
        db.query(func.count(Order.id))
        .filter(Order.status == OrderStatus.pending)
        .scalar()
    )

    return {
        "total_users": total_users,
        "total_orders": total_orders,
        "total_revenue": float(total_revenue),
        "total_products": total_products,
        "pending_orders": pending_orders,
    }


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
def toggle_user_active(
    user_id: int,
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_active = not user.is_active
    db.commit()
    db.refresh(user)
    return user


@router.put("/users/{user_id}/make-admin", response_model=UserResponse)
def make_admin(
    user_id: int,
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    from app.models.user import UserRole
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.role = UserRole.admin
    db.commit()
    db.refresh(user)
    return user
