from decimal import Decimal
import json
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import select
from typing import List, Optional
from app.database import get_db
from app.models.order import Order, OrderItem, OrderStatus, PaymentStatus
from app.models.cart import Cart
from app.models.address import Address
from app.models.marketing import MarketingBanner
from app.models.product import Product
from app.models.inventory import MovementType
from app.schemas.order import OrderCreate, OrderResponse, OrderStatusUpdate
from app.core.dependencies import get_current_user, get_current_admin
from app.config import settings
from app.utils.shipping import calculate_order_shipping_fee
from app.utils.variant_pricing import (
    adjust_stock_quantity,
    ensure_stock_available,
    normalize_attributes,
    resolve_product_unit_price,
)

router = APIRouter(prefix="/orders", tags=["Orders"])
MONEY_QUANT = Decimal("0.01")


def get_checkout_tax_rate() -> Decimal:
    return Decimal(str(settings.CHECKOUT_TAX_RATE or "0"))


def get_global_discount_percentage(db: Session) -> Decimal:
    marketing_settings = db.query(MarketingBanner).order_by(MarketingBanner.id.asc()).first()
    if not marketing_settings:
        return Decimal("0")
    discount = Decimal(str(marketing_settings.global_discount_percentage or "0"))
    return min(max(discount, Decimal("0")), Decimal("100"))


def release_reserved_stock(order: Order, db: Session | None = None, actor: str | None = None) -> None:
    if not order.stock_reserved:
        return

    for item in order.items:
        if item.product:
            adjust_stock_quantity(
                item.product,
                item.selected_attributes or {},
                item.quantity,
                db=db,
                movement_type=MovementType.return_,
                reason=f"Order #{order.id} cancelled",
                actor=actor,
            )
    order.stock_reserved = False


@router.post("/", response_model=OrderResponse, status_code=201)
def create_order(
    order_data: OrderCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    delivery_mode = (order_data.delivery_mode or "ship").strip().lower()
    if delivery_mode not in {"ship", "pickup"}:
        raise HTTPException(status_code=422, detail="Invalid delivery mode")

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

    subtotal = Decimal("0")
    for item in selected_cart_items:
        product = products_by_id.get(item.product_id)
        if not product:
            raise HTTPException(status_code=404, detail="Product not found during checkout")
        if not product.is_active:
            raise HTTPException(
                status_code=400, detail=f"Product '{product.name}' is no longer available"
            )
        try:
            ensure_stock_available(product, item.selected_attributes or {}, item.quantity)
        except ValueError:
            raise HTTPException(
                status_code=400, detail=f"Insufficient stock for '{product.name}'"
            )
        price = resolve_product_unit_price(product, item.selected_attributes)
        subtotal += price * item.quantity

    discount_percentage = get_global_discount_percentage(db)
    discount_amount = ((subtotal * discount_percentage) / Decimal("100")).quantize(MONEY_QUANT)
    discounted_subtotal = (subtotal - discount_amount).quantize(MONEY_QUANT)
    tax_rate = get_checkout_tax_rate()
    tax_amount = (discounted_subtotal * tax_rate).quantize(MONEY_QUANT)
    shipping_fee = calculate_order_shipping_fee(
        db,
        (products_by_id[item.product_id] for item in selected_cart_items),
        delivery_mode,
    )
    total = (discounted_subtotal + tax_amount + shipping_fee).quantize(MONEY_QUANT)

    selected_item_ids = [item.id for item in selected_cart_items]
    stock_reserved = False
    order = Order(
        user_id=current_user.id,
        address_id=address.id,
        total_amount=total,
        subtotal_amount=subtotal.quantize(MONEY_QUANT),
        discount_percentage=discount_percentage.quantize(Decimal("0.01")),
        discount_amount=discount_amount,
        tax_rate=tax_rate,
        tax_amount=tax_amount,
        shipping_fee=shipping_fee,
        status=OrderStatus.pending,
        payment_status=PaymentStatus.pending,
        checkout_cart_item_ids=json.dumps(selected_item_ids),
        stock_reserved=False,
        delivery_mode=delivery_mode,
        delivery_note=(order_data.delivery_note or "").strip() or None,
        notes=order_data.notes,
    )
    db.add(order)
    db.flush()

    for item in selected_cart_items:
        product = products_by_id[item.product_id]
        selected_attributes = normalize_attributes(item.selected_attributes or {})
        price = resolve_product_unit_price(product, selected_attributes)
        line_total = price * item.quantity
        db.add(
            OrderItem(
                order_id=order.id,
                product_id=product.id,
                quantity=item.quantity,
                unit_price=price,
                total_price=line_total,
                selected_attributes=selected_attributes or None,
            )
        )
        adjust_stock_quantity(
            product,
            selected_attributes,
            -item.quantity,
            db=db,
            movement_type=MovementType.sale,
            reason=f"Order #{order.id} stock reserved",
            actor=current_user.full_name,
        )
        stock_reserved = True

    order.stock_reserved = stock_reserved

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

    release_reserved_stock(order, db=db, actor=current_user.full_name)
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
