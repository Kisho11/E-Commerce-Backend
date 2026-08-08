from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional
from pydantic import BaseModel
from app.models.order import OrderStatus, PaymentStatus
from app.schemas.address import AddressResponse


class OrderItemResponse(BaseModel):
    id: int
    product_id: int
    product_name: Optional[str] = None
    quantity: int
    unit_price: Decimal
    total_price: Decimal
    selected_attributes: Optional[Dict[str, str]] = None

    model_config = {"from_attributes": True}


class OrderCreate(BaseModel):
    address_id: int
    delivery_mode: str = "ship"
    delivery_note: Optional[str] = None
    notes: Optional[str] = None
    cart_item_ids: Optional[List[int]] = None


class OrderStatusUpdate(BaseModel):
    status: OrderStatus


class OrderResponse(BaseModel):
    id: int
    user_id: int
    status: OrderStatus
    total_amount: Decimal
    subtotal_amount: Optional[Decimal] = None
    discount_percentage: Decimal = Decimal("0")
    discount_amount: Decimal = Decimal("0")
    tax_rate: Decimal = Decimal("0")
    tax_amount: Decimal = Decimal("0")
    shipping_fee: Decimal = Decimal("0")
    payment_status: PaymentStatus
    payment_intent_id: Optional[str] = None
    delivery_mode: str = "ship"
    delivery_note: Optional[str] = None
    notes: Optional[str] = None
    address: AddressResponse
    items: List[OrderItemResponse] = []
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class OrderListResponse(BaseModel):
    items: List[OrderResponse]
    total: int
    page: int
    per_page: int
