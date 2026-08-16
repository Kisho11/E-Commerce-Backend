from sqlalchemy import Boolean, Column, DateTime, Integer, JSON, Numeric, String, Text, func
from app.database import Base


class MarketingBanner(Base):
    __tablename__ = "marketing_banners"

    id = Column(Integer, primary_key=True, index=True)
    image_url = Column(String, nullable=True)
    cta_url = Column(String, default="/catalogue", nullable=False)
    is_active = Column(Boolean, default=False, nullable=False)
    global_discount_percentage = Column(Numeric(5, 2), default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class MarketingCatalogue(Base):
    __tablename__ = "marketing_catalogues"

    id = Column(Integer, primary_key=True, index=True)
    file_url = Column(String, nullable=False)
    original_filename = Column(String, nullable=False)
    file_size = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class NewsletterSubscriber(Base):
    __tablename__ = "newsletter_subscribers"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    business_type = Column(String, default="shopowner", nullable=False)
    consent_accepted = Column(Boolean, default=True, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    unsubscribe_token = Column(String, unique=True, index=True, nullable=False)
    subscribed_at = Column(DateTime(timezone=True), server_default=func.now())
    unsubscribed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class MarketingEmailCampaign(Base):
    __tablename__ = "marketing_email_campaigns"

    id = Column(Integer, primary_key=True, index=True)
    campaign_type = Column(String, nullable=False)
    subject = Column(String, nullable=False)
    message_html = Column(Text, nullable=False)
    image_urls = Column(JSON, default=list, nullable=False)
    sent_count = Column(Integer, default=0, nullable=False)
    failed_count = Column(Integer, default=0, nullable=False)
    status = Column(String, default="draft", nullable=False)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
