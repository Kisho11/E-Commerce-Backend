# Import all models so SQLAlchemy registers them with Base.metadata
from app.models.user import User, AdminAuditLog
from app.models.address import Address
from app.models.category import Category
from app.models.product import Product, ProductImage, ProductVariantGroup, ProductVariant
from app.models.inventory import Inventory, StockMovement
from app.models.cart import Cart, CartItem
from app.models.order import Order, OrderItem
from app.models.review import Review
from app.models.task import Task

__all__ = [
    "User",
    "AdminAuditLog",
    "Address",
    "Category",
    "Product",
    "ProductImage",
    "ProductVariantGroup",
    "ProductVariant",
    "Inventory",
    "StockMovement",
    "Cart",
    "CartItem",
    "Order",
    "OrderItem",
    "Review",
    "Task",
]
