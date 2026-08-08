from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, func

from app.database import Base


class ProductView(Base):
    __tablename__ = "product_views"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    visitor_id = Column(String(80), nullable=False, index=True)
    session_id = Column(String(80), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    __table_args__ = (
        Index("ix_product_views_product_session_created", "product_id", "session_id", "created_at"),
    )


class SiteVisit(Base):
    __tablename__ = "site_visits"

    id = Column(Integer, primary_key=True, index=True)
    visitor_id = Column(String(80), nullable=False, index=True)
    session_id = Column(String(80), nullable=False, index=True)
    path = Column(String(255), nullable=False, default="/")
    user_agent = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    __table_args__ = (
        Index("ix_site_visits_session_path_created", "session_id", "path", "created_at"),
    )
