from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional
from pydantic import BaseModel, EmailStr, Field


BusinessType = Literal["shopowner", "shopfitter"]


class MarketingBannerResponse(BaseModel):
    id: int
    image_url: Optional[str] = None
    cta_url: str = "/catalogue"
    is_active: bool = False
    global_discount_percentage: Decimal = Decimal("0")
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class MarketingSettingsResponse(BaseModel):
    global_discount_percentage: Decimal = Decimal("0")


class MarketingSettingsUpdate(BaseModel):
    global_discount_percentage: Decimal = Decimal("0")


class NewsletterSubscribeRequest(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=120)
    email: EmailStr
    business_type: BusinessType
    consent_accepted: bool


class NewsletterSubscribeResponse(BaseModel):
    message: str
    is_active: bool = True


class NewsletterSubscriberResponse(BaseModel):
    id: int
    full_name: str
    email: EmailStr
    business_type: BusinessType = "shopowner"
    is_active: bool
    subscribed_at: Optional[datetime] = None
    unsubscribed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class MarketingEmailCampaignResponse(BaseModel):
    id: int
    campaign_type: str
    subject: str
    message_html: str
    image_urls: list[str] = []
    sent_count: int = 0
    failed_count: int = 0
    status: str
    sent_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class MarketingCampaignSendResponse(BaseModel):
    campaign: MarketingEmailCampaignResponse
    subscriber_count: int


class MarketingCampaignImageUploadResponse(BaseModel):
    image_urls: list[str]
