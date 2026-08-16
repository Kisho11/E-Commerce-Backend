from sqlalchemy import Boolean, Column, DateTime, Integer, JSON, String, Text, func
from app.database import Base


class QuotationRequest(Base):
    __tablename__ = "quotation_requests"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String, nullable=False)
    email = Column(String, index=True, nullable=False)
    phone = Column(String, nullable=False)
    requirements = Column(JSON, default=list, nullable=False)
    message = Column(Text, nullable=False)
    wants_catalogue = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
