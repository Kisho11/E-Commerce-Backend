import re
import secrets
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from html import escape
from html.parser import HTMLParser
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy.orm import Session
from app.core.dependencies import get_current_admin
from app.database import get_db
from app.models.marketing import MarketingBanner, MarketingCatalogue, MarketingEmailCampaign, NewsletterSubscriber
from app.schemas.marketing import (
    MarketingBannerResponse,
    MarketingCatalogueDeleteResponse,
    MarketingCatalogueResponse,
    MarketingCampaignSendResponse,
    MarketingCampaignImageUploadResponse,
    MarketingEmailCampaignResponse,
    MarketingSettingsResponse,
    MarketingSettingsUpdate,
    NewsletterSubscribeRequest,
    NewsletterSubscribeResponse,
    NewsletterSubscriberResponse,
)
from app.utils.email import send_marketing_campaign_email
from app.utils.file_upload import delete_uploaded_file, resolve_uploaded_file_path, save_pdf_upload, save_upload

router = APIRouter(prefix="/marketing", tags=["Marketing"])

MARKETING_IMAGE_TYPES = {"image/jpeg", "image/png"}
HERO_IMAGE_TYPES = {"image/jpeg", "image/png"}
SHOWROOM_IMAGE_TYPES = {"image/jpeg", "image/png"}
DISCOUNT_MIN = Decimal("0")
DISCOUNT_MAX = Decimal("100")
DEFAULT_CAMPAIGN_TYPE = "Marketing Update"
CAMPAIGN_IMAGE_MAX_COUNT = 5
CAMPAIGN_IMAGE_MAX_BYTES = 2 * 1024 * 1024
CATALOGUE_PDF_MAX_BYTES = 50 * 1024 * 1024
ADMIN_EMAIL_CAMPAIGNS_ENABLED = False
ALLOWED_CAMPAIGN_HTML_TAGS = {
    "p", "br", "strong", "b", "em", "i", "u", "s", "h2", "h3", "ul", "ol", "li", "blockquote", "img",
}
SCRIPT_STYLE_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)


