import json
from decimal import Decimal


def normalize_attributes(attributes):
    if not isinstance(attributes, dict):
        return {}

    return {
        str(key).strip(): str(value).strip()
        for key, value in attributes.items()
        if str(key or "").strip() and str(value or "").strip()
    }


def get_product_attribute_options(product):
    options = {}
    for group in product.variant_groups or []:
        if group.attribute == "Combination":
            for variant in group.variants or []:
                try:
                    attributes = normalize_attributes(json.loads(variant.sku_suffix or "{}"))
                except (TypeError, json.JSONDecodeError):
                    attributes = {}
                for attribute, value in attributes.items():
                    options.setdefault(attribute, set()).add(value)
            continue

        attribute = str(group.attribute or "").strip()
        if not attribute:
            continue
        for variant in group.variants or []:
            value = str(variant.value or "").strip()
            if value:
                options.setdefault(attribute, set()).add(value)

    return options


def normalize_product_attributes(product, attributes):
    selected = normalize_attributes(attributes)
    options = get_product_attribute_options(product)
    if not options:
        return selected

    return {
        attribute: value
        for attribute, value in selected.items()
        if value in options.get(attribute, set())
    }


def get_product_type_value(product):
    product_type = getattr(product, "product_type", None)
    return getattr(product_type, "value", product_type)


def get_variant_attributes(variant):
    try:
        return normalize_attributes(json.loads(variant.sku_suffix or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def find_stock_variant(product, selected_attributes=None):
    selected = normalize_attributes(selected_attributes)
    if get_product_type_value(product) != "variable":
        return None

    # Combination variants are the stock-bearing SKU rows for variable products.
    for group in product.variant_groups or []:
        if group.attribute != "Combination":
            continue
        for variant in group.variants or []:
            attributes = get_variant_attributes(variant)
            if attributes and attributes == selected:
                return variant

    # Fallback for older products that were stored as a single variant group.
    if len(selected) == 1:
        selected_attribute, selected_value = next(iter(selected.items()))
        for group in product.variant_groups or []:
            if group.attribute != selected_attribute:
                continue
            for variant in group.variants or []:
                if str(variant.value or "").strip() == selected_value:
                    return variant

    return None


def get_stock_quantity(product, selected_attributes=None):
    product_type = get_product_type_value(product)
    if product_type == "custom":
        return None

    stock_variant = find_stock_variant(product, selected_attributes)
    if stock_variant is not None:
        return int(stock_variant.stock_quantity or 0)

    if product_type == "variable":
        return 0

    return int(product.stock_quantity or 0)


def ensure_stock_available(product, selected_attributes, requested_quantity):
    stock_quantity = get_stock_quantity(product, selected_attributes)
    if stock_quantity is None:
        return

    if stock_quantity < int(requested_quantity or 0):
        raise ValueError("Insufficient stock")


def adjust_stock_quantity(
    product,
    selected_attributes,
    quantity_delta,
    db=None,
    movement_type=None,
    reason=None,
    actor=None,
):
    product_type = get_product_type_value(product)
    stock_variant = find_stock_variant(product, selected_attributes)
    if stock_variant is not None:
        qty_before = int(stock_variant.stock_quantity or 0)
        qty_after = max(0, qty_before + int(quantity_delta or 0))
        stock_variant.stock_quantity = qty_after
        if db is not None:
            from app.models.inventory import MovementType, VariantInventory, VariantStockMovement

            inv = db.query(VariantInventory).filter(VariantInventory.variant_id == stock_variant.id).first()
            if not inv:
                inv = VariantInventory(
                    product_id=product.id,
                    variant_id=stock_variant.id,
                    on_hand=qty_before,
                )
                db.add(inv)
                db.flush()

            inv_before = int(inv.on_hand or 0)
            inv_after = max(0, inv_before + int(quantity_delta or 0))
            inv.on_hand = inv_after
            db.add(
                VariantStockMovement(
                    inventory_id=inv.id,
                    product_id=product.id,
                    variant_id=stock_variant.id,
                    movement_type=movement_type or MovementType.adjustment,
                    qty_change=int(quantity_delta or 0),
                    qty_before=inv_before,
                    qty_after=inv_after,
                    reason=reason,
                    actor=actor,
                )
            )
        return stock_variant.stock_quantity

    if product_type == "variable":
        return 0

    product.stock_quantity = max(0, int(product.stock_quantity or 0) + int(quantity_delta or 0))
    return product.stock_quantity


def resolve_product_unit_price(product, selected_attributes=None):
    selected = normalize_attributes(selected_attributes)
    base_price = Decimal(product.sale_price or product.price or 0)

    if not selected:
        return base_price

    matches = []
    for group in product.variant_groups or []:
        if group.attribute != "Combination":
            continue

        for variant in group.variants or []:
            attributes = get_variant_attributes(variant)

            if not attributes:
                continue

            if all(selected.get(attribute) == value for attribute, value in attributes.items()):
                matches.append((len(attributes), Decimal(product.price or 0) + Decimal(variant.price_modifier or 0)))

    if not matches:
        return base_price

    return sorted(matches, key=lambda match: match[0], reverse=True)[0][1]
