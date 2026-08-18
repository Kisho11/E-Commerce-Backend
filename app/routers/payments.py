from datetime import datetime, timezone
import json
import logging
from typing import Optional
import stripe
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.cart import Cart, CartItem
from app.models.order import Order, OrderStatus, PaymentStatus
from app.models.product import Product
from app.models.inventory import MovementType
from app.schemas.order import OrderResponse
from app.core.dependencies import get_current_user
from app.config import settings
from app.utils.email import send_new_order_notification_email, send_order_confirmation_email
from app.utils.variant_pricing import adjust_stock_quantity, ensure_stock_available

stripe.api_key = settings.STRIPE_SECRET_KEY

router = APIRouter(prefix="/payments", tags=["Payments"])
logger = logging.getLogger(__name__)
REPLACEABLE_PAYMENT_INTENT_STATUSES = {"requires_payment_method", "canceled"}
ACTIVE_PAYMENT_INTENT_STATUSES = {"requires_confirmation", "requires_action", "processing", "requires_capture"}
STRIPE_PAYMENT_METHOD_TYPES = ["card", "link", "klarna"]


def send_order_confirmation_email_safely(**payload):
    try:
        send_order_confirmation_email(**payload)
    except Exception:
        logger.exception("Failed to send order confirmation email for order %s", payload.get("order_id"))


def send_new_order_notification_email_safely(**payload):
    try:
        send_new_order_notification_email(**payload)
    except Exception:
        logger.exception("Failed to send new order notification email for order %s", payload.get("order_id"))


