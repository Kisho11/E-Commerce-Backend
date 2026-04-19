from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel
from app.models.product import ProductType


class ProductImageResponse(BaseModel):
    id: int
    image_url: str
    is_primary: bool
    sort_order: int

    model_config = {"from_attributes": True}


class ProductVideoResponse(BaseModel):
    id: int
    video_url: str
    sort_order: int

    model_config = {"from_attributes": True}


class ProductVariantBase(BaseModel):
    value: str
    price_modifier: Decimal = Decimal("0")
    stock_quantity: int = 0
    sku_suffix: Optional[str] = None


class ProductVariantCreate(ProductVariantBase):
    pass


class ProductVariantResponse(ProductVariantBase):
    id: int

    model_config = {"from_attributes": True}


class ProductVariantGroupBase(BaseModel):
    attribute: str


class ProductVariantGroupCreate(ProductVariantGroupBase):
    variants: List[ProductVariantCreate] = []


class ProductVariantGroupResponse(ProductVariantGroupBase):
    id: int
    variants: List[ProductVariantResponse] = []

    model_config = {"from_attributes": True}


class CategorySlim(BaseModel):
    id: int
    name: str
    slug: str

    model_config = {"from_attributes": True}


class ProductBase(BaseModel):
    name: str
    description: Optional[str] = None
    price: Decimal
    sale_price: Optional[Decimal] = None
    stock_quantity: int = 0
    sku: Optional[str] = None
    product_type: ProductType = ProductType.simple
    industries: Optional[List[str]] = None
    is_active: bool = True
    is_featured: bool = False


class ProductCreate(ProductBase):
    category_ids: List[int] = []
    variant_groups: List[ProductVariantGroupCreate] = []


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[Decimal] = None
    sale_price: Optional[Decimal] = None
    stock_quantity: Optional[int] = None
    sku: Optional[str] = None
    product_type: Optional[ProductType] = None
    industries: Optional[List[str]] = None
    category_ids: Optional[List[int]] = None
    is_active: Optional[bool] = None
    is_featured: Optional[bool] = None
    variant_groups: Optional[List[ProductVariantGroupCreate]] = None


class ProductResponse(ProductBase):
    id: int
    slug: str
    categories: List[CategorySlim] = []
    images: List[ProductImageResponse] = []
    videos: List[ProductVideoResponse] = []
    variant_groups: List[ProductVariantGroupResponse] = []
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
