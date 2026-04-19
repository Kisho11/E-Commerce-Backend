from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from typing import List, Optional
from slugify import slugify
from app.database import get_db
from app.models.category import Category
from app.schemas.category import CategoryCreate, CategoryUpdate, CategoryResponse
from app.core.dependencies import get_current_admin
from app.utils.file_upload import save_upload

router = APIRouter(prefix="/categories", tags=["Categories"])


def make_unique_slug(name: str, db: Session, exclude_id: int = None) -> str:
    base_slug = slugify(name)
    slug = base_slug
    counter = 1
    while True:
        query = db.query(Category).filter(Category.slug == slug)
        if exclude_id:
            query = query.filter(Category.id != exclude_id)
        if not query.first():
            break
        slug = f"{base_slug}-{counter}"
        counter += 1
    return slug


@router.get("/", response_model=List[CategoryResponse])
def get_categories(parent_id: Optional[int] = None, db: Session = Depends(get_db)):
    query = db.query(Category).filter(Category.is_active == True)
    if parent_id is None:
        query = query.filter(Category.parent_id == None)
    else:
        query = query.filter(Category.parent_id == parent_id)
    return query.all()


@router.get("/all", response_model=List[CategoryResponse])
def get_all_categories(db: Session = Depends(get_db)):
    return db.query(Category).filter(Category.is_active == True).all()


@router.get("/{category_id}", response_model=CategoryResponse)
def get_category(category_id: int, db: Session = Depends(get_db)):
    category = db.query(Category).filter(Category.id == category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    return category


@router.post("/", response_model=CategoryResponse, status_code=201)
def create_category(
    category_data: CategoryCreate,
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    slug = make_unique_slug(category_data.name, db)
    category = Category(**category_data.model_dump(), slug=slug)
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


@router.put("/{category_id}", response_model=CategoryResponse)
def update_category(
    category_id: int,
    update_data: CategoryUpdate,
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    category = db.query(Category).filter(Category.id == category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    if update_data.name:
        category.slug = make_unique_slug(update_data.name, db, exclude_id=category_id)
    for field, value in update_data.model_dump(exclude_unset=True).items():
        setattr(category, field, value)
    db.commit()
    db.refresh(category)
    return category


@router.delete("/{category_id}", status_code=204)
def delete_category(
    category_id: int,
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    category = db.query(Category).filter(Category.id == category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    category.is_active = False
    db.commit()


@router.post("/{category_id}/image")
async def upload_category_image(
    category_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    category = db.query(Category).filter(Category.id == category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    image_url = await save_upload(file, folder="categories")
    category.image_url = image_url
    db.commit()
    return {"image_url": image_url}
