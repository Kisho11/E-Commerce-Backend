from decimal import Decimal
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.cart import Cart, CartItem
from app.models.product import Product
from app.schemas.cart import CartItemCreate, CartItemUpdate, CartResponse
from app.core.dependencies import get_current_user
from app.utils.variant_pricing import (
    normalize_attributes,
    normalize_product_attributes,
    resolve_product_unit_price,
)

router = APIRouter(prefix="/cart", tags=["Cart"])


def mark_cart_activity(cart: Cart) -> None:
    cart.updated_at = datetime.now(timezone.utc)


def get_or_create_cart(user, db: Session) -> Cart:
    cart = db.query(Cart).filter(Cart.user_id == user.id).first()
    if not cart:
        cart = Cart(user_id=user.id)
        db.add(cart)
        db.commit()
        db.refresh(cart)
    return cart


def cart_item_matches(item: CartItem, product_id: int, selected_attributes: dict) -> bool:
    return (
        item.product_id == product_id
        and normalize_attributes(item.selected_attributes or {}) == selected_attributes
    )


def build_cart_response(cart: Cart) -> dict:
    items = []
    total = Decimal("0")
    for item in cart.items:
        selected_attributes = normalize_attributes(item.selected_attributes or {})
        price = resolve_product_unit_price(item.product, selected_attributes)
        subtotal = price * item.quantity
        total += subtotal
        # Attach computed fields not on the model
        item.avg_rating = None
        item.review_count = 0
        items.append(
            {
                "id": item.id,
                "product_id": item.product_id,
                "quantity": item.quantity,
                "selected_attributes": selected_attributes,
                "unit_price": price,
                "product": item.product,
                "subtotal": subtotal,
            }
        )
    return {"id": cart.id, "items": items, "total": total, "item_count": len(items)}


@router.get("/", response_model=CartResponse)
def get_cart(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    cart = get_or_create_cart(current_user, db)
    return build_cart_response(cart)


@router.post("/items", response_model=CartResponse, status_code=201)
def add_to_cart(
    item_data: CartItemCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    product = (
        db.query(Product)
        .filter(Product.id == item_data.product_id, Product.is_active == True)
        .first()
    )
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    cart = get_or_create_cart(current_user, db)
    selected_attributes = normalize_product_attributes(product, item_data.selected_attributes or {})
    existing = next(
        (
            item
            for item in cart.items
            if cart_item_matches(item, item_data.product_id, selected_attributes)
        ),
        None,
    )

    new_qty = (existing.quantity if existing else 0) + item_data.quantity
    if product.stock_quantity > 0 and product.stock_quantity < new_qty:
        raise HTTPException(status_code=400, detail="Insufficient stock")

    if existing:
        existing.quantity = new_qty
    else:
        db.add(
            CartItem(
                cart_id=cart.id,
                product_id=item_data.product_id,
                quantity=item_data.quantity,
                selected_attributes=selected_attributes or None,
            )
        )
    mark_cart_activity(cart)

    db.commit()
    db.refresh(cart)
    return build_cart_response(cart)


@router.put("/items/{item_id}", response_model=CartResponse)
def update_cart_item(
    item_id: int,
    update_data: CartItemUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    cart = get_or_create_cart(current_user, db)
    item = (
        db.query(CartItem)
        .filter(CartItem.id == item_id, CartItem.cart_id == cart.id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Cart item not found")

    if update_data.quantity <= 0:
        db.delete(item)
    else:
        if item.product.stock_quantity > 0 and item.product.stock_quantity < update_data.quantity:
            raise HTTPException(status_code=400, detail="Insufficient stock")
        item.quantity = update_data.quantity
    mark_cart_activity(cart)

    db.commit()
    db.refresh(cart)
    return build_cart_response(cart)


@router.delete("/items/{item_id}", response_model=CartResponse)
def remove_cart_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    cart = get_or_create_cart(current_user, db)
    item = (
        db.query(CartItem)
        .filter(CartItem.id == item_id, CartItem.cart_id == cart.id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Cart item not found")
    db.delete(item)
    mark_cart_activity(cart)
    db.commit()
    db.refresh(cart)
    return build_cart_response(cart)


@router.delete("/", status_code=204)
def clear_cart(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    cart = get_or_create_cart(current_user, db)
    db.query(CartItem).filter(CartItem.cart_id == cart.id).delete()
    mark_cart_activity(cart)
    db.commit()
