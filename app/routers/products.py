from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, cast, String
from typing import List, Optional
from slugify import slugify
from app.database import get_db
from app.models.product import Product, ProductImage, ProductRelatedProduct, ProductVariantGroup, ProductVariant, ProductType
from app.models.category import Category
from app.models.review import Review
from app.schemas.product import (
    ProductCreate, ProductUpdate, ProductResponse, ProductListResponse,
)
from app.core.dependencies import get_current_manager
from app.utils.file_upload import save_upload

router = APIRouter(prefix="/products", tags=["Products"])


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


def ensure_unique_product_name(db: Session, name: str, exclude_id: Optional[int] = None):
    query = db.query(Product).filter(
        func.lower(Product.name) == name.strip().lower(),
        Product.is_active == True,
    )
    if exclude_id:
        query = query.filter(Product.id != exclude_id)
    if query.first():
        raise HTTPException(
            status_code=400,
            detail="A product with this name already exists",
        )


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


def _set_categories(product: Product, category_ids: List[int], db: Session):
    cats = db.query(Category).filter(Category.id.in_(category_ids)).all()
    product.categories = cats


def _dedupe_int_ids(ids: Optional[List[int]]) -> List[int]:
    seen = set()
    normalized = []
    for value in ids or []:
        try:
            product_id = int(value)
        except (TypeError, ValueError):
            continue
        if product_id > 0 and product_id not in seen:
            seen.add(product_id)
            normalized.append(product_id)
    return normalized


def _set_related_products(product: Product, related_product_ids: Optional[List[int]], db: Session):
    normalized_ids = [product_id for product_id in _dedupe_int_ids(related_product_ids) if product_id != product.id]
    for link in list(product.related_product_links):
        db.delete(link)
    db.flush()

    if not normalized_ids:
        return

    found_ids = {
        row[0]
        for row in db.query(Product.id)
        .filter(Product.id.in_(normalized_ids), Product.is_active == True)
        .all()
    }
    missing_ids = [product_id for product_id in normalized_ids if product_id not in found_ids]
    if missing_ids:
        raise HTTPException(status_code=422, detail=f"Related product not found: {missing_ids[0]}")

    for sort_order, related_product_id in enumerate(normalized_ids):
        db.add(ProductRelatedProduct(
            product_id=product.id,
            related_product_id=related_product_id,
            sort_order=sort_order,
        ))


def _set_variant_groups(product: Product, variant_groups_data: list, db: Session):
    # Replace existing variant groups
    for vg in list(product.variant_groups):
        db.delete(vg)
    db.flush()
    for vg_data in variant_groups_data:
        vg = ProductVariantGroup(product_id=product.id, attribute=vg_data.attribute)
        db.add(vg)
        db.flush()
        for v_data in vg_data.variants:
            v = ProductVariant(
                group_id=vg.id,
                value=v_data.value,
                price_modifier=v_data.price_modifier,
                stock_quantity=v_data.stock_quantity,
                sku_suffix=v_data.sku_suffix,
            )
            db.add(v)


def _infer_product_type(explicit_type: Optional[ProductType], variant_groups_data: Optional[list]) -> ProductType:
    if explicit_type == ProductType.custom:
        return ProductType.custom

    if variant_groups_data:
        has_variants = any(getattr(group, "variants", None) for group in variant_groups_data)
        if has_variants:
            return ProductType.variable

    return ProductType.simple


@router.get("/", response_model=ProductListResponse)
def get_products(
    page: int = Query(1, ge=1),
    per_page: int = Query(12, ge=1, le=2000),
    category_id: Optional[int] = None,
    search: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    is_featured: Optional[bool] = None,
    product_type: Optional[str] = None,
    sort_by: str = Query("created_at", enum=["price", "created_at", "name"]),
    sort_order: str = Query("desc", enum=["asc", "desc"]),
    db: Session = Depends(get_db),
):
    query = db.query(Product).filter(Product.is_active == True)

    if category_id:
        query = query.filter(Product.categories.any(Category.id == category_id))
    if search:
        for term in search.strip().split():
            like_term = f"%{term}%"
            query = query.filter(
                or_(
                    Product.name.ilike(like_term),
                    Product.sku.ilike(like_term),
                    cast(Product.description, String).ilike(like_term),
                    cast(Product.key_features, String).ilike(like_term),
                    cast(Product.additional_information, String).ilike(like_term),
                    Product.categories.any(Category.name.ilike(like_term)),
                )
            )
    if min_price is not None:
        query = query.filter(Product.price >= min_price)
    if max_price is not None:
        query = query.filter(Product.price <= max_price)
    if is_featured is not None:
        query = query.filter(Product.is_featured == is_featured)
    if product_type is not None:
        query = query.filter(Product.product_type == product_type)

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
    product = db.query(Product).filter(Product.id == product_id, Product.is_active == True).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    attach_rating(product, db)
    return product


