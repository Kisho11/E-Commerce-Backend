from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from app.database import get_db
from app.models.inventory import Inventory, StockMovement, MovementType
from app.models.product import Product
from app.schemas.inventory import (
    InventoryResponse, InventoryUpdate, StockAdjustRequest,
    StockMovementResponse, InventorySummary,
)
from app.core.dependencies import get_current_manager

router = APIRouter(prefix="/inventory", tags=["Inventory"])


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


@router.get("/", response_model=List[InventoryResponse])
def list_inventory(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    status: Optional[str] = Query(None, description="Healthy | Low Stock | Out of Stock"),
    db: Session = Depends(get_db),
    user=Depends(get_current_manager),
):
    q = db.query(Inventory).join(Product).filter(Product.is_active == True)
    records = q.offset((page - 1) * per_page).limit(per_page).all()

    if status:
        records = [r for r in records if r.status == status]

    return records


@router.get("/summary", response_model=InventorySummary)
def inventory_summary(db: Session = Depends(get_db), user=Depends(get_current_manager)):
    all_inv = db.query(Inventory).all()
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
