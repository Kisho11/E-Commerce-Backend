import enum
from sqlalchemy import (
    Boolean, Column, DateTime, Enum, ForeignKey, Integer,
    JSON, Numeric, String, Table, Text, func,
)
from sqlalchemy.orm import relationship
from app.database import Base


class ProductType(str, enum.Enum):
    simple = "simple"
    variable = "variable"
    custom = "custom"


# Many-to-many: products <-> categories
product_categories = Table(
    "product_categories",
    Base.metadata,
    Column("product_id", Integer, ForeignKey("products.id", ondelete="CASCADE"), primary_key=True),
    Column("category_id", Integer, ForeignKey("categories.id", ondelete="CASCADE"), primary_key=True),
)


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    slug = Column(String, unique=True, index=True, nullable=False)
    description = Column(Text, nullable=True)
    price = Column(Numeric(10, 2), nullable=False)
    sale_price = Column(Numeric(10, 2), nullable=True)
    stock_quantity = Column(Integer, default=0)
    sku = Column(String, unique=True, nullable=True)
    product_type = Column(Enum(ProductType), default=ProductType.simple, nullable=False)
    # JSON list of industry strings e.g. ["Restaurant", "Hotel"]
    industries = Column(JSON, nullable=True, default=list)
    is_active = Column(Boolean, default=True)
    is_featured = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    categories = relationship("Category", secondary=product_categories, back_populates="products")
    images = relationship("ProductImage", back_populates="product", cascade="all, delete-orphan", order_by="ProductImage.sort_order")
    videos = relationship("ProductVideo", back_populates="product", cascade="all, delete-orphan", order_by="ProductVideo.sort_order")
    variant_groups = relationship("ProductVariantGroup", back_populates="product", cascade="all, delete-orphan")
    cart_items = relationship("CartItem", back_populates="product")
    order_items = relationship("OrderItem", back_populates="product")
    reviews = relationship("Review", back_populates="product")
    inventory = relationship("Inventory", back_populates="product", uselist=False, cascade="all, delete-orphan")


class ProductImage(Base):
    __tablename__ = "product_images"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    image_url = Column(String, nullable=False)
    is_primary = Column(Boolean, default=False)
    sort_order = Column(Integer, default=0)

    product = relationship("Product", back_populates="images")


class ProductVideo(Base):
    __tablename__ = "product_videos"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    video_url = Column(String, nullable=False)
    sort_order = Column(Integer, default=0)

    product = relationship("Product", back_populates="videos")


class ProductVariantGroup(Base):
    __tablename__ = "product_variant_groups"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    attribute = Column(String, nullable=False)  # e.g. "Color", "Size"

    product = relationship("Product", back_populates="variant_groups")
    variants = relationship("ProductVariant", back_populates="group", cascade="all, delete-orphan")


class ProductVariant(Base):
    __tablename__ = "product_variants"

    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey("product_variant_groups.id", ondelete="CASCADE"), nullable=False)
    value = Column(String, nullable=False)        # e.g. "Red", "Large"
    price_modifier = Column(Numeric(10, 2), default=0)
    stock_quantity = Column(Integer, default=0)
    sku_suffix = Column(String, nullable=True)

    group = relationship("ProductVariantGroup", back_populates="variants")
