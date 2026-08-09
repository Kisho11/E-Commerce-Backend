from decimal import Decimal
from typing import Iterable

from sqlalchemy.orm import Session

from app.models.category import Category
from app.models.product import Product


MONEY_QUANT = Decimal("0.01")
PICKUP_SHIPPING_FEE = Decimal("0.00")
STANDARD_SHIPPING_FEE = Decimal("30.00")
BOARDS_SHIPPING_FEE = Decimal("180.00")
BOARDS_CATEGORY_SLUG = "boards"
BOARDS_STANDARD_SHIPPING_SLUG = "inserts-corner-trims"


def _category_ancestor_slugs(category: Category, categories_by_id: dict[int, Category]) -> set[str]:
    slugs = set()
    current = category
    visited_ids = set()

    while current and current.id not in visited_ids:
        visited_ids.add(current.id)
        if current.slug:
            slugs.add(current.slug)
        current = categories_by_id.get(current.parent_id) if current.parent_id else None

    return slugs


def _product_triggers_boards_shipping(product: Product, categories_by_id: dict[int, Category]) -> bool:
    product_slugs = set()
    for category in product.categories or []:
        product_slugs.update(_category_ancestor_slugs(category, categories_by_id))

    return (
        BOARDS_CATEGORY_SLUG in product_slugs
        and BOARDS_STANDARD_SHIPPING_SLUG not in product_slugs
    )


def calculate_order_shipping_fee(
    db: Session,
    products: Iterable[Product],
    delivery_mode: str = "ship",
) -> Decimal:
    if (delivery_mode or "ship").strip().lower() == "pickup":
        return PICKUP_SHIPPING_FEE

    categories_by_id = {category.id: category for category in db.query(Category).all()}
    if any(_product_triggers_boards_shipping(product, categories_by_id) for product in products):
        return BOARDS_SHIPPING_FEE

    return STANDARD_SHIPPING_FEE
