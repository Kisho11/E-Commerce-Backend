from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import select
from typing import List, Optional
from app.database import get_db
from app.models.order import Order, OrderItem, OrderStatus
from app.models.cart import Cart, CartItem
from app.models.address import Address
from app.models.product import Product
from app.schemas.order import OrderCreate, OrderResponse, OrderStatusUpdate
from app.core.dependencies import get_current_user, get_current_admin

router = APIRouter(prefix="/orders", tags=["Orders"])


@router.post("/", response_model=OrderResponse, status_code=201)
def create_order(
    order_data: OrderCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    address = (
        db.query(Address)
        .filter(Address.id == order_data.address_id, Address.user_id == current_user.id)
        .first()
    )
    if not address:
        raise HTTPException(status_code=404, detail="Address not found")

    cart = db.query(Cart).filter(Cart.user_id == current_user.id).first()
    if not cart or not cart.items:
        raise HTTPException(status_code=400, detail="Cart is empty")

    locked_cart = (
        db.query(Cart)
        .filter(Cart.user_id == current_user.id)
        .with_for_update()
        .first()
    )
    if not locked_cart or not locked_cart.items:
        raise HTTPException(status_code=400, detail="Cart is empty")

    selected_cart_items = list(locked_cart.items)
    if order_data.cart_item_ids is not None:
        requested_item_ids = set(order_data.cart_item_ids)
        selected_cart_items = [item for item in locked_cart.items if item.id in requested_item_ids]
        if not selected_cart_items:
            raise HTTPException(status_code=400, detail="Select at least one cart item to checkout")
        if len(selected_cart_items) != len(requested_item_ids):
            raise HTTPException(status_code=400, detail="One or more selected cart items were not found")

    product_ids = [item.product_id for item in selected_cart_items]
    locked_products = (
        db.execute(
            select(Product)
            .where(Product.id.in_(product_ids))
            .with_for_update()
        )
        .scalars()
        .all()
    )
    products_by_id = {product.id: product for product in locked_products}

    total = Decimal("0")
    for item in selected_cart_items:
        product = products_by_id.get(item.product_id)
        if not product:
            raise HTTPException(status_code=404, detail="Product not found during checkout")
        if not product.is_active:
            raise HTTPException(
                status_code=400, detail=f"Product '{product.name}' is no longer available"
            )
        if product.stock_quantity > 0 and product.stock_quantity < item.quantity:
            raise HTTPException(
                status_code=400, detail=f"Insufficient stock for '{product.name}'"
            )
        price = product.sale_price or product.price
        total += price * item.quantity

    order = Order(
        user_id=current_user.id,
        address_id=address.id,
        total_amount=total,
        notes=order_data.notes,
    )
    db.add(order)
    db.flush()

    for item in selected_cart_items:
        product = products_by_id[item.product_id]
        price = product.sale_price or product.price
        db.add(
            OrderItem(
                order_id=order.id,
                product_id=product.id,
                quantity=item.quantity,
                unit_price=price,
                total_price=price * item.quantity,
            )
        )
        product.stock_quantity -= item.quantity

    selected_item_ids = [item.id for item in selected_cart_items]
    db.query(CartItem).filter(
        CartItem.cart_id == locked_cart.id,
        CartItem.id.in_(selected_item_ids),
    ).delete(synchronize_session=False)
    db.commit()
    db.refresh(order)
    return order


@router.get("/", response_model=List[OrderResponse])
def get_my_orders(
    status: Optional[OrderStatus] = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    query = db.query(Order).filter(Order.user_id == current_user.id)
    if status:
        query = query.filter(Order.status == status)
    return query.order_by(Order.created_at.desc()).all()


@router.get("/{order_id}", response_model=OrderResponse)
def get_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    order = (
        db.query(Order)
        .filter(Order.id == order_id, Order.user_id == current_user.id)
        .first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@router.put("/{order_id}/cancel", response_model=OrderResponse)
def cancel_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    order = (
        db.query(Order)
        .filter(Order.id == order_id, Order.user_id == current_user.id)
        .first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.status not in [OrderStatus.pending, OrderStatus.confirmed]:
        raise HTTPException(status_code=400, detail="Order cannot be cancelled at this stage")

    for item in order.items:
        item.product.stock_quantity += item.quantity

    order.status = OrderStatus.cancelled
    db.commit()
    db.refresh(order)
    return order


# ── Admin endpoints ────────────────────────────────────────────────────────────

@router.get("/admin/all", response_model=List[OrderResponse])
def admin_get_all_orders(
    status: Optional[OrderStatus] = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    query = db.query(Order)
    if status:
        query = query.filter(Order.status == status)
    return (
        query.order_by(Order.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )


@router.put("/admin/{order_id}/status", response_model=OrderResponse)
def admin_update_order_status(
    order_id: int,
    status_update: OrderStatusUpdate,
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    order.status = status_update.status
    db.commit()
    db.refresh(order)
    return order
