from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.models.review import Review
from app.models.order import Order, OrderItem, OrderStatus
from app.schemas.review import ReviewCreate, ReviewResponse
from app.core.dependencies import get_current_user

router = APIRouter(prefix="/reviews", tags=["Reviews"])


@router.get("/product/{product_id}", response_model=List[ReviewResponse])
def get_product_reviews(
    product_id: int,
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    return (
        db.query(Review)
        .filter(Review.product_id == product_id)
        .order_by(Review.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )


@router.post("/", response_model=ReviewResponse, status_code=201)
def create_review(
    review_data: ReviewCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if (
        db.query(Review)
        .filter(
            Review.user_id == current_user.id,
            Review.product_id == review_data.product_id,
        )
        .first()
    ):
        raise HTTPException(status_code=400, detail="You have already reviewed this product")

    # Mark as verified if user has a delivered order containing this product
    has_purchased = (
        db.query(Order)
        .join(Order.items)
        .filter(
            Order.user_id == current_user.id,
            Order.status == OrderStatus.delivered,
            OrderItem.product_id == review_data.product_id,
        )
        .first()
        is not None
    )

    review = Review(
        **review_data.model_dump(),
        user_id=current_user.id,
        is_verified=has_purchased,
    )
    db.add(review)
    db.commit()
    db.refresh(review)
    return review


@router.delete("/{review_id}", status_code=204)
def delete_review(
    review_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    review = (
        db.query(Review)
        .filter(Review.id == review_id, Review.user_id == current_user.id)
        .first()
    )
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    db.delete(review)
    db.commit()
