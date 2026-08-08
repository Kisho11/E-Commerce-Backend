from sqlalchemy import Boolean, Column, DateTime, Integer, Numeric, String, func
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
