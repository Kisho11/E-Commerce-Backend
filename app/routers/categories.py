from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy import func
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


def ensure_unique_category_name(
    db: Session,
    name: str,
    parent_id: Optional[int] = None,
    exclude_id: Optional[int] = None,
):
    query = db.query(Category).filter(
        func.lower(Category.name) == name.strip().lower(),
        Category.parent_id == parent_id,
        Category.is_active == True,
    )
    if exclude_id:
        query = query.filter(Category.id != exclude_id)
    if query.first():
        raise HTTPException(
            status_code=400,
            detail="A category with this name already exists at the same level",
        )


def serialize_category(category: Category):
    active_children = [
        child for child in sorted(category.children, key=lambda item: item.id) if child.is_active
    ]
    return {
        "id": category.id,
        "name": category.name,
        "description": category.description,
        "image_url": category.image_url,
        "parent_id": category.parent_id,
        "is_active": category.is_active,
        "slug": category.slug,
        "created_at": category.created_at,
        "children": [serialize_category(child) for child in active_children],
    }


@router.get("/", response_model=List[CategoryResponse])
def get_categories(parent_id: Optional[int] = None, db: Session = Depends(get_db)):
    query = db.query(Category).filter(Category.is_active == True)
    if parent_id is None:
        query = query.filter(Category.parent_id == None)
    else:
        query = query.filter(Category.parent_id == parent_id)
    return [serialize_category(category) for category in query.all()]


@router.get("/all", response_model=List[CategoryResponse])
def get_all_categories(db: Session = Depends(get_db)):
    categories = db.query(Category).filter(Category.is_active == True).all()
    return [serialize_category(category) for category in categories]


@router.get("/{category_id}", response_model=CategoryResponse)
def get_category(category_id: int, db: Session = Depends(get_db)):
    category = db.query(Category).filter(Category.id == category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    return serialize_category(category)


@router.post("/", response_model=CategoryResponse, status_code=201)
def create_category(
    category_data: CategoryCreate,
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    ensure_unique_category_name(db, category_data.name, category_data.parent_id)
    slug = make_unique_slug(category_data.name, db)
    category = Category(**category_data.model_dump(), slug=slug)
    db.add(category)
    db.commit()
    db.refresh(category)
    return serialize_category(category)


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
        ensure_unique_category_name(
            db,
            update_data.name,
            update_data.parent_id if update_data.parent_id is not None else category.parent_id,
            exclude_id=category_id,
        )
        category.slug = make_unique_slug(update_data.name, db, exclude_id=category_id)
    for field, value in update_data.model_dump(exclude_unset=True).items():
        setattr(category, field, value)
    db.commit()
    db.refresh(category)
    return serialize_category(category)


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