class CampaignHtmlCleaner(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        tag_name = tag.lower()
        if tag_name not in ALLOWED_CAMPAIGN_HTML_TAGS:
            return
        if tag_name == "img":
            attr_map = {key.lower(): value for key, value in attrs if value}
            src = attr_map.get("src", "").strip()
            if not re.match(r"^https?://", src, re.IGNORECASE):
                return
            alt = attr_map.get("alt", "")
            self.parts.append(
                f'<img src="{escape(src, quote=True)}" alt="{escape(alt, quote=True)}" '
                'style="display:block;width:100%;max-width:600px;height:auto;border-radius:12px;border:1px solid #e2e8f0;margin:18px 0;">'
            )
            return
        self.parts.append(f"<{tag_name}>")

    def handle_endtag(self, tag):
        tag_name = tag.lower()
        if tag_name in ALLOWED_CAMPAIGN_HTML_TAGS and tag_name not in {"br", "img"}:
            self.parts.append(f"</{tag_name}>")

    def handle_data(self, data):
        self.parts.append(escape(data))

    def handle_entityref(self, name):
        self.parts.append(f"&{name};")

    def handle_charref(self, name):
        self.parts.append(f"&#{name};")

    def get_html(self) -> str:
        return "".join(self.parts)


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


def _get_catalogue(db: Session) -> Optional[MarketingCatalogue]:
    return db.query(MarketingCatalogue).order_by(MarketingCatalogue.id.asc()).first()


def _normalize_discount_percentage(value: str | Decimal | int | float | None) -> Decimal:
    try:
        discount = Decimal(str(value if value is not None else "0"))
    except (InvalidOperation, ValueError):
        raise HTTPException(status_code=422, detail="Global discount percentage must be a valid number")

    if discount < DISCOUNT_MIN or discount > DISCOUNT_MAX:
        raise HTTPException(status_code=422, detail="Global discount percentage must be between 0 and 100")
    return discount.quantize(Decimal("0.01"))


def _normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def _clean_campaign_html(value: str) -> str:
    html = SCRIPT_STYLE_RE.sub("", value or "").strip()
    cleaner = CampaignHtmlCleaner()
    cleaner.feed(html)
    cleaned = cleaner.get_html()
    has_text = bool(re.sub(r"<[^>]*>", "", cleaned).strip())
    has_image = bool(re.search(r"<img\b", cleaned, flags=re.IGNORECASE))
    if not has_text and not has_image:
        raise HTTPException(status_code=422, detail="Email message is required")
    return cleaned


async def _save_campaign_images(files: Optional[list[UploadFile]], request: Request) -> list[str]:
    uploaded_files = [file for file in (files or []) if file and file.filename]
    if len(uploaded_files) > CAMPAIGN_IMAGE_MAX_COUNT:
        raise HTTPException(status_code=400, detail="You can upload a maximum of 5 campaign images")

    image_urls = []
    base_url = str(request.base_url).rstrip("/")

    for file in uploaded_files:
        if file.content_type not in MARKETING_IMAGE_TYPES:
            raise HTTPException(status_code=400, detail="Campaign images must be PNG or JPEG files")

        contents = await file.read()
        if len(contents) > CAMPAIGN_IMAGE_MAX_BYTES:
            raise HTTPException(status_code=400, detail="Each campaign image must be 2 MB or smaller")

        await file.seek(0)
        saved_url = await save_upload(file, folder="marketing")
        image_urls.append(f"{base_url}{saved_url}")

    return image_urls


def _extract_campaign_image_urls(message_html: str) -> list[str]:
    return re.findall(r'<img[^>]+src="([^"]+)"', message_html, flags=re.IGNORECASE)


def _ensure_admin_email_campaigns_enabled() -> None:
    if not ADMIN_EMAIL_CAMPAIGNS_ENABLED:
        raise HTTPException(status_code=404, detail="Email campaigns are currently disabled")


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
        "hero_image_url": banner.hero_image_url if banner else None,
        "showroom_image_url": banner.showroom_image_url if banner else None,
    }


@router.get("/catalogue", response_model=Optional[MarketingCatalogueResponse])
def get_catalogue(db: Session = Depends(get_db)):
    return _get_catalogue(db)


@router.get("/catalogue/download")
def download_catalogue(db: Session = Depends(get_db)):
    catalogue = _get_catalogue(db)
    if not catalogue:
        raise HTTPException(status_code=404, detail="No catalogue is currently uploaded")

    file_path = resolve_uploaded_file_path(catalogue.file_url)
    if not file_path or not Path(file_path).is_file():
        raise HTTPException(status_code=404, detail="Catalogue file not found")

    return FileResponse(
        file_path,
        media_type="application/pdf",
        filename=catalogue.original_filename or "Elmshelf Catalogue.pdf",
    )


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
        "hero_image_url": banner.hero_image_url,
        "showroom_image_url": banner.showroom_image_url,
    }


