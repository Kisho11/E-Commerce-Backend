from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from typing import List, Optional
from slugify import slugify
from app.database import get_db
from app.models.product import Product, ProductImage
from app.models.review import Review
from app.schemas.product import ProductCreate, ProductUpdate, ProductResponse, ProductListResponse
from app.core.dependencies import get_current_admin
from app.utils.file_upload import save_upload

router = APIRouter(prefix="/products", tags=["Products"])

SORTABLE_FIELDS = {"price", "created_at", "name"}


def make_unique_slug(name: str, db: Session, exclude_id: int = None) -> str:
    base_slug = slugify(name)
    slug = base_slug
    counter = 1
    while True:
        query = db.query(Product).filter(Product.slug == slug)
        if exclude_id:
            query = query.filter(Product.id != exclude_id)
        if not query.first():
            break
        slug = f"{base_slug}-{counter}"
        counter += 1
    return slug


def attach_rating(product, db: Session):
    stats = (
        db.query(
            func.avg(Review.rating).label("avg"),
            func.count(Review.id).label("count"),
        )
        .filter(Review.product_id == product.id)
        .first()
    )
    product.avg_rating = round(float(stats.avg), 1) if stats.avg else None
    product.review_count = stats.count or 0


@router.get("/", response_model=ProductListResponse)
def get_products(
    page: int = Query(1, ge=1),
    per_page: int = Query(12, ge=1, le=100),
    category_id: Optional[int] = None,
    search: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    is_featured: Optional[bool] = None,
    sort_by: str = Query("created_at", enum=["price", "created_at", "name"]),
    sort_order: str = Query("desc", enum=["asc", "desc"]),
    db: Session = Depends(get_db),
):
    query = db.query(Product).filter(Product.is_active == True)

    if category_id:
        query = query.filter(Product.category_id == category_id)
    if search:
        query = query.filter(
            or_(
                Product.name.ilike(f"%{search}%"),
                Product.description.ilike(f"%{search}%"),
            )
        )
    if min_price is not None:
        query = query.filter(Product.price >= min_price)
    if max_price is not None:
        query = query.filter(Product.price <= max_price)
    if is_featured is not None:
        query = query.filter(Product.is_featured == is_featured)

    total = query.count()

    sort_col = getattr(Product, sort_by)
    query = query.order_by(sort_col.asc() if sort_order == "asc" else sort_col.desc())
    products = query.offset((page - 1) * per_page).limit(per_page).all()

    for p in products:
        attach_rating(p, db)

    return {
        "items": products,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": max(1, (total + per_page - 1) // per_page),
    }


@router.get("/featured", response_model=List[ProductResponse])
def get_featured(limit: int = Query(8, ge=1, le=20), db: Session = Depends(get_db)):
    products = (
        db.query(Product)
        .filter(Product.is_active == True, Product.is_featured == True)
        .limit(limit)
        .all()
    )
    for p in products:
        attach_rating(p, db)
    return products


@router.get("/{product_id}", response_model=ProductResponse)
def get_product(product_id: int, db: Session = Depends(get_db)):
    product = (
        db.query(Product)
        .filter(Product.id == product_id, Product.is_active == True)
        .first()
    )
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    attach_rating(product, db)
    return product


@router.post("/", response_model=ProductResponse, status_code=201)
def create_product(
    product_data: ProductCreate,
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    slug = make_unique_slug(product_data.name, db)
    product = Product(**product_data.model_dump(), slug=slug)
    db.add(product)
    db.commit()
    db.refresh(product)
    attach_rating(product, db)
    return product


@router.put("/{product_id}", response_model=ProductResponse)
def update_product(
    product_id: int,
    update_data: ProductUpdate,
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    if update_data.name:
        product.slug = make_unique_slug(update_data.name, db, exclude_id=product_id)
    for field, value in update_data.model_dump(exclude_unset=True).items():
        setattr(product, field, value)
    db.commit()
    db.refresh(product)
    attach_rating(product, db)
    return product


@router.delete("/{product_id}", status_code=204)
def delete_product(
    product_id: int,
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    product.is_active = False
    db.commit()


@router.post("/{product_id}/images")
async def upload_product_image(
    product_id: int,
    file: UploadFile = File(...),
    is_primary: bool = False,
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    if is_primary:
        db.query(ProductImage).filter(ProductImage.product_id == product_id).update(
            {"is_primary": False}
        )

    image_url = await save_upload(file, folder="products")
    sort_order = (
        db.query(ProductImage).filter(ProductImage.product_id == product_id).count()
    )
    img = ProductImage(
        product_id=product_id,
        image_url=image_url,
        is_primary=is_primary,
        sort_order=sort_order,
    )
    db.add(img)
    db.commit()
    db.refresh(img)
    return {"id": img.id, "image_url": image_url, "is_primary": is_primary}


@router.delete("/{product_id}/images/{image_id}", status_code=204)
def delete_product_image(
    product_id: int,
    image_id: int,
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    img = (
        db.query(ProductImage)
        .filter(ProductImage.id == image_id, ProductImage.product_id == product_id)
        .first()
    )
    if not img:
        raise HTTPException(status_code=404, detail="Image not found")
    db.delete(img)
    db.commit()
