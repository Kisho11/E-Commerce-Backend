from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.cart import Cart, CartItem
from app.models.product import Product
from app.schemas.cart import CartItemCreate, CartItemUpdate, CartResponse
from app.core.dependencies import get_current_user

router = APIRouter(prefix="/cart", tags=["Cart"])


def get_or_create_cart(user, db: Session) -> Cart:
    cart = db.query(Cart).filter(Cart.user_id == user.id).first()
    if not cart:
        cart = Cart(user_id=user.id)
        db.add(cart)
        db.commit()
        db.refresh(cart)
    return cart


def build_cart_response(cart: Cart) -> dict:
    items = []
    total = Decimal("0")
    for item in cart.items:
        price = item.product.sale_price or item.product.price
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
    existing = (
        db.query(CartItem)
        .filter(CartItem.cart_id == cart.id, CartItem.product_id == item_data.product_id)
        .first()
    )

    new_qty = (existing.quantity if existing else 0) + item_data.quantity
    if product.stock_quantity < new_qty:
        raise HTTPException(status_code=400, detail="Insufficient stock")

    if existing:
        existing.quantity = new_qty
    else:
        db.add(CartItem(cart_id=cart.id, **item_data.model_dump()))

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
        if item.product.stock_quantity < update_data.quantity:
            raise HTTPException(status_code=400, detail="Insufficient stock")
        item.quantity = update_data.quantity

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
    db.commit()
    db.refresh(cart)
    return build_cart_response(cart)


@router.delete("/", status_code=204)
def clear_cart(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    cart = get_or_create_cart(current_user, db)
    db.query(CartItem).filter(CartItem.cart_id == cart.id).delete()
    db.commit()
