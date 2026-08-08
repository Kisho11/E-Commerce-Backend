from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class MarketingBannerResponse(BaseModel):
    id: int
    image_url: Optional[str] = None
    cta_url: str = "/catalogue"
    is_active: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
