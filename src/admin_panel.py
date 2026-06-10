"""
Admin panel — only visible to users with is_admin = true.
"""

import os
import streamlit as st
import auth
from supabase import create_client


def _get_admin_client():
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        raise RuntimeError("Supabase service key not configured")
    return create_client(url, key)


def show_admin_panel():
    if not auth.is_admin():
        st.error("🚫 Access denied.")
        return

    st.markdown("## 🛠️ Admin Panel")
    st.caption("Only visible to admin accounts.")

    _user_management()
    st.divider()
    _subscription_management()
    st.divider()
    _discord_settings()


def _user_management():
    st.markdown("### 👥 User Management")

    try:
        client = _get_admin_client()
        res = client.table("profiles").select("id, email, full_name, tier, is_admin, created_at").order("created_at", desc=True).execute()
        users = res.data or []
    except Exception as e:
        st.error(f"Failed to load users: {e}")
        return

    st.caption(f"{len(users)} total users")

    for u in users:
        col1, col2, col3, col4 = st.columns([3, 2, 2, 2])
        with col1:
            label = f"{'👑 ' if u.get('is_admin') else ''}{u.get('full_name') or u['email']}"
            st.markdown(f"**{label}**  \n`{u['email']}`")
        with col2:
            tier = u.get("tier", "free")
            badges = {"free": "⚪ Free", "standard": "🔵 Standard", "premium": "🔥 Premium"}
            st.markdown(badges.get(tier, tier))
        with col3:
            new_tier = st.selectbox(
                "Tier", ["free", "standard", "premium"],
                index=["free", "standard", "premium"].index(tier),
                key=f"tier_select_{u['id']}",
                label_visibility="collapsed",
            )
        with col4:
            if st.button("Save", key=f"save_tier_{u['id']}"):
                try:
                    client.table("profiles").update({"tier": new_tier}).eq("id", u["id"]).execute()
                    st.success(f"Updated {u['email']} → {new_tier}")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))


def _subscription_management():
    st.markdown("### 💳 Manage Subscriptions")

    try:
        import stripe
        stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")
        subs = stripe.Subscription.list(limit=20, status="all")
        items = subs.get("data", [])
    except Exception as e:
        st.warning(f"Stripe not available: {e}")
        return

    if not items:
        st.info("No subscriptions found.")
        return

    for sub in items:
        cust = sub.get("customer", "")
        status = sub.get("status", "")
        tier_meta = sub.get("metadata", {}).get("tier", "—")
        user_id = sub.get("metadata", {}).get("user_id", "—")
        period_end = sub.get("current_period_end", 0)
        from datetime import datetime
        end_str = datetime.utcfromtimestamp(period_end).strftime("%Y-%m-%d") if period_end else "—"

        col1, col2, col3, col4 = st.columns([3, 2, 2, 2])
        with col1:
            st.markdown(f"`{sub['id']}`  \nCustomer: `{cust}`")
        with col2:
            color = "🟢" if status == "active" else "🔴"
            st.markdown(f"{color} {status}")
        with col3:
            st.markdown(f"**{tier_meta}** · renews {end_str}")
        with col4:
            if status == "active" and st.button("Cancel", key=f"cancel_{sub['id']}"):
                try:
                    stripe.Subscription.cancel(sub["id"])
                    st.success("Cancelled.")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))


def _discord_settings():
    st.markdown("### 📣 Discord Webhook")

    current = os.environ.get("DISCORD_WEBHOOK_URL", "")
    if current and current != "your_discord_webhook_url_here":
        st.success(f"✅ Connected: `{current[:50]}...`")
    else:
        st.warning("⚠️ No Discord webhook configured.")

    st.info("To update, set `DISCORD_WEBHOOK_URL` in your Streamlit Cloud secrets and redeploy.")

    if st.button("🧪 Send Test Message", key="admin_discord_test"):
        _send_discord_test(current)


def _send_discord_test(webhook_url: str):
    if not webhook_url or webhook_url == "your_discord_webhook_url_here":
        st.error("No webhook URL set.")
        return
    try:
        import requests
        r = requests.post(webhook_url, json={"content": "✅ Sports Betting Plus — Discord webhook test successful!"})
        if r.status_code in (200, 204):
            st.success("Test message sent!")
        else:
            st.error(f"Failed: HTTP {r.status_code}")
    except Exception as e:
        st.error(str(e))