@router.put("/admin/hero-image", response_model=MarketingBannerResponse)
async def update_admin_hero_image(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    if not file or not file.filename:
        raise HTTPException(status_code=422, detail="Upload a PNG or JPEG homepage hero image")

    if file.content_type not in HERO_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Homepage hero image must be a PNG or JPEG image")

    banner = _get_or_create_banner(db)
    previous_file_url = banner.hero_image_url
    banner.hero_image_url = await save_upload(file, folder="marketing")

    db.commit()
    db.refresh(banner)

    if previous_file_url and previous_file_url.startswith("/uploads/") and previous_file_url != banner.hero_image_url:
        delete_uploaded_file(previous_file_url)

    return banner


@router.put("/admin/showroom-image", response_model=MarketingBannerResponse)
async def update_admin_showroom_image(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    if not file or not file.filename:
        raise HTTPException(status_code=422, detail="Upload a PNG or JPEG showroom image")

    if file.content_type not in SHOWROOM_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Showroom image must be a PNG or JPEG image")

    banner = _get_or_create_banner(db)
    previous_file_url = banner.showroom_image_url
    banner.showroom_image_url = await save_upload(file, folder="marketing")

    db.commit()
    db.refresh(banner)

    if previous_file_url and previous_file_url.startswith("/uploads/") and previous_file_url != banner.showroom_image_url:
        delete_uploaded_file(previous_file_url)

    return banner


@router.get("/admin/catalogue", response_model=Optional[MarketingCatalogueResponse])
def get_admin_catalogue(db: Session = Depends(get_db), admin=Depends(get_current_admin)):
    return _get_catalogue(db)


@router.put("/admin/catalogue", response_model=MarketingCatalogueResponse)
async def update_admin_catalogue(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    if not file or not file.filename:
        raise HTTPException(status_code=422, detail="Upload a PDF catalogue file")

    file_url, file_size = await save_pdf_upload(
        file,
        folder="catalogue",
        max_size_bytes=CATALOGUE_PDF_MAX_BYTES,
    )
    catalogue = _get_catalogue(db)
    previous_file_url = catalogue.file_url if catalogue else None

    if not catalogue:
        catalogue = MarketingCatalogue(
            file_url=file_url,
            original_filename=file.filename,
            file_size=file_size,
        )
        db.add(catalogue)
    else:
        catalogue.file_url = file_url
        catalogue.original_filename = file.filename
        catalogue.file_size = file_size

    db.commit()
    db.refresh(catalogue)

    if previous_file_url and previous_file_url != file_url:
        delete_uploaded_file(previous_file_url)

    return catalogue


@router.delete("/admin/catalogue", response_model=MarketingCatalogueDeleteResponse)
def delete_admin_catalogue(db: Session = Depends(get_db), admin=Depends(get_current_admin)):
    catalogue = _get_catalogue(db)
    if not catalogue:
        return {"message": "No catalogue uploaded."}

    file_url = catalogue.file_url
    db.delete(catalogue)
    db.commit()
    delete_uploaded_file(file_url)
    return {"message": "Catalogue deleted."}


@router.post("/subscribe", response_model=NewsletterSubscribeResponse)
def subscribe_to_newsletter(
    subscription: NewsletterSubscribeRequest,
    db: Session = Depends(get_db),
):
    if not subscription.consent_accepted:
        raise HTTPException(status_code=422, detail="Consent is required before subscribing")

    email = _normalize_email(subscription.email)
    full_name = subscription.full_name.strip()
    business_type = subscription.business_type
    if len(full_name) < 2:
        raise HTTPException(status_code=422, detail="Name is required before subscribing")
    subscriber = db.query(NewsletterSubscriber).filter(NewsletterSubscriber.email == email).first()

    if subscriber:
        if subscriber.is_active:
            return {"message": "You're already subscribed.", "is_active": True}

        subscriber.full_name = full_name
        subscriber.business_type = business_type
        subscriber.is_active = True
        subscriber.consent_accepted = True
        subscriber.unsubscribed_at = None
        subscriber.subscribed_at = datetime.now(timezone.utc)
        db.commit()
        return {"message": "You're subscribed again. Thanks for joining us.", "is_active": True}

    subscriber = NewsletterSubscriber(
        full_name=full_name,
        email=email,
        business_type=business_type,
        consent_accepted=True,
        is_active=True,
        unsubscribe_token=secrets.token_urlsafe(32),
    )
    db.add(subscriber)
    db.commit()
    return {"message": "Thanks, you're subscribed.", "is_active": True}


@router.get("/unsubscribe", response_class=HTMLResponse)
def unsubscribe_from_newsletter(token: str, db: Session = Depends(get_db)):
    subscriber = db.query(NewsletterSubscriber).filter(
        NewsletterSubscriber.unsubscribe_token == token
    ).first()

    title = "Subscription updated"
    message = "You have been unsubscribed from Elmshelf marketing emails."

    if not subscriber:
        title = "Link not found"
        message = "This unsubscribe link is invalid or has already been replaced."
    else:
        subscriber.is_active = False
        subscriber.unsubscribed_at = datetime.now(timezone.utc)
        db.commit()

    return f"""<!DOCTYPE html>
<html>
<body style="font-family:Arial,sans-serif;max-width:520px;margin:0 auto;padding:40px 20px;color:#1e293b;">
  <h1>{title}</h1>
  <p>{message}</p>
  <p><a href="/" style="color:#dc2626;font-weight:700;">Return to website</a></p>
</body>
</html>"""


@router.get("/admin/subscribers", response_model=list[NewsletterSubscriberResponse])
def get_newsletter_subscribers(db: Session = Depends(get_db), admin=Depends(get_current_admin)):
    return db.query(NewsletterSubscriber).order_by(
        NewsletterSubscriber.is_active.desc(),
        NewsletterSubscriber.created_at.desc(),
    ).all()


@router.get("/admin/campaigns", response_model=list[MarketingEmailCampaignResponse])
def get_marketing_campaigns(db: Session = Depends(get_db), admin=Depends(get_current_admin)):
    _ensure_admin_email_campaigns_enabled()
    return db.query(MarketingEmailCampaign).order_by(MarketingEmailCampaign.created_at.desc()).limit(20).all()


@router.post("/admin/campaign-images", response_model=MarketingCampaignImageUploadResponse)
async def upload_marketing_campaign_images(
    request: Request,
    images: list[UploadFile] = File(...),
    admin=Depends(get_current_admin),
):
    _ensure_admin_email_campaigns_enabled()
    image_urls = await _save_campaign_images(images, request)
    return {"image_urls": image_urls}


@router.post("/admin/campaigns/send", response_model=MarketingCampaignSendResponse)
async def send_marketing_campaign(
    request: Request,
    subject: str = Form(...),
    message_html: str = Form(...),
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
):
    _ensure_admin_email_campaigns_enabled()
    clean_subject = (subject or "").strip()

    if len(clean_subject) < 3 or len(clean_subject) > 180:
        raise HTTPException(status_code=422, detail="Subject must be between 3 and 180 characters")

    clean_message_html = _clean_campaign_html(message_html)
    image_urls = _extract_campaign_image_urls(clean_message_html)

    subscribers = db.query(NewsletterSubscriber).filter(NewsletterSubscriber.is_active.is_(True)).all()
    if not subscribers:
        raise HTTPException(status_code=422, detail="There are no active newsletter subscribers")

    campaign = MarketingEmailCampaign(
        campaign_type=DEFAULT_CAMPAIGN_TYPE,
        subject=clean_subject,
        message_html=clean_message_html,
        image_urls=image_urls,
        status="sending",
    )
    db.add(campaign)
    db.commit()
    db.refresh(campaign)

    sent_count = 0
    failed_count = 0
    base_url = str(request.base_url).rstrip("/")
    for subscriber in subscribers:
        try:
            send_marketing_campaign_email(
                to_email=subscriber.email,
                full_name=subscriber.full_name,
                campaign_type=DEFAULT_CAMPAIGN_TYPE,
                subject=clean_subject,
                message_html=clean_message_html,
                image_urls=image_urls,
                unsubscribe_url=f"{base_url}/api/v1/marketing/unsubscribe?token={subscriber.unsubscribe_token}",
            )
            sent_count += 1
        except Exception:
            failed_count += 1

    campaign.sent_count = sent_count
    campaign.failed_count = failed_count
    campaign.status = "sent" if failed_count == 0 else "partial"
    campaign.sent_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(campaign)

    return {
        "campaign": campaign,
        "subscriber_count": len(subscribers),
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
