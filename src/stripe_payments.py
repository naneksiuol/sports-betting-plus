"""
Stripe payment integration — checkout sessions, webhook handling, portal.
"""

import os
import stripe
import streamlit as st

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")

STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

# Fill these in after creating products in Stripe dashboard
PRICE_IDS = {
    "standard": os.environ.get("STRIPE_STANDARD_PRICE_ID", ""),
    "premium":  os.environ.get("STRIPE_PREMIUM_PRICE_ID", ""),
}

APP_URL = os.environ.get("APP_URL", "http://localhost:8501")


def create_checkout_session(user_id: str, user_email: str, tier: str) -> str | None:
    """Create a Stripe checkout session. Returns URL or None on failure."""
    price_id = PRICE_IDS.get(tier)
    if not price_id:
        st.error(f"Stripe price ID for '{tier}' not configured yet.")
        return None
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            mode="subscription",
            customer_email=user_email,
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=f"{APP_URL}?payment=success&tier={tier}",
            cancel_url=f"{APP_URL}?payment=cancelled",
            metadata={"user_id": user_id, "tier": tier},
            subscription_data={"metadata": {"user_id": user_id, "tier": tier}},
        )
        return session.url
    except Exception as e:
        st.error(f"Stripe error: {e}")
        return None


def create_portal_session(stripe_customer_id: str) -> str | None:
    """Customer billing portal — manage/cancel subscription."""
    try:
        session = stripe.billing_portal.Session.create(
            customer=stripe_customer_id,
            return_url=APP_URL,
        )
        return session.url
    except Exception as e:
        st.error(f"Stripe portal error: {e}")
        return None


def handle_webhook(payload: bytes, sig_header: str) -> dict | None:
    """Verify and parse Stripe webhook. Returns event dict or None."""
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
        return event
    except stripe.error.SignatureVerificationError:
        return None


def get_tier_from_event(event: dict) -> tuple[str, str] | None:
    """
    Extract (user_id, new_tier) from a checkout.session.completed
    or customer.subscription.deleted event.
    Returns None if not applicable.
    """
    etype = event.get("type")
    data = event["data"]["object"]

    if etype == "checkout.session.completed":
        meta = data.get("metadata", {})
        return meta.get("user_id"), meta.get("tier", "standard")

    if etype in ("customer.subscription.deleted", "customer.subscription.updated"):
        meta = data.get("metadata", {})
        user_id = meta.get("user_id")
        if not user_id:
            return None
        status = data.get("status")
        if status in ("canceled", "unpaid", "past_due"):
            return user_id, "free"
        return user_id, meta.get("tier", "standard")

    return None
