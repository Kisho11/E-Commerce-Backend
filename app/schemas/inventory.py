from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel
from app.models.inventory import MovementType


class StockAdjustRequest(BaseModel):
    change: int
    reason: Optional[str] = None
    actor: Optional[str] = None
    movement_type: MovementType = MovementType.adjustment


class StockMovementResponse(BaseModel):
    id: int
    product_id: int
    movement_type: MovementType
    qty_change: int
    qty_before: int
    qty_after: int
    reason: Optional[str]
    actor: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class VariantStockMovementResponse(StockMovementResponse):
    variant_id: int


class InventoryResponse(BaseModel):
    id: int
    product_id: int
    product_name: Optional[str] = None
    on_hand: int
    reserved: int
    available: int
    reorder_level: int
    reorder_qty: int
    avg_daily_usage: Optional[Decimal]
    location: Optional[str]
    supplier: Optional[str]
    lead_time_days: int
    status: str
    coverage_days: Optional[int]
    updated_at: Optional[datetime]
    movements: List[StockMovementResponse] = []

    model_config = {"from_attributes": True}


class VariantInventoryResponse(BaseModel):
    id: int
    product_id: int
    variant_id: int
    product_name: Optional[str] = None
    variant_label: Optional[str] = None
    on_hand: int
    reserved: int
    available: int
    reorder_level: int
    reorder_qty: int
    avg_daily_usage: Optional[Decimal]
    location: Optional[str]
    supplier: Optional[str]
    lead_time_days: int
    status: str
    coverage_days: Optional[int]
    updated_at: Optional[datetime]
    movements: List[VariantStockMovementResponse] = []

    model_config = {"from_attributes": True}


class InventoryUpdate(BaseModel):
    reorder_level: Optional[int] = None
    reorder_qty: Optional[int] = None
    avg_daily_usage: Optional[Decimal] = None
    location: Optional[str] = None
    supplier: Optional[str] = None
    lead_time_days: Optional[int] = None


class InventorySummary(BaseModel):
    total_products: int
    low_stock_count: int
    out_of_stock_count: int
    healthy_count: int
    total_on_hand: int
