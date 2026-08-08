from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.analytics import ProductView, SiteVisit
from app.models.product import Product


router = APIRouter(prefix="/analytics", tags=["Analytics"])

VIEW_DEDUPE_WINDOW = timedelta(minutes=30)
MAX_USER_AGENT_LENGTH = 255


class SiteVisitIn(BaseModel):
    visitor_id: str = Field(..., min_length=8, max_length=80)
    session_id: str = Field(..., min_length=8, max_length=80)
    path: str = Field("/", max_length=255)


class ProductViewIn(BaseModel):
    product_id: int = Field(..., ge=1)
    visitor_id: str = Field(..., min_length=8, max_length=80)
    session_id: str = Field(..., min_length=8, max_length=80)


def _recent_cutoff():
    return datetime.now(timezone.utc) - VIEW_DEDUPE_WINDOW


@router.post("/visit", status_code=201)
def record_site_visit(payload: SiteVisitIn, request: Request, db: Session = Depends(get_db)):
    normalized_path = (payload.path.strip() or "/")[:255]
    cutoff = _recent_cutoff()

    recent_visit = (
        db.query(SiteVisit)
        .filter(
            SiteVisit.session_id == payload.session_id,
            SiteVisit.path == normalized_path,
            SiteVisit.created_at >= cutoff,
        )
        .first()
    )
    if recent_visit:
        return {"tracked": False, "reason": "recent_duplicate"}

    user_agent = request.headers.get("user-agent") or ""
    visit = SiteVisit(
        visitor_id=payload.visitor_id,
        session_id=payload.session_id,
        path=normalized_path,
        user_agent=user_agent[:MAX_USER_AGENT_LENGTH] or None,
    )
    db.add(visit)
    db.commit()
    return {"tracked": True}


@router.post("/product-view", status_code=201)
def record_product_view(payload: ProductViewIn, db: Session = Depends(get_db)):
    product_exists = (
        db.query(Product.id)
        .filter(Product.id == payload.product_id, Product.is_active == True)
        .first()
    )
    if not product_exists:
        raise HTTPException(status_code=404, detail="Product not found")

    cutoff = _recent_cutoff()
    recent_view = (
        db.query(ProductView)
        .filter(
            ProductView.product_id == payload.product_id,
            ProductView.session_id == payload.session_id,
            ProductView.created_at >= cutoff,
        )
        .first()
    )
    if recent_view:
        return {"tracked": False, "reason": "recent_duplicate"}

    view = ProductView(
        product_id=payload.product_id,
        visitor_id=payload.visitor_id,
        session_id=payload.session_id,
    )
    db.add(view)
    db.commit()
    return {"tracked": True}
