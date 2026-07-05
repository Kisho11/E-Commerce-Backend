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
            try:
                attributes = normalize_attributes(json.loads(variant.sku_suffix or "{}"))
            except (TypeError, json.JSONDecodeError):
                attributes = {}

            if not attributes:
                continue

            if all(selected.get(attribute) == value for attribute, value in attributes.items()):
                matches.append((len(attributes), Decimal(product.price or 0) + Decimal(variant.price_modifier or 0)))

    if not matches:
        return base_price

    return sorted(matches, key=lambda match: match[0], reverse=True)[0][1]
