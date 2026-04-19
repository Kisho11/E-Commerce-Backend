import enum
from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import relationship
from app.database import Base


class MovementType(str, enum.Enum):
    receive = "receive"
    sale = "sale"
    adjustment = "adjustment"
    return_ = "return"


class Inventory(Base):
    __tablename__ = "inventory"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), unique=True, nullable=False)
    on_hand = Column(Integer, default=0, nullable=False)
    reserved = Column(Integer, default=0, nullable=False)
    reorder_level = Column(Integer, default=10)
    reorder_qty = Column(Integer, default=50)
    avg_daily_usage = Column(Numeric(8, 2), default=0)
    location = Column(String, nullable=True)
    supplier = Column(String, nullable=True)
    lead_time_days = Column(Integer, default=7)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    product = relationship("Product", back_populates="inventory")
    movements = relationship("StockMovement", back_populates="inventory", cascade="all, delete-orphan", order_by="StockMovement.created_at.desc()")

    @property
    def available(self):
        return max(0, self.on_hand - self.reserved)

    @property
    def status(self):
        if self.on_hand <= 0:
            return "Out of Stock"
        if self.on_hand <= self.reorder_level:
            return "Low Stock"
        return "Healthy"

    @property
    def coverage_days(self):
        if not self.avg_daily_usage or self.avg_daily_usage == 0:
            return None
        return round(self.available / float(self.avg_daily_usage))


class StockMovement(Base):
    __tablename__ = "stock_movements"

    id = Column(Integer, primary_key=True, index=True)
    inventory_id = Column(Integer, ForeignKey("inventory.id", ondelete="CASCADE"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    movement_type = Column(Enum(MovementType), nullable=False)
    qty_change = Column(Integer, nullable=False)
    qty_before = Column(Integer, nullable=False)
    qty_after = Column(Integer, nullable=False)
    reason = Column(String, nullable=True)
    actor = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    inventory = relationship("Inventory", back_populates="movements")
