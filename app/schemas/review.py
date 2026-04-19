from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class ReviewCreate(BaseModel):
    product_id: int
    rating: int = Field(..., ge=1, le=5)
    title: Optional[str] = None
    body: Optional[str] = None


class ReviewResponse(BaseModel):
    id: int
    user_id: int
    product_id: int
    rating: int
    title: Optional[str] = None
    body: Optional[str] = None
    is_verified: bool
    created_at: datetime

    model_config = {"from_attributes": True}
