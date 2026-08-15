# Import all models so SQLAlchemy registers them with Base.metadata
from app.models.user import User, AdminAuditLog
from app.models.address import Address
from app.models.category import Category
from app.models.industry import Industry
from app.models.product import Product, ProductImage, ProductRelatedProduct, ProductVariantGroup, ProductVariant
from app.models.inventory import Inventory, StockMovement, VariantInventory, VariantStockMovement
from app.models.cart import Cart, CartItem
from app.models.order import Order, OrderItem
from app.models.review import Review
from app.models.task import Task
from app.models.analytics import ProductView, SiteVisit
from app.models.marketing import MarketingBanner, MarketingEmailCampaign, NewsletterSubscriber

__all__ = [
    "User",
    "AdminAuditLog",
    "Address",
    "Category",
    "Industry",
    "Product",
    "ProductImage",
    "ProductRelatedProduct",
    "ProductVariantGroup",
    "ProductVariant",
    "Inventory",
    "StockMovement",
    "VariantInventory",
    "VariantStockMovement",
    "Cart",
    "CartItem",
    "Order",
    "OrderItem",
    "Review",
    "Task",
    "ProductView",
    "SiteVisit",
    "MarketingBanner",
    "MarketingEmailCampaign",
    "NewsletterSubscriber",
]