@router.post("/", response_model=ProductResponse, status_code=201)
def create_product(
    product_data: ProductCreate,
    db: Session = Depends(get_db),
    manager=Depends(get_current_manager),
):
    name = product_data.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Name cannot be empty")
    if product_data.is_active:
        ensure_unique_product_name(db, name)
    slug = make_unique_slug(name, db)
    data = product_data.model_dump(exclude={"category_ids", "variant_groups", "related_product_ids"})
    data["name"] = name
    data["product_type"] = _infer_product_type(product_data.product_type, product_data.variant_groups)
    if data["product_type"] == ProductType.variable:
        data["stock_quantity"] = 0
    product = Product(**data, slug=slug)
    db.add(product)
    db.flush()

    if product_data.category_ids:
        _set_categories(product, product_data.category_ids, db)
    if product_data.variant_groups:
        _set_variant_groups(product, product_data.variant_groups, db)
    _set_related_products(product, product_data.related_product_ids, db)

    db.commit()
    db.refresh(product)
    attach_rating(product, db)
    return product


@router.put("/{product_id}", response_model=ProductResponse)
def update_product(
    product_id: int,
    update_data: ProductUpdate,
    db: Session = Depends(get_db),
    manager=Depends(get_current_manager),
):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    data = update_data.model_dump(exclude_unset=True, exclude={"category_ids", "variant_groups", "related_product_ids"})
    candidate_name = data.get("name", product.name)
    if candidate_name is not None:
        candidate_name = candidate_name.strip()
        if not candidate_name:
            raise HTTPException(status_code=422, detail="Name cannot be empty")
        data["name"] = candidate_name
    candidate_active = data.get("is_active", product.is_active)
    if candidate_active:
        ensure_unique_product_name(db, candidate_name, exclude_id=product_id)
    if "name" in data:
        product.slug = make_unique_slug(candidate_name, db, exclude_id=product_id)
    if update_data.variant_groups is not None:
        data["product_type"] = _infer_product_type(update_data.product_type, update_data.variant_groups)
    elif update_data.product_type == ProductType.custom:
        data["product_type"] = ProductType.custom
    next_product_type = data.get("product_type", product.product_type)
    if next_product_type == ProductType.variable:
        data["stock_quantity"] = 0
    for field, value in data.items():
        setattr(product, field, value)

    if update_data.category_ids is not None:
        _set_categories(product, update_data.category_ids, db)
    if update_data.variant_groups is not None:
        _set_variant_groups(product, update_data.variant_groups, db)
    if update_data.related_product_ids is not None:
        _set_related_products(product, update_data.related_product_ids, db)

    db.commit()
    db.refresh(product)
    attach_rating(product, db)
    return product


@router.delete("/{product_id}", status_code=204)
def delete_product(product_id: int, db: Session = Depends(get_db), manager=Depends(get_current_manager)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    product.is_active = False
    db.commit()


# ── Images ────────────────────────────────────────────────────────────────────

@router.post("/{product_id}/images")
async def upload_product_image(
    product_id: int,
    file: UploadFile = File(...),
    is_primary: bool = False,
    variant_tag: Optional[str] = None,
    db: Session = Depends(get_db),
    manager=Depends(get_current_manager),
):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    if is_primary:
        db.query(ProductImage).filter(ProductImage.product_id == product_id).update({"is_primary": False})

    image_url = await save_upload(file, folder="products")
    sort_order = db.query(ProductImage).filter(ProductImage.product_id == product_id).count()
    img = ProductImage(
        product_id=product_id,
        image_url=image_url,
        is_primary=is_primary,
        sort_order=sort_order,
        variant_tag=variant_tag or None,
    )
    db.add(img)
    db.commit()
    db.refresh(img)
    return {"id": img.id, "image_url": image_url, "is_primary": is_primary, "sort_order": sort_order, "variant_tag": img.variant_tag}


@router.delete("/{product_id}/images/{image_id}", status_code=204)
def delete_product_image(
    product_id: int,
    image_id: int,
    db: Session = Depends(get_db),
    manager=Depends(get_current_manager),
):
    img = db.query(ProductImage).filter(
        ProductImage.id == image_id, ProductImage.product_id == product_id
    ).first()
    if not img:
        raise HTTPException(status_code=404, detail="Image not found")
    db.delete(img)
    db.commit()
