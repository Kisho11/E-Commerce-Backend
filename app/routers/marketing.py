from typing import Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session
from app.core.dependencies import get_current_admin
from app.database import get_db
from app.models.marketing import MarketingBanner
from app.schemas.marketing import MarketingBannerResponse
from app.utils.file_upload import save_upload

router = APIRouter(prefix="/marketing", tags=["Marketing"])

MARKETING_IMAGE_TYPES = {"image/jpeg", "image/png"}


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


@router.get("/banner", response_model=Optional[MarketingBannerResponse])
def get_active_banner(db: Session = Depends(get_db)):
    banner = _get_banner(db)
    if not banner or not banner.is_active or not banner.image_url:
        return None
    return banner


@router.get("/admin/banner", response_model=MarketingBannerResponse)
def get_admin_banner(db: Session = Depends(get_db), admin=Depends(get_current_admin)):
    return _get_or_create_banner(db)


@router.put("/admin/banner", response_model=MarketingBannerResponse)
async def update_admin_banner(
    is_active: bool = Form(False),
    cta_url: str = Form("/catalogue"),
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
    db.commit()
    db.refresh(banner)
    return banner