def parse_checkout_cart_item_ids(order: Order) -> list[int]:
    try:
        value = json.loads(order.checkout_cart_item_ids or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(value, list):
        return []
    return [int(item_id) for item_id in value if str(item_id).isdigit()]


def build_order_email_items(order: Order) -> list[dict]:
    return [
        {
            "name": item.product.name if item.product else f"Product #{item.product_id}",
            "quantity": item.quantity,
            "line_total": float(item.total_price),
        }
        for item in order.items
    ]


def build_order_email_payload(order: Order) -> dict:
    address = order.address
    return {
        "to_email": order.user.email,
        "full_name": order.user.full_name,
        "order_id": order.id,
        "total_amount": float(order.total_amount),
        "delivery_mode": order.delivery_mode,
        "delivery_note": order.delivery_note,
        "address": {
            "address_line1": address.address_line1,
            "address_line2": address.address_line2,
            "city": address.city,
            "state": address.state,
            "postal_code": address.postal_code,
            "country": address.country,
        },
        "items": build_order_email_items(order),
    }


def build_new_order_notification_email_payload(order: Order) -> dict:
    address = order.address
    return {
        "to_email": settings.ORDER_NOTIFICATION_EMAIL or settings.EMAIL_REPLY_TO or settings.GMAIL_USER,
        "customer_email": order.user.email,
        "customer_name": order.user.full_name,
        "customer_phone": order.user.phone,
        "order_id": order.id,
        "total_amount": float(order.total_amount),
        "delivery_mode": order.delivery_mode,
        "delivery_note": order.delivery_note,
        "address": {
            "address_line1": address.address_line1,
            "address_line2": address.address_line2,
            "city": address.city,
            "state": address.state,
            "postal_code": address.postal_code,
            "country": address.country,
        },
        "items": build_order_email_items(order),
    }


def stripe_amount_for_order(order: Order) -> int:
    return int(order.total_amount * 100)


def stripe_currency() -> str:
    return (settings.PAYMENT_CURRENCY or "gbp").lower()


def intent_matches_order(intent, order: Order) -> bool:
    meta = intent.metadata
    try:
        meta_order_id = str(meta["order_id"]) if meta else ""
        meta_user_id = str(meta["user_id"]) if meta else ""
    except (KeyError, TypeError, AttributeError):
        return False
    return (
        int(intent.amount) == stripe_amount_for_order(order)
        and str(intent.currency).lower() == stripe_currency()
        and meta_order_id == str(order.id)
        and meta_user_id == str(order.user_id)
    )


def release_reserved_stock(order: Order, db: Session | None = None) -> None:
    if not order.stock_reserved:
        return

    for item in order.items:
        if item.product:
            adjust_stock_quantity(
                item.product,
                item.selected_attributes or {},
                item.quantity,
                db=db,
                movement_type=MovementType.return_,
                reason=f"Order #{order.id} payment failed",
                actor="System",
            )
    order.stock_reserved = False


def finalize_paid_order(
    order: Order,
    db: Session,
    background_tasks: Optional[BackgroundTasks] = None,
) -> Order:
    if order.payment_status == PaymentStatus.paid:
        if order.status != OrderStatus.confirmed:
            order.status = OrderStatus.confirmed
            db.commit()
            db.refresh(order)
        return order

    if order.status == OrderStatus.cancelled and order.payment_status != PaymentStatus.failed:
        raise HTTPException(status_code=400, detail="Order has been cancelled")

    if not order.stock_reserved:
        product_ids = [item.product_id for item in order.items]
        products = (
            db.execute(
                select(Product)
                .where(Product.id.in_(product_ids))
                .with_for_update()
            )
            .scalars()
            .all()
        )
        products_by_id = {product.id: product for product in products}
        stock_reserved = False
        for item in order.items:
            product = products_by_id.get(item.product_id)
            if product:
                try:
                    ensure_stock_available(product, item.selected_attributes or {}, item.quantity)
                except ValueError:
                    raise HTTPException(status_code=400, detail=f"Insufficient stock for '{product.name}'")
                adjust_stock_quantity(
                    product,
                    item.selected_attributes or {},
                    -item.quantity,
                    db=db,
                    movement_type=MovementType.sale,
                    reason=f"Order #{order.id} payment stock reserved",
                    actor="System",
                )
                stock_reserved = True
        order.stock_reserved = stock_reserved

    cart_item_ids = parse_checkout_cart_item_ids(order)
    if cart_item_ids:
        cart = (
            db.query(Cart)
            .filter(Cart.user_id == order.user_id)
            .with_for_update()
            .first()
        )
        if cart:
            db.query(CartItem).filter(
                CartItem.cart_id == cart.id,
                CartItem.id.in_(cart_item_ids),
            ).delete(synchronize_session=False)
            cart.updated_at = datetime.now(timezone.utc)

    order.payment_status = PaymentStatus.paid
    order.status = OrderStatus.confirmed
    db.commit()
    db.refresh(order)

    try:
        email_payload = build_order_email_payload(order)
        notification_payload = build_new_order_notification_email_payload(order)
        if background_tasks:
            background_tasks.add_task(send_order_confirmation_email_safely, **email_payload)
            background_tasks.add_task(send_new_order_notification_email_safely, **notification_payload)
        else:
            send_order_confirmation_email_safely(**email_payload)
            send_new_order_notification_email_safely(**notification_payload)
    except Exception:
        logger.exception("Failed to build/send paid order emails for order %s", order.id)

    return order


def mark_order_payment_failed(order: Order, db: Session) -> Order:
    if order.payment_status != PaymentStatus.paid:
        release_reserved_stock(order, db=db)
        order.payment_status = PaymentStatus.failed
        order.status = OrderStatus.cancelled
        db.commit()
        db.refresh(order)
    return order


@router.post("/create-payment-intent/{order_id}")
def create_payment_intent(
    order_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    order = (
        db.query(Order)
        .filter(Order.id == order_id, Order.user_id == current_user.id)
        .with_for_update()
        .first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.payment_status == PaymentStatus.paid:
        raise HTTPException(status_code=400, detail="Order is already paid")
    if order.status == OrderStatus.cancelled:
        raise HTTPException(status_code=400, detail="Order has been cancelled")

    try:
        if order.payment_intent_id:
            existing_intent = stripe.PaymentIntent.retrieve(order.payment_intent_id)
            if existing_intent.status == "succeeded":
                raise HTTPException(status_code=400, detail="Order payment has already succeeded")
            if existing_intent.status in ACTIVE_PAYMENT_INTENT_STATUSES:
                if not intent_matches_order(existing_intent, order):
                    raise HTTPException(status_code=400, detail="Existing payment intent does not match this order")
                return {
                    "client_secret": existing_intent.client_secret,
                    "payment_intent_id": existing_intent.id,
                }

        intent = stripe.PaymentIntent.create(
            amount=stripe_amount_for_order(order),
            currency=stripe_currency(),
            payment_method_types=STRIPE_PAYMENT_METHOD_TYPES,
            metadata={"order_id": str(order.id), "user_id": str(current_user.id)},
        )
        order.payment_intent_id = intent.id
        order.payment_status = PaymentStatus.pending
        order.status = OrderStatus.pending
        db.commit()
        return {"client_secret": intent.client_secret, "payment_intent_id": intent.id}
    except HTTPException:
        raise
    except stripe.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        logger.exception("Unexpected error creating payment intent for order %s", order_id)
        raise HTTPException(status_code=500, detail="Unable to initialize payment. Please try again.")


@router.post("/confirm-order/{order_id}", response_model=OrderResponse)
def confirm_order_payment(
    order_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    order = (
        db.query(Order)
        .filter(Order.id == order_id, Order.user_id == current_user.id)
        .first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if not order.payment_intent_id:
        raise HTTPException(status_code=400, detail="Order has no payment intent")

    try:
        intent = stripe.PaymentIntent.retrieve(order.payment_intent_id)
    except stripe.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not intent_matches_order(intent, order):
        raise HTTPException(status_code=400, detail="Payment intent does not match this order")

    order = (
        db.query(Order)
        .filter(Order.id == order_id, Order.user_id == current_user.id)
        .with_for_update()
        .first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    try:
        if intent.status == "succeeded":
            return finalize_paid_order(order, db, background_tasks)

        if intent.status in {"requires_payment_method", "canceled"}:
            mark_order_payment_failed(order, db)
            raise HTTPException(status_code=402, detail="Payment failed. Please try another card.")
    except HTTPException:
        raise
    except Exception:
        logger.exception("Unexpected error confirming order %s", order_id)
        raise HTTPException(status_code=500, detail="Unable to confirm your payment. Please contact support.")

    raise HTTPException(
        status_code=409,
        detail=f"Payment is not complete yet. Current Stripe status: {intent.status}",
    )


@router.post("/mark-payment-failed/{order_id}", response_model=OrderResponse)
def mark_payment_failed(
    order_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    existing_order = (
        db.query(Order)
        .filter(Order.id == order_id, Order.user_id == current_user.id)
        .first()
    )
    if not existing_order:
        raise HTTPException(status_code=404, detail="Order not found")
    if not existing_order.payment_intent_id:
        raise HTTPException(status_code=400, detail="Order has no payment intent")

    try:
        intent = stripe.PaymentIntent.retrieve(existing_order.payment_intent_id)
    except stripe.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not intent_matches_order(intent, existing_order):
        raise HTTPException(status_code=400, detail="Payment intent does not match this order")

    order = (
        db.query(Order)
        .filter(Order.id == order_id, Order.user_id == current_user.id)
        .with_for_update()
        .first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    try:
        if intent.status == "succeeded":
            return finalize_paid_order(order, db, background_tasks)
        if intent.status in REPLACEABLE_PAYMENT_INTENT_STATUSES:
            return mark_order_payment_failed(order, db)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Unexpected error marking payment failed for order %s", order_id)
        raise HTTPException(status_code=500, detail="Unable to update order status. Please contact support.")

    raise HTTPException(
        status_code=409,
        detail=f"Payment is not failed. Current Stripe status: {intent.status}",
    )


@router.post("/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    if event["type"] == "payment_intent.succeeded":
        pi = event["data"]["object"]
        order = (
            db.query(Order)
            .filter(Order.payment_intent_id == pi["id"])
            .with_for_update()
            .first()
        )
        if order:
            try:
                if intent_matches_order(pi, order):
                    finalize_paid_order(order, db)
                else:
                    logger.warning("Ignoring mismatched succeeded PaymentIntent %s for order %s", pi["id"], order.id)
            except Exception:
                logger.exception("Error processing payment_intent.succeeded for order %s", order.id)

    elif event["type"] == "payment_intent.payment_failed":
        pi = event["data"]["object"]
        order = (
            db.query(Order)
            .filter(Order.payment_intent_id == pi["id"])
            .with_for_update()
            .first()
        )
        if order:
            try:
                if intent_matches_order(pi, order):
                    mark_order_payment_failed(order, db)
                else:
                    logger.warning("Ignoring mismatched failed PaymentIntent %s for order %s", pi["id"], order.id)
            except Exception:
                logger.exception("Error processing payment_intent.payment_failed for order %s", order.id)

    return {"status": "ok"}
