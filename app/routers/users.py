from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.models.address import Address
from app.schemas.user import UserResponse, UserUpdate
from app.schemas.address import AddressCreate, AddressUpdate, AddressResponse
from app.core.dependencies import get_current_user

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
