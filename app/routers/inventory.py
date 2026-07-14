import json
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import String, cast, func, or_
from typing import List, Optional
from app.database import get_db
from app.models.inventory import Inventory, StockMovement, MovementType, VariantInventory, VariantStockMovement
from app.models.product import Product, ProductVariant, ProductVariantGroup, ProductType
from app.schemas.inventory import (
    InventoryResponse, InventoryUpdate, StockAdjustRequest,
    StockMovementResponse, InventorySummary, VariantInventoryResponse,
)
from app.core.dependencies import get_current_manager

router = APIRouter(prefix="/inventory", tags=["Inventory"])


def _is_option_meta(sku_suffix: str | None) -> bool:
    if not sku_suffix:
        return False
    try:
        parsed = json.loads(sku_suffix)
    except (TypeError, ValueError, json.JSONDecodeError):
        return False
    return bool(isinstance(parsed, dict) and parsed.get("__option"))


def _stock_variants_for_product(product: Product) -> list[ProductVariant]:
    groups = product.variant_groups or []
    combination_groups = [group for group in groups if group.attribute == "Combination"]
    stock_groups = combination_groups or groups
    variants = []
    for group in stock_groups:
        for variant in group.variants or []:
            if not _is_option_meta(variant.sku_suffix):
                variants.append(variant)
    return variants


def _get_or_create_variant_inventory(variant_id: int, db: Session) -> VariantInventory:
    inv = db.query(VariantInventory).filter(VariantInventory.variant_id == variant_id).first()
    if inv:
        return inv

    variant = (
        db.query(ProductVariant)
        .options(joinedload(ProductVariant.group).joinedload(ProductVariantGroup.product))
        .filter(ProductVariant.id == variant_id)
        .first()
    )
    if not variant or not variant.group or not variant.group.product:
        raise HTTPException(status_code=404, detail="Variant not found")

    product = variant.group.product
    parent_inv = db.query(Inventory).filter(Inventory.product_id == product.id).first()
    inv = VariantInventory(
        product_id=product.id,
        variant_id=variant.id,
        on_hand=int(variant.stock_quantity or 0),
        reserved=0,
        reorder_level=parent_inv.reorder_level if parent_inv else 10,
        reorder_qty=parent_inv.reorder_qty if parent_inv else 50,
        avg_daily_usage=parent_inv.avg_daily_usage if parent_inv else 0,
        location=parent_inv.location if parent_inv else None,
        supplier=parent_inv.supplier if parent_inv else None,
        lead_time_days=parent_inv.lead_time_days if parent_inv else 7,
    )
    db.add(inv)
    db.flush()
    return inv


def _ensure_variant_inventory_for_active_products(db: Session) -> None:
    products = (
        db.query(Product)
        .options(joinedload(Product.variant_groups).joinedload(ProductVariantGroup.variants))
        .filter(Product.is_active == True, Product.product_type == ProductType.variable)
        .all()
    )
    changed = False
    for product in products:
        for variant in _stock_variants_for_product(product):
            existing = db.query(VariantInventory.id).filter(VariantInventory.variant_id == variant.id).first()
            if existing:
                continue
            _get_or_create_variant_inventory(variant.id, db)
            changed = True
    if changed:
        db.commit()


def _get_or_create_inventory(product_id: int, db: Session) -> Inventory:
    inv = db.query(Inventory).filter(Inventory.product_id == product_id).first()
    if not inv:
        product = db.query(Product).filter(Product.id == product_id).first()
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")
        inv = Inventory(product_id=product_id, on_hand=product.stock_quantity)
        db.add(inv)
        db.commit()
        db.refresh(inv)
    return inv


def _ensure_inventory_for_active_products(db: Session) -> None:
    missing_products = (
        db.query(Product)
        .outerjoin(Inventory, Inventory.product_id == Product.id)
        .filter(Product.is_active == True, Inventory.id == None)
        .all()
    )
    if not missing_products:
        return

    for product in missing_products:
        db.add(Inventory(product_id=product.id, on_hand=product.stock_quantity or 0))
    db.commit()


@router.get("/", response_model=List[InventoryResponse])
def list_inventory(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=2000),
    status: Optional[str] = Query(None, description="Healthy | Low Stock | Out of Stock"),
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    user=Depends(get_current_manager),
):
    _ensure_inventory_for_active_products(db)

    q = (
        db.query(Inventory)
        .join(Product)
        .options(joinedload(Inventory.product))
        .filter(Product.is_active == True)
    )

    if search:
        for term in search.strip().split():
            pattern = f"%{term}%"
            q = q.filter(
                or_(
                    Product.name.ilike(pattern),
                    cast(Product.id, String).ilike(pattern),
                    Inventory.location.ilike(pattern),
                    Inventory.supplier.ilike(pattern),
                )
            )

    if status:
        if status == "Healthy":
            q = q.filter(Inventory.on_hand > Inventory.reorder_level)
        elif status == "Low Stock":
            q = q.filter(Inventory.on_hand > 0, Inventory.on_hand <= Inventory.reorder_level)
        elif status == "Out of Stock":
            q = q.filter(Inventory.on_hand <= 0)

    records = q.order_by(Product.name.asc()).offset((page - 1) * per_page).limit(per_page).all()

    return records


