from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.models.order import Order, OrderStatus
from app.models.product import Product
from app.models.inventory import Inventory
from app.models.review import Review
from app.core.dependencies import get_current_manager

router = APIRouter(prefix="/manager", tags=["Manager"])


@router.get("/dashboard")
def manager_dashboard(db: Session = Depends(get_db), user=Depends(get_current_manager)):
    total_orders = db.query(func.count(Order.id)).scalar()
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
        "total_orders": total_orders,
        "pending_orders": pending_orders,
        "low_stock_count": low_stock_count,
        "pending_reviews": pending_reviews,
    }
