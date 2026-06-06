"""
Supabase authentication — login, signup, Google/Apple OAuth, session management.
"""

import os
import streamlit as st
from supabase import create_client, Client

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_ANON_KEY", "")


def get_client() -> Client:
    if not SUPABASE_URL or not SUPABASE_KEY:
        st.error("⚠️ Supabase not configured. Set SUPABASE_URL and SUPABASE_ANON_KEY in your .env file.")
        st.stop()
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def get_user() -> dict | None:
    """Return current user dict from session state, or None if not logged in."""
    return st.session_state.get("user")


def get_tier() -> str:
    """Return current user's tier: 'free', 'standard', or 'premium'."""
    user = get_user()
    if not user:
        return "free"
    return user.get("tier", "free")


def is_authenticated() -> bool:
    return get_user() is not None


def login(email: str, password: str) -> tuple[bool, str]:
    """Returns (success, error_message)."""
    try:
        client = get_client()
        res = client.auth.sign_in_with_password({"email": email, "password": password})
        user = res.user
        if user:
            profile = _fetch_profile(client, user.id)
            st.session_state["user"] = {
                "id": user.id,
                "email": user.email,
                "tier": profile.get("tier", "free"),
                "name": profile.get("full_name", email.split("@")[0]),
            }
            st.session_state["access_token"] = res.session.access_token
            return True, ""
        return False, "Invalid credentials"
    except Exception as e:
        msg = str(e)
        if "Invalid login credentials" in msg:
            return False, "Wrong email or password."
        if "Email not confirmed" in msg:
            return False, "Please confirm your email before logging in."
        return False, f"Login failed: {msg}"


def signup(email: str, password: str, full_name: str) -> tuple[bool, str]:
    """Returns (success, error_message)."""
    try:
        client = get_client()
        res = client.auth.sign_up({
            "email": email,
            "password": password,
            "options": {"data": {"full_name": full_name}},
        })
        if res.user:
            # Create profile row
            client.table("profiles").upsert({
                "id": res.user.id,
                "email": email,
                "full_name": full_name,
                "tier": "free",
            }).execute()
            return True, ""
        return False, "Signup failed — please try again."
    except Exception as e:
        msg = str(e)
        if "already registered" in msg.lower() or "already been registered" in msg.lower():
            return False, "That email is already registered. Try logging in."
        return False, f"Signup failed: {msg}"


def logout():
    try:
        get_client().auth.sign_out()
    except Exception:
        pass
    st.session_state.pop("user", None)
    st.session_state.pop("access_token", None)


def get_google_oauth_url() -> str:
    client = get_client()
    res = client.auth.sign_in_with_oauth({
        "provider": "google",
        "options": {
            "redirect_to": os.environ.get("OAUTH_REDIRECT_URL", "http://localhost:8501"),
        },
    })
    return res.url


def get_apple_oauth_url() -> str:
    client = get_client()
    res = client.auth.sign_in_with_oauth({
        "provider": "apple",
        "options": {
            "redirect_to": os.environ.get("OAUTH_REDIRECT_URL", "http://localhost:8501"),
        },
    })
    return res.url


def handle_oauth_callback():
    """Check URL params for OAuth tokens after redirect."""
    params = st.query_params
    access_token = params.get("access_token")
    refresh_token = params.get("refresh_token")
    if access_token and not is_authenticated():
        try:
            client = get_client()
            res = client.auth.set_session(access_token, refresh_token or "")
            user = res.user
            if user:
                profile = _fetch_profile(client, user.id)
                # Auto-create profile if first OAuth login
                if not profile:
                    name = (user.user_metadata or {}).get("full_name", user.email.split("@")[0])
                    client.table("profiles").upsert({
                        "id": user.id,
                        "email": user.email,
                        "full_name": name,
                        "tier": "free",
                    }).execute()
                    profile = {"tier": "free", "full_name": name}
                st.session_state["user"] = {
                    "id": user.id,
                    "email": user.email,
                    "tier": profile.get("tier", "free"),
                    "name": profile.get("full_name", user.email.split("@")[0]),
                }
                st.session_state["access_token"] = access_token
                # Clear tokens from URL
                st.query_params.clear()
                st.rerun()
        except Exception:
            pass


def refresh_tier():
    """Re-fetch tier from DB (call after Stripe webhook updates it)."""
    user = get_user()
    if not user:
        return
    try:
        client = get_client()
        profile = _fetch_profile(client, user["id"])
        if profile:
            st.session_state["user"]["tier"] = profile.get("tier", "free")
    except Exception:
        pass


def _fetch_profile(client: Client, user_id: str) -> dict:
    try:
        res = client.table("profiles").select("*").eq("id", user_id).single().execute()
        return res.data or {}
    except Exception:
        return {}
