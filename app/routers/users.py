import secrets
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session
from typing import List
from app.config import settings
from app.database import get_db
from app.models.address import Address
from app.models.cart import Cart
from app.models.review import Review
from app.models.user import UserRole
from app.schemas.user import UserResponse, UserUpdate
from app.schemas.address import AddressCreate, AddressUpdate, AddressResponse
from app.core.dependencies import get_current_user
from app.core.security import hash_password

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/me", response_model=UserResponse)
def get_profile(current_user=Depends(get_current_user)):
    return current_user


@router.put("/me", response_model=UserResponse)
def update_profile(
    update_data: UserUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    for field, value in update_data.model_dump(exclude_unset=True).items():
        setattr(current_user, field, value)
    db.commit()
    db.refresh(current_user)
    return current_user


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_my_account(
    response: Response,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if current_user.role != UserRole.user:
        raise HTTPException(status_code=403, detail="Only customer accounts can be deleted from the customer portal")

    deleted_at = datetime.now(timezone.utc)
    anonymized_email = f"deleted-user-{current_user.id}-{int(deleted_at.timestamp())}@deleted.local"

    cart = db.query(Cart).filter(Cart.user_id == current_user.id).first()
    if cart:
        db.delete(cart)

    db.query(Review).filter(Review.user_id == current_user.id).delete(synchronize_session=False)

    for address in db.query(Address).filter(Address.user_id == current_user.id).all():
        address.full_name = "Deleted Customer"
        address.phone = "Deleted"
        address.address_line1 = "Deleted address"
        address.address_line2 = None
        address.city = "Deleted"
        address.state = "Deleted"
        address.postal_code = "Deleted"
        address.country = "Deleted"
        address.is_default = False

    current_user.email = anonymized_email
    current_user.full_name = "Deleted Customer"
    current_user.phone = None
    current_user.hashed_password = hash_password(secrets.token_urlsafe(32))
    current_user.is_active = False
    current_user.is_email_verified = False
    current_user.must_reset_password = False
    current_user.token_version += 1

    db.commit()

    response.delete_cookie(settings.ACCESS_TOKEN_COOKIE_NAME, path="/")
    response.delete_cookie(settings.REFRESH_TOKEN_COOKIE_NAME, path="/api/v1/auth")
    response.delete_cookie(settings.CSRF_COOKIE_NAME, path="/", domain=settings.COOKIE_DOMAIN)


@router.get("/me/addresses", response_model=List[AddressResponse])
def get_addresses(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    return db.query(Address).filter(Address.user_id == current_user.id).all()


@router.post("/me/addresses", response_model=AddressResponse, status_code=201)
def create_address(
    address_data: AddressCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if address_data.is_default:
        db.query(Address).filter(Address.user_id == current_user.id).update(
            {"is_default": False}
        )
    address = Address(**address_data.model_dump(), user_id=current_user.id)
    db.add(address)
    db.commit()
    db.refresh(address)
    return address


@router.put("/me/addresses/{address_id}", response_model=AddressResponse)
def update_address(
    address_id: int,
    update_data: AddressUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    address = (
        db.query(Address)
        .filter(Address.id == address_id, Address.user_id == current_user.id)
        .first()
    )
    if not address:
        raise HTTPException(status_code=404, detail="Address not found")
    if update_data.is_default:
        db.query(Address).filter(Address.user_id == current_user.id).update(
            {"is_default": False}
        )
    for field, value in update_data.model_dump(exclude_unset=True).items():
        setattr(address, field, value)
    db.commit()
    db.refresh(address)
    return address


@router.delete("/me/addresses/{address_id}", status_code=204)
def delete_address(
    address_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    address = (
        db.query(Address)
        .filter(Address.id == address_id, Address.user_id == current_user.id)
        .first()
    )
    if not address:
        raise HTTPException(status_code=404, detail="Address not found")
    db.delete(address)
    db.commit()
