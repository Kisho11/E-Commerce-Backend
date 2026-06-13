import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.order import Order, OrderStatus, PaymentStatus
from app.core.dependencies import get_current_user
from app.config import settings

stripe.api_key = settings.STRIPE_SECRET_KEY

router = APIRouter(prefix="/payments", tags=["Payments"])


@router.post("/create-payment-intent/{order_id}")
def create_payment_intent(
    order_id: int,
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
    if order.payment_status == PaymentStatus.paid:
        raise HTTPException(status_code=400, detail="Order is already paid")

    try:
        intent = stripe.PaymentIntent.create(
            amount=int(order.total_amount * 100),  # convert to cents
            currency="usd",
            metadata={"order_id": str(order.id), "user_id": str(current_user.id)},
        )
        order.payment_intent_id = intent.id
        db.commit()
        return {"client_secret": intent.client_secret, "payment_intent_id": intent.id}
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))


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
        order = db.query(Order).filter(Order.payment_intent_id == pi["id"]).first()
        if order:
            order.payment_status = PaymentStatus.paid
            order.status = OrderStatus.confirmed
            db.commit()

    elif event["type"] == "payment_intent.payment_failed":
        pi = event["data"]["object"]
        order = db.query(Order).filter(Order.payment_intent_id == pi["id"]).first()
        if order:
            order.payment_status = PaymentStatus.failed
            db.commit()

    return {"status": "ok"}
