import random
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import app.models  # noqa: F401
from app.core.security import hash_password
from app.database import Base, SessionLocal, engine
from app.models.address import Address
from app.models.analytics import ProductView, SiteVisit
from app.models.order import Order, OrderItem, OrderStatus, PaymentStatus
from app.models.product import Product
from app.models.user import User, UserRole


SAMPLE_PREFIX = "sample-analytics"
SAMPLE_EMAIL = "sample.analytics@elmshelf.test"
SAMPLE_NAME = "Sample Analytics Customer"
SAMPLE_VISITOR_COUNT = 18
SAMPLE_ORDER_COUNT = 8


def cleanup_previous_samples(db):
    sample_orders = (
        db.query(Order)
        .filter(Order.payment_intent_id.like(f"{SAMPLE_PREFIX}-%"))
        .all()
    )
    for order in sample_orders:
        db.query(OrderItem).filter(OrderItem.order_id == order.id).delete(synchronize_session=False)
        db.delete(order)

    db.query(ProductView).filter(ProductView.visitor_id.like(f"{SAMPLE_PREFIX}-%")).delete(synchronize_session=False)
    db.query(SiteVisit).filter(SiteVisit.visitor_id.like(f"{SAMPLE_PREFIX}-%")).delete(synchronize_session=False)
    db.commit()


def get_or_create_sample_customer(db):
    user = db.query(User).filter(User.email == SAMPLE_EMAIL).first()
    if not user:
        user = User(
            email=SAMPLE_EMAIL,
            hashed_password=hash_password("SampleOnly123!"),
            full_name=SAMPLE_NAME,
            phone="+440000000000",
            role=UserRole.user,
            is_active=True,
            is_email_verified=True,
        )
        db.add(user)
        db.flush()

    address = (
        db.query(Address)
        .filter(Address.user_id == user.id, Address.full_name == SAMPLE_NAME)
        .first()
    )
    if not address:
        address = Address(
            user_id=user.id,
            full_name=SAMPLE_NAME,
            phone="+440000000000",
            address_line1="Sample House",
            city="London",
            state="Greater London",
            postal_code="SW1A 1AA",
            country="GB",
            is_default=False,
        )
        db.add(address)
        db.flush()

    return user, address


def seed_site_visits(db, now):
    paths = [
        "/",
        "/categories",
        "/products-by-industry",
        "/showroom",
        "/catalogue",
        "/reviews",
    ]

    created = 0
    for index in range(SAMPLE_VISITOR_COUNT):
        visitor_id = f"{SAMPLE_PREFIX}-visitor-{index + 1:02d}"
        session_id = f"{SAMPLE_PREFIX}-session-{index + 1:02d}"
        days_ago = index % 28
        visit_count = 1 + (index % 4)

        for visit_index in range(visit_count):
            db.add(
                SiteVisit(
                    visitor_id=visitor_id,
                    session_id=session_id,
                    path=paths[(index + visit_index) % len(paths)],
                    user_agent="Sample Analytics Seeder",
                    created_at=now - timedelta(days=days_ago, hours=visit_index),
                )
            )
            created += 1

    return created


def seed_product_views(db, products, now):
    created = 0
    for rank, product in enumerate(products[:10]):
        view_count = max(3, 42 - (rank * 4))

        for view_index in range(view_count):
            visitor_number = (view_index % SAMPLE_VISITOR_COUNT) + 1
            days_ago = view_index % 21
            db.add(
                ProductView(
                    product_id=product.id,
                    visitor_id=f"{SAMPLE_PREFIX}-visitor-{visitor_number:02d}",
                    session_id=f"{SAMPLE_PREFIX}-pv-session-{rank + 1:02d}-{view_index + 1:03d}",
                    created_at=now - timedelta(days=days_ago, minutes=view_index * 7),
                )
            )
            created += 1

    return created


def seed_paid_orders(db, products, customer, address, now):
    created_orders = 0
    created_items = 0

    for order_index in range(SAMPLE_ORDER_COUNT):
        selected_products = random.sample(products[: min(len(products), 8)], k=min(3, len(products)))
        lines = []
        total = Decimal("0.00")
        for product_index, product in enumerate(selected_products):
            quantity = 1 + ((order_index + product_index) % 5)
            unit_price = Decimal(str(product.sale_price or product.price or 0)).quantize(Decimal("0.01"))
            line_total = unit_price * quantity
            total += line_total
            lines.append((product, quantity, unit_price, line_total))

        order = Order(
            user_id=customer.id,
            address_id=address.id,
            status=OrderStatus.delivered if order_index % 3 else OrderStatus.confirmed,
            total_amount=total,
            payment_status=PaymentStatus.paid,
            payment_intent_id=f"{SAMPLE_PREFIX}-paid-order-{order_index + 1:02d}",
            delivery_mode="ship",
            notes="Sample analytics seed order",
            created_at=now - timedelta(days=order_index * 3),
        )
        db.add(order)
        db.flush()

        for product, quantity, unit_price, line_total in lines:
            db.add(
                OrderItem(
                    order_id=order.id,
                    product_id=product.id,
                    quantity=quantity,
                    unit_price=unit_price,
                    total_price=line_total,
                )
            )
            created_items += 1

        created_orders += 1

    return created_orders, created_items


def main():
    random.seed(42)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        products = (
            db.query(Product)
            .filter(Product.is_active == True)
            .order_by(Product.id.asc())
            .limit(12)
            .all()
        )
        if not products:
            print("No active products found. Add products before seeding sample analytics.")
            return 1

        cleanup_previous_samples(db)
        customer, address = get_or_create_sample_customer(db)
        now = datetime.now(timezone.utc)

        visit_count = seed_site_visits(db, now)
        product_view_count = seed_product_views(db, products, now)
        order_count, order_item_count = seed_paid_orders(db, products, customer, address, now)
        db.commit()

        print("Sample analytics records seeded successfully.")
        print(f"site_visits={visit_count}")
        print(f"product_views={product_view_count}")
        print(f"paid_orders={order_count}")
        print(f"order_items={order_item_count}")
        return 0
    except Exception as error:
        db.rollback()
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
