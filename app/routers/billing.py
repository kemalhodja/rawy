"""Plan kataloğu ve abonelik özeti + Stripe checkout/webhook."""

import json

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import get_current_user
from app.models import User
from app.services.billing import plans_catalog, stripe_enabled, subscription_snapshot

router = APIRouter()


@router.get("/plans")
def get_plans():
    """Genel fiyatlandırma tablosu (auth gerekmez)."""
    return plans_catalog()


@router.get("/subscription")
def get_subscription(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mevcut kullanıcı: etkin plan, deneme, aylık ses kullanımı."""
    return subscription_snapshot(db, current_user)


@router.post("/stripe/checkout-session")
def create_checkout_session(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not stripe_enabled():
        raise HTTPException(400, "Stripe yapılandırması eksik")
    import stripe

    stripe.api_key = settings.STRIPE_SECRET_KEY

    customer_id = current_user.stripe_customer_id
    if not customer_id:
        customer = stripe.Customer.create(email=current_user.email)
        current_user.stripe_customer_id = customer.id
        db.commit()
        db.refresh(current_user)
        customer_id = customer.id

    session = stripe.checkout.Session.create(
        mode="subscription",
        customer=customer_id,
        line_items=[{"price": settings.STRIPE_PRICE_PRO_MONTHLY, "quantity": 1}],
        success_url=f"{settings.APP_PUBLIC_URL}/billing/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{settings.APP_PUBLIC_URL}/billing/cancel",
        metadata={"user_id": str(current_user.id), "plan": "pro"},
    )
    return {"checkout_url": session.url, "session_id": session.id}


@router.post("/stripe/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
    db: Session = Depends(get_db),
):
    import stripe

    payload = await request.body()
    secret = settings.STRIPE_WEBHOOK_SECRET
    if secret and stripe_signature:
        try:
            event = stripe.Webhook.construct_event(payload=payload, sig_header=stripe_signature, secret=secret)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Invalid stripe signature: {exc}") from exc
    else:
        try:
            event = json.loads(payload.decode("utf-8"))
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid webhook payload") from None

    etype = event.get("type")
    data = (event.get("data") or {}).get("object") or {}

    if etype == "checkout.session.completed":
        metadata = data.get("metadata") or {}
        uid = metadata.get("user_id")
        if uid and str(uid).isdigit():
            user = db.query(User).filter(User.id == int(uid)).first()
            if user:
                user.plan = "pro"
                user.billing_interval = "monthly"
                sub_id = data.get("subscription")
                if sub_id:
                    user.stripe_subscription_id = sub_id
                db.commit()
    elif etype in ("customer.subscription.deleted", "customer.subscription.paused"):
        sub_id = data.get("id")
        if sub_id:
            user = db.query(User).filter(User.stripe_subscription_id == sub_id).first()
            if user:
                user.plan = "starter"
                user.billing_interval = None
                user.stripe_subscription_id = None
                db.commit()

    return {"received": True, "type": etype}