@router.get("/summary", response_model=InventorySummary)
def inventory_summary(db: Session = Depends(get_db), user=Depends(get_current_manager)):
    _ensure_inventory_for_active_products(db)
    all_inv = db.query(Inventory).join(Product).filter(Product.is_active == True).all()
    low = [i for i in all_inv if i.on_hand > 0 and i.on_hand <= i.reorder_level]
    out = [i for i in all_inv if i.on_hand <= 0]
    healthy = [i for i in all_inv if i.on_hand > i.reorder_level]
    total_on_hand = sum(i.on_hand for i in all_inv)

    return InventorySummary(
        total_products=len(all_inv),
        low_stock_count=len(low),
        out_of_stock_count=len(out),
        healthy_count=len(healthy),
        total_on_hand=total_on_hand,
    )


@router.get("/movements", response_model=List[StockMovementResponse])
def list_movements(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    product_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    user=Depends(get_current_manager),
):
    q = db.query(StockMovement).order_by(StockMovement.created_at.desc())
    if product_id:
        q = q.filter(StockMovement.product_id == product_id)
    return q.offset((page - 1) * per_page).limit(per_page).all()


@router.get("/variants", response_model=List[VariantInventoryResponse])
def list_variant_inventory(
    page: int = Query(1, ge=1),
    per_page: int = Query(200, ge=1, le=2000),
    status: Optional[str] = Query(None, description="Healthy | Low Stock | Out of Stock"),
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    user=Depends(get_current_manager),
):
    _ensure_variant_inventory_for_active_products(db)

    q = (
        db.query(VariantInventory)
        .join(Product, VariantInventory.product_id == Product.id)
        .join(ProductVariant, VariantInventory.variant_id == ProductVariant.id)
        .options(
            joinedload(VariantInventory.product),
            joinedload(VariantInventory.variant),
            joinedload(VariantInventory.movements),
        )
        .filter(Product.is_active == True)
    )

    if search:
        for term in search.strip().split():
            pattern = f"%{term}%"
            q = q.filter(
                or_(
                    Product.name.ilike(pattern),
                    ProductVariant.value.ilike(pattern),
                    ProductVariant.sku_suffix.ilike(pattern),
                    cast(Product.id, String).ilike(pattern),
                    cast(ProductVariant.id, String).ilike(pattern),
                    VariantInventory.location.ilike(pattern),
                    VariantInventory.supplier.ilike(pattern),
                )
            )

    records = q.order_by(Product.name.asc(), ProductVariant.value.asc()).all()
    if status:
        records = [record for record in records if record.status == status]

    start = (page - 1) * per_page
    return records[start:start + per_page]


@router.get("/variants/{variant_id}", response_model=VariantInventoryResponse)
def get_variant_inventory(variant_id: int, db: Session = Depends(get_db), user=Depends(get_current_manager)):
    inv = _get_or_create_variant_inventory(variant_id, db)
    db.commit()
    db.refresh(inv)
    return inv


@router.patch("/variants/{variant_id}", response_model=VariantInventoryResponse)
def update_variant_inventory_settings(
    variant_id: int,
    body: InventoryUpdate,
    db: Session = Depends(get_db),
    user=Depends(get_current_manager),
):
    inv = _get_or_create_variant_inventory(variant_id, db)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(inv, field, value)
    db.commit()
    db.refresh(inv)
    return inv


@router.post("/variants/{variant_id}/adjust", response_model=VariantInventoryResponse)
def adjust_variant_stock(
    variant_id: int,
    body: StockAdjustRequest,
    db: Session = Depends(get_db),
    user=Depends(get_current_manager),
):
    inv = _get_or_create_variant_inventory(variant_id, db)
    qty_before = inv.on_hand
    new_qty = inv.on_hand + body.change
    if new_qty < 0:
        raise HTTPException(status_code=400, detail="Stock cannot go below zero")

    inv.on_hand = new_qty
    variant = db.query(ProductVariant).filter(ProductVariant.id == variant_id).first()
    if variant:
        variant.stock_quantity = new_qty

    movement = VariantStockMovement(
        inventory_id=inv.id,
        product_id=inv.product_id,
        variant_id=variant_id,
        movement_type=body.movement_type,
        qty_change=body.change,
        qty_before=qty_before,
        qty_after=new_qty,
        reason=body.reason,
        actor=body.actor or user.full_name,
    )
    db.add(movement)
    db.commit()
    db.refresh(inv)
    return inv


@router.get("/{product_id}", response_model=InventoryResponse)
def get_inventory(product_id: int, db: Session = Depends(get_db), user=Depends(get_current_manager)):
    return _get_or_create_inventory(product_id, db)


@router.patch("/{product_id}", response_model=InventoryResponse)
def update_inventory_settings(
    product_id: int,
    body: InventoryUpdate,
    db: Session = Depends(get_db),
    user=Depends(get_current_manager),
):
    inv = _get_or_create_inventory(product_id, db)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(inv, field, value)
    db.commit()
    db.refresh(inv)
    return inv


@router.post("/{product_id}/adjust", response_model=InventoryResponse)
def adjust_stock(
    product_id: int,
    body: StockAdjustRequest,
    db: Session = Depends(get_db),
    user=Depends(get_current_manager),
):
    inv = _get_or_create_inventory(product_id, db)
    qty_before = inv.on_hand
    new_qty = inv.on_hand + body.change
    if new_qty < 0:
        raise HTTPException(status_code=400, detail="Stock cannot go below zero")

    inv.on_hand = new_qty

    movement = StockMovement(
        inventory_id=inv.id,
        product_id=product_id,
        movement_type=body.movement_type,
        qty_change=body.change,
        qty_before=qty_before,
        qty_after=new_qty,
        reason=body.reason,
        actor=body.actor or user.full_name,
    )
    db.add(movement)

    # Keep product.stock_quantity in sync
    product = db.query(Product).filter(Product.id == product_id).first()
    if product:
        product.stock_quantity = new_qty

    db.commit()
    db.refresh(inv)
    return inv
