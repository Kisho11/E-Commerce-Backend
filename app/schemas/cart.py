from decimal import Decimal
from typing import List
from pydantic import BaseModel
from app.schemas.product import ProductResponse


class CartItemCreate(BaseModel):
    product_id: int
    quantity: int = 1


class CartItemUpdate(BaseModel):
    quantity: int


class CartItemResponse(BaseModel):
    id: int
    product_id: int
    quantity: int
    product: ProductResponse
    subtotal: Decimal

    model_config = {"from_attributes": True}


class CartResponse(BaseModel):
    id: int
    items: List[CartItemResponse] = []
    total: Decimal
    item_count: int

    model_config = {"from_attributes": True}
