from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel


class ProductImageResponse(BaseModel):
    id: int
    image_url: str
    is_primary: bool
    sort_order: int

    model_config = {"from_attributes": True}


class ProductBase(BaseModel):
    name: str
    description: Optional[str] = None
    price: Decimal
    sale_price: Optional[Decimal] = None
    stock_quantity: int = 0
    sku: Optional[str] = None
    category_id: int
    is_active: bool = True
    is_featured: bool = False


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[Decimal] = None
    sale_price: Optional[Decimal] = None
    stock_quantity: Optional[int] = None
    sku: Optional[str] = None
    category_id: Optional[int] = None
    is_active: Optional[bool] = None
    is_featured: Optional[bool] = None


class ProductResponse(ProductBase):
    id: int
    slug: str
    images: List[ProductImageResponse] = []
    avg_rating: Optional[float] = None
    review_count: int = 0
    created_at: datetime

    model_config = {"from_attributes": True}


class ProductListResponse(BaseModel):
    items: List[ProductResponse]
    total: int
    page: int
    per_page: int
    pages: int
