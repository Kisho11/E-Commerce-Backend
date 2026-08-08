from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel


class MarketingBannerResponse(BaseModel):
    id: int
    image_url: Optional[str] = None
    cta_url: str = "/catalogue"
    is_active: bool = False
    global_discount_percentage: Decimal = Decimal("0")
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class MarketingSettingsResponse(BaseModel):
    global_discount_percentage: Decimal = Decimal("0")


class MarketingSettingsUpdate(BaseModel):
    global_discount_percentage: Decimal = Decimal("0")
