from decimal import Decimal, InvalidOperation
from typing import Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session
from app.core.dependencies import get_current_admin
from app.database import get_db
from app.models.marketing import MarketingBanner
from app.schemas.marketing import MarketingBannerResponse, MarketingSettingsResponse, MarketingSettingsUpdate
from app.utils.file_upload import save_upload

router = APIRouter(prefix="/marketing", tags=["Marketing"])

MARKETING_IMAGE_TYPES = {"image/jpeg", "image/png"}
DISCOUNT_MIN = Decimal("0")
DISCOUNT_MAX = Decimal("100")


def _get_banner(db: Session) -> Optional[MarketingBanner]:
    return db.query(MarketingBanner).order_by(MarketingBanner.id.asc()).first()


def _get_or_create_banner(db: Session) -> MarketingBanner:
    banner = _get_banner(db)
    if banner:
        return banner
    banner = MarketingBanner(is_active=False, cta_url="/catalogue")
    db.add(banner)
    db.commit()
    db.refresh(banner)
    return banner


def _normalize_discount_percentage(value: str | Decimal | int | float | None) -> Decimal:
    try:
        discount = Decimal(str(value if value is not None else "0"))
    except (InvalidOperation, ValueError):
        raise HTTPException(status_code=422, detail="Global discount percentage must be a valid number")

    if discount < DISCOUNT_MIN or discount > DISCOUNT_MAX:
        raise HTTPException(status_code=422, detail="Global discount percentage must be between 0 and 100")
    return discount.quantize(Decimal("0.01"))


@router.get("/banner", response_model=Optional[MarketingBannerResponse])
def get_active_banner(db: Session = Depends(get_db)):
    banner = _get_banner(db)
    if not banner or not banner.is_active or not banner.image_url:
        return None
    return banner


@router.get("/settings", response_model=MarketingSettingsResponse)
def get_marketing_settings(db: Session = Depends(get_db)):
    banner = _get_banner(db)
    return {
        "global_discount_percentage": banner.global_discount_percentage if banner else Decimal("0"),
    }


@router.put("/admin/settings", response_model=MarketingSettingsResponse)
def update_marketing_settings(
    settings_data: MarketingSettingsUpdate,
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    banner = _get_or_create_banner(db)
    banner.global_discount_percentage = _normalize_discount_percentage(
        settings_data.global_discount_percentage
    )
    db.commit()
    db.refresh(banner)
    return {
        "global_discount_percentage": banner.global_discount_percentage,
    }


@router.get("/admin/banner", response_model=MarketingBannerResponse)
def get_admin_banner(db: Session = Depends(get_db), admin=Depends(get_current_admin)):
    return _get_or_create_banner(db)


@router.put("/admin/banner", response_model=MarketingBannerResponse)
async def update_admin_banner(
    is_active: bool = Form(False),
    cta_url: str = Form("/catalogue"),
    global_discount_percentage: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    banner = _get_or_create_banner(db)
    clean_cta_url = (cta_url or "/catalogue").strip() or "/catalogue"

    if file and file.filename:
        if file.content_type not in MARKETING_IMAGE_TYPES:
            raise HTTPException(status_code=400, detail="Marketing banner must be a PNG or JPEG image")
        banner.image_url = await save_upload(file, folder="marketing")

    if is_active and not banner.image_url:
        raise HTTPException(status_code=422, detail="Upload a PNG or JPEG banner before enabling it")

    banner.is_active = is_active
    banner.cta_url = clean_cta_url
    if global_discount_percentage is not None:
        banner.global_discount_percentage = _normalize_discount_percentage(global_discount_percentage)
    db.commit()
    db.refresh(banner)
    return banner
