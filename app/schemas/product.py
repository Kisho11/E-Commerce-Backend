from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import List, Optional
from pydantic import BaseModel, field_validator
from app.models.product import ProductType

MONEY_QUANT = Decimal("0.01")


def validate_money_scale(value: Optional[Decimal], field_label: str, allow_negative: bool = False) -> Optional[Decimal]:
    if value is None:
        return value

    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field_label} must be a valid amount")

    if not allow_negative and amount < 0:
        raise ValueError(f"{field_label} cannot be negative")

    if amount != amount.quantize(MONEY_QUANT):
        raise ValueError(f"{field_label} must have no more than 2 decimal places")

    return amount


class ProductImageResponse(BaseModel):
    id: int
    image_url: str
    is_primary: bool
    sort_order: int
    variant_tag: Optional[str] = None

    model_config = {"from_attributes": True}


class ProductVariantBase(BaseModel):
    value: str
    price_modifier: Decimal = Decimal("0")
    stock_quantity: int = 0
    sku_suffix: Optional[str] = None

    @field_validator("price_modifier")
    @classmethod
    def validate_price_modifier(cls, value):
        return validate_money_scale(value, "Variant price modifier", allow_negative=True)


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
    parent_id: Optional[int] = None

    model_config = {"from_attributes": True}


class ProductBase(BaseModel):
    name: str
    description: Optional[str] = None
    main_note: Optional[str] = None
    key_features: Optional[str] = None
    whats_included: Optional[str] = None
    important_notes: Optional[str] = None
    additional_information: Optional[str] = None
    price: Decimal
    sale_price: Optional[Decimal] = None
    stock_quantity: int = 0
    sku: Optional[str] = None
    product_type: Optional[ProductType] = None
    industries: Optional[List[str]] = None
    is_active: bool = True
    is_featured: bool = False

    @field_validator("price")
    @classmethod
    def validate_price(cls, value):
        return validate_money_scale(value, "Price")

    @field_validator("sale_price")
    @classmethod
    def validate_sale_price(cls, value):
        return validate_money_scale(value, "Sale price")


class ProductCreate(ProductBase):
    category_ids: List[int] = []
    variant_groups: List[ProductVariantGroupCreate] = []
    related_product_ids: List[int] = []


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    main_note: Optional[str] = None
    key_features: Optional[str] = None
    whats_included: Optional[str] = None
    important_notes: Optional[str] = None
    additional_information: Optional[str] = None
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
    related_product_ids: Optional[List[int]] = None

    @field_validator("price")
    @classmethod
    def validate_price(cls, value):
        return validate_money_scale(value, "Price")

    @field_validator("sale_price")
    @classmethod
    def validate_sale_price(cls, value):
        return validate_money_scale(value, "Sale price")


class ProductResponse(ProductBase):
    id: int
    slug: str
    categories: List[CategorySlim] = []
    images: List[ProductImageResponse] = []
    variant_groups: List[ProductVariantGroupResponse] = []
    related_product_ids: List[int] = []
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
