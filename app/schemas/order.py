from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel
from app.models.order import OrderStatus, PaymentStatus
from app.schemas.address import AddressResponse


class OrderItemResponse(BaseModel):
    id: int
    product_id: int
    quantity: int
    unit_price: Decimal
    total_price: Decimal

    model_config = {"from_attributes": True}


class OrderCreate(BaseModel):
    address_id: int
    notes: Optional[str] = None


class OrderStatusUpdate(BaseModel):
    status: OrderStatus


class OrderResponse(BaseModel):
    id: int
    user_id: int
    status: OrderStatus
    total_amount: Decimal
    payment_status: PaymentStatus
    payment_intent_id: Optional[str] = None
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
