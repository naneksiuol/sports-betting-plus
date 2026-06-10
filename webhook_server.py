"""
Stripe webhook handler — runs as a separate process alongside Streamlit.
Start with: python webhook_server.py
"""

import os
import sys
from pathlib import Path

# Load .env
_env = Path(__file__).parent / ".env"
try:
    from dotenv import load_dotenv
    load_dotenv(_env, override=True)
except ImportError:
    if _env.exists():
        for line in _env.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

sys.path.insert(0, str(Path(__file__).parent / "src"))

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import stripe
from supabase import create_client

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")
WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

PORT = int(os.environ.get("WEBHOOK_PORT", 8502))

_processed_events: set = set()


def _update_tier(user_id: str, tier: str):
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        print(f"[webhook] Supabase service key not configured — cannot update tier for {user_id}")
        return
    client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    client.table("profiles").update({"tier": tier}).eq("id", user_id).execute()
    print(f"[webhook] Updated user {user_id} → tier={tier}")


class WebhookHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/webhook":
            self.send_response(404)
            self.end_headers()
            return

        length = int(self.headers.get("Content-Length", 0))
        payload = self.rfile.read(length)
        sig = self.headers.get("Stripe-Signature", "")

        try:
            event = stripe.Webhook.construct_event(payload, sig, WEBHOOK_SECRET)
        except Exception as e:
            print(f"[webhook] Invalid signature: {e}")
            self.send_response(400)
            self.end_headers()
            return

        etype = event["type"]
        event_id = event["id"]
        data = event["data"]["object"]

        # Idempotency guard — skip already-processed events
        if event_id in _processed_events:
            print(f"[webhook] Duplicate event {event_id}, skipping")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"received": true}')
            return
        _processed_events.add(event_id)

        if etype == "checkout.session.completed":
            session = data
            meta = session.get("metadata", {})
            user_id = meta.get("user_id")
            tier = meta.get("tier", "standard")
            if user_id:
                _update_tier(user_id, tier)
                try:
                    if SUPABASE_URL and SUPABASE_SERVICE_KEY:
                        client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
                        client.table("profiles").update({
                            "stripe_customer_id": session.get("customer"),
                            "stripe_subscription_id": session.get("subscription"),
                        }).eq("id", user_id).execute()
                        print(f"[webhook] Saved stripe_customer_id/stripe_subscription_id for {user_id}")
                except Exception as exc:
                    print(f"[webhook] WARNING: could not save stripe IDs for {user_id}: {exc}")

        elif etype == "customer.subscription.created":
            meta = data.get("metadata", {})
            user_id = meta.get("user_id")
            if user_id:
                status = data.get("status")
                if status in ("active", "trialing"):
                    tier = meta.get("tier", "standard")
                elif status in ("canceled", "unpaid", "past_due", "incomplete_expired", "paused"):
                    tier = "free"
                else:
                    tier = meta.get("tier", "standard")
                _update_tier(user_id, tier)
                try:
                    if SUPABASE_URL and SUPABASE_SERVICE_KEY:
                        client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
                        client.table("profiles").update({
                            "stripe_customer_id": data.get("customer"),
                            "stripe_subscription_id": data.get("id"),
                        }).eq("id", user_id).execute()
                        print(f"[webhook] Saved stripe_customer_id/stripe_subscription_id for {user_id}")
                except Exception as exc:
                    print(f"[webhook] WARNING: could not save stripe IDs for {user_id}: {exc}")

        elif etype == "customer.subscription.updated":
            meta = data.get("metadata", {})
            user_id = meta.get("user_id")
            if user_id:
                status = data.get("status")
                if status in ("active", "trialing"):
                    tier = meta.get("tier", "standard")
                elif status in ("canceled", "unpaid", "past_due", "incomplete_expired", "paused"):
                    tier = "free"
                else:
                    tier = meta.get("tier", "standard")
                _update_tier(user_id, tier)

        elif etype == "invoice.payment_failed":
            sub_id = data.get("subscription")
            customer_id = data.get("customer")
            if SUPABASE_URL and SUPABASE_SERVICE_KEY:
                try:
                    client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
                    if sub_id:
                        rows = client.table("profiles").select("id").eq("stripe_subscription_id", sub_id).execute()
                    elif customer_id:
                        rows = client.table("profiles").select("id").eq("stripe_customer_id", customer_id).execute()
                    else:
                        rows = None
                    if rows and rows.data:
                        user_id = rows.data[0]["id"]
                        _update_tier(user_id, "past_due")
                    else:
                        print(f"[webhook] invoice.payment_failed: no profile found for sub={sub_id} customer={customer_id}")
                except Exception as exc:
                    print(f"[webhook] WARNING: could not handle invoice.payment_failed: {exc}")

        elif etype == "customer.subscription.deleted":
            meta = data.get("metadata", {})
            user_id = meta.get("user_id")
            if user_id:
                _update_tier(user_id, "free")

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"received": true}')

    def log_message(self, fmt, *args):
        print(f"[webhook] {fmt % args}")


if __name__ == "__main__":
    if not WEBHOOK_SECRET:
        raise RuntimeError("STRIPE_WEBHOOK_SECRET not set")
    print(f"[webhook] Listening on port {PORT}")
    HTTPServer(("0.0.0.0", PORT), WebhookHandler).serve_forever()
