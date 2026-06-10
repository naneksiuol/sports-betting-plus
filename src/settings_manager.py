"""settings_manager.py — Load/save bankroll & unit-size settings.

Persistence strategy:
- If SUPABASE_URL is configured and a user is authenticated, settings are
  stored in the `settings` JSONB column on the `profiles` table.
- Otherwise falls back to local data/settings.json (dev / offline).
"""
import json
import os

_SETTINGS_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "settings.json")

_DEFAULTS: dict = {
    "starting_bankroll": 1000.0,
    "unit_size": 10.0,
    "kelly_multiplier": 0.25,
}


# ── Supabase helpers (mirrors bet_tracker.py) ─────────────────────────────────

def _sb_url() -> str:
    return os.environ.get("SUPABASE_URL", "")


def _sb_anon_key() -> str:
    return os.environ.get("SUPABASE_ANON_KEY", "")


def _supabase_configured() -> bool:
    return bool(_sb_url() and _sb_anon_key())


def _session_user_id() -> str | None:
    """Pull user_id from Streamlit session state when running inside the app."""
    try:
        import streamlit as st
        return st.session_state.get("user_id")
    except Exception:
        return None


def _session_tokens() -> tuple[str | None, str | None]:
    """Return (access_token, refresh_token) from Streamlit session state."""
    try:
        import streamlit as st
        return (
            st.session_state.get("access_token"),
            st.session_state.get("refresh_token"),
        )
    except Exception:
        return None, None


def _authed_client():
    """
    Return a Supabase client authenticated as the current user (anon key +
    JWT from session state).  Returns None if not configured or no session.
    """
    if not _supabase_configured():
        return None
    try:
        from supabase import create_client
        client = create_client(_sb_url(), _sb_anon_key())
        access, refresh = _session_tokens()
        if access:
            client.auth.set_session(access, refresh or "")
        return client
    except Exception:
        return None


# ── File fallback helpers ─────────────────────────────────────────────────────

def _file_load() -> dict:
    """Return settings from data/settings.json, falling back to defaults."""
    try:
        with open(_SETTINGS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        merged = dict(_DEFAULTS)
        merged.update(data)
        return merged
    except (FileNotFoundError, json.JSONDecodeError):
        return dict(_DEFAULTS)


def _file_save(d: dict) -> None:
    """Persist settings dict to data/settings.json."""
    os.makedirs(os.path.dirname(_SETTINGS_PATH), exist_ok=True)
    with open(_SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2)


# ── Public API ────────────────────────────────────────────────────────────────

def load_settings(user_id: str = None) -> dict:
    """
    Return settings for the given user (or current session user).
    Tries Supabase `profiles.settings` first; falls back to local JSON.
    """
    uid = user_id or _session_user_id()

    if _supabase_configured() and uid:
        try:
            client = _authed_client()
            if client is not None:
                resp = (
                    client.table("profiles")
                    .select("settings")
                    .eq("id", uid)
                    .single()
                    .execute()
                )
                data = (resp.data or {}).get("settings") or {}
                merged = dict(_DEFAULTS)
                merged.update(data)
                return merged
        except Exception:
            pass

    return _file_load()


def save_settings(d: dict, user_id: str = None) -> None:
    """
    Persist settings dict.
    Tries Supabase `profiles.settings` first; falls back to local JSON.
    """
    uid = user_id or _session_user_id()

    if _supabase_configured() and uid:
        try:
            client = _authed_client()
            if client is not None:
                client.table("profiles").upsert(
                    {"id": uid, "settings": d}
                ).execute()
                return
        except Exception:
            pass

    _file_save(d)
