import asyncio
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import and_, or_
from sqlalchemy.orm import joinedload

from app.config import settings
from app.database import SessionLocal
from app.models.cart import Cart, CartItem
from app.models.user import User, UserRole
from app.utils.email import send_cart_reminder_email

logger = logging.getLogger(__name__)


def _build_cart_email_payload(cart: Cart):
    items = []
    total = Decimal("0")

    for item in cart.items:
        product = item.product
        if not product or not product.is_active:
            continue

        price = product.sale_price or product.price
        line_total = price * item.quantity
        total += line_total
        items.append({
            "name": product.name,
            "quantity": item.quantity,
            "line_total": float(line_total),
        })

    return items, total


def send_due_cart_reminders() -> int:
    if not settings.CART_REMINDER_ENABLED:
        return 0

    if not settings.GMAIL_USER or not settings.GMAIL_APP_PASSWORD:
        logger.info("Cart reminders skipped because email credentials are not configured.")
        return 0

    now = datetime.now(timezone.utc)
    stale_cutoff = now - timedelta(days=settings.CART_REMINDER_MIN_CART_AGE_DAYS)
    reminder_cutoff = now - timedelta(days=settings.CART_REMINDER_INTERVAL_DAYS)

    db = SessionLocal()
    sent_count = 0
    try:
        carts = (
            db.query(Cart)
            .join(Cart.user)
            .options(
                joinedload(Cart.user),
                joinedload(Cart.items).joinedload(CartItem.product),
            )
            .filter(
                User.role == UserRole.user,
                User.is_active == True,
                User.is_email_verified == True,
                Cart.items.any(),
                or_(
                    Cart.updated_at <= stale_cutoff,
                    and_(Cart.updated_at.is_(None), Cart.created_at <= stale_cutoff),
                ),
                or_(
                    Cart.last_reminder_at.is_(None),
                    Cart.last_reminder_at <= reminder_cutoff,
                ),
            )
            .with_for_update(of=Cart, skip_locked=True)
            .all()
        )

        for cart in carts:
            items, total = _build_cart_email_payload(cart)
            if not items:
                continue

            user = cart.user
            try:
                send_cart_reminder_email(
                    to_email=user.email,
                    full_name=user.full_name,
                    items=items,
                    total_amount=total,
                )
            except Exception:
                logger.exception("Failed to send cart reminder email for user %s", user.id)
                continue

            cart.last_reminder_at = now
            sent_count += 1

        db.commit()
        if sent_count:
            logger.info("Sent %s cart reminder email(s).", sent_count)
        return sent_count
    finally:
        db.close()


async def cart_reminder_scheduler():
    while True:
        try:
            send_due_cart_reminders()
        except Exception:
            logger.exception("Cart reminder scheduler failed.")

        await asyncio.sleep(max(settings.CART_REMINDER_CHECK_INTERVAL_HOURS, 1) * 60 * 60)


def start_cart_reminder_scheduler(app):
    if getattr(app.state, "cart_reminder_scheduler_started", False):
        return

    app.state.cart_reminder_scheduler_started = True
    app.state.cart_reminder_scheduler_task = asyncio.create_task(cart_reminder_scheduler())


async def stop_cart_reminder_scheduler(app):
    task = getattr(app.state, "cart_reminder_scheduler_task", None)
    if not task:
        return

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    app.state.cart_reminder_scheduler_started = False
