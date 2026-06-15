"""
Watchlist — per-user saved props with injury push alerting.

Storage: Supabase `watched_props` table when configured, else
session-state in-memory (resets on page reload).

Injury alerts fire from the scheduled job (run_discord_slip.py) so
they reach users even when the app isn't open.
"""

from __future__ import annotations

import os
from typing import Any

_SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
_SUPABASE_KEY = os.environ.get("SUPABASE_ANON_KEY", "")


def _client(access_token: str | None = None):
    from supabase import create_client
    sb = create_client(_SUPABASE_URL, _SUPABASE_KEY)
    if access_token:
        try:
            sb.auth.set_session(access_token, "")
        except Exception:
            pass
    return sb


def _supabase_ok() -> bool:
    return bool(_SUPABASE_URL and _SUPABASE_KEY)


# ── CRUD ──────────────────────────────────────────────────────────────────────

def add_watch(user_id: str, player: str, sport: str, market: str,
              line: float | None, access_token: str | None = None) -> bool:
    """Star a prop. Returns True on success."""
    if not _supabase_ok():
        return False
    try:
        _client(access_token).table("watched_props").upsert({
            "user_id": user_id,
            "player":  player,
            "sport":   sport,
            "market":  market,
            "line":    line,
        }, on_conflict="user_id,player,sport,market").execute()
        return True
    except Exception as e:
        print(f"[watchlist] add_watch error: {e}")
        return False


def remove_watch(user_id: str, player: str, sport: str, market: str,
                 access_token: str | None = None) -> bool:
    """Unstar a prop."""
    if not _supabase_ok():
        return False
    try:
        (_client(access_token)
            .table("watched_props")
            .delete()
            .eq("user_id", user_id)
            .eq("player", player)
            .eq("sport", sport)
            .eq("market", market)
            .execute())
        return True
    except Exception as e:
        print(f"[watchlist] remove_watch error: {e}")
        return False


def get_watchlist(user_id: str, access_token: str | None = None) -> list[dict]:
    """Return all watched props for a user, newest first."""
    if not _supabase_ok():
        return []
    try:
        res = (_client(access_token)
               .table("watched_props")
               .select("*")
               .eq("user_id", user_id)
               .order("created_at", desc=True)
               .execute())
        return res.data or []
    except Exception as e:
        print(f"[watchlist] get_watchlist error: {e}")
        return []


def get_all_watchlist_service() -> list[dict]:
    """
    Fetch all rows (all users) using the service role key.
    Used by the scheduler job to check injuries without user tokens.
    """
    svc_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not _SUPABASE_URL or not svc_key:
        return []
    try:
        from supabase import create_client
        sb = create_client(_SUPABASE_URL, svc_key)
        res = sb.table("watched_props").select("*").execute()
        return res.data or []
    except Exception as e:
        print(f"[watchlist] get_all_watchlist_service error: {e}")
        return []


def mark_alerted(row_id: str, status: str) -> None:
    """Record the status we just alerted on so we don't re-alert."""
    svc_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not _SUPABASE_URL or not svc_key:
        return
    try:
        from supabase import create_client
        from datetime import datetime, timezone
        sb = create_client(_SUPABASE_URL, svc_key)
        sb.table("watched_props").update({
            "last_status": status,
            "alerted_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", row_id).execute()
    except Exception as e:
        print(f"[watchlist] mark_alerted error: {e}")


# ── Scheduler-side injury alert check ────────────────────────────────────────

def run_injury_alerts(sport: str | None = None) -> int:
    """
    Called from run_discord_slip.py after scraping.
    Queries all watched props, checks current ESPN injury status,
    and sends Discord + Telegram alerts when a watched player's
    status changes to Out/Doubtful/Questionable.

    Returns the number of alerts sent.
    """
    rows = get_all_watchlist_service()
    if not rows:
        return 0

    if sport:
        rows = [r for r in rows if r.get("sport", "").upper() == sport.upper()]

    # Build per-sport injury lists from ESPN (cached inside espn_service)
    # injury_map: sport_upper -> list[{"player", "team", "status", ...}]
    injury_map: dict[str, list] = {}
    try:
        from espn_service import get_injuries
        sports_needed = {r.get("sport", "").upper() for r in rows}
        for sp in sports_needed:
            if sp:
                injury_map[sp] = get_injuries(sp)
    except Exception:
        pass

    alerts_sent = 0
    _ALERT_STATUSES = {"Out", "Doubtful", "Questionable"}

    for row in rows:
        player   = row.get("player", "")
        sp       = row.get("sport", "").upper()
        market   = row.get("market", "")
        line     = row.get("line")
        last_st  = row.get("last_status") or ""
        row_id   = row.get("id", "")

        # Look up current status — espn_service returns list of dicts
        current_status = _lookup_injury_status(player, injury_map.get(sp, []))
        if not current_status or current_status not in _ALERT_STATUSES:
            # If player is now healthy and we had an alert, clear it
            if last_st in _ALERT_STATUSES:
                mark_alerted(row_id, "")
            continue

        # Only alert when status is new (avoids repeat pings every morning)
        if current_status == last_st:
            continue

        _send_injury_alert(player, sp, market, line, current_status)
        mark_alerted(row_id, current_status)
        alerts_sent += 1

    return alerts_sent


def _lookup_injury_status(player: str, injury_list: list) -> str:
    """
    Find injury status for a player.
    ESPN injury list: list of {"player", "team", "status", "detail", "sport"}.
    """
    if not injury_list or not player:
        return ""
    try:
        for item in injury_list:
            name = item.get("player") or item.get("name") or ""
            if _names_match(player, name):
                return item.get("status", "")
    except Exception:
        pass
    return ""


def _names_match(a: str, b: str) -> bool:
    """Loose name match: both are non-empty and one contains the other (normalized)."""
    def _norm(s: str) -> str:
        import unicodedata, re
        s = unicodedata.normalize("NFD", s)
        s = "".join(c for c in s if unicodedata.category(c) != "Mn")
        s = re.sub(r"[^\w\s]", "", s.lower())
        return " ".join(s.split())
    a, b = _norm(a), _norm(b)
    return bool(a and b and (a in b or b in a))


def _send_injury_alert(player: str, sport: str, market: str,
                       line: float | None, status: str) -> None:
    """Send injury alert via Discord and Telegram."""
    line_str = f" O{line}" if line is not None else ""
    msg = (
        f"🚑 **Watchlist Alert — {player}** is listed as **{status}**\n"
        f"Sport: {sport} · Prop: {market}{line_str}\n"
        f"PropLens • 21+ • Not betting advice • Gambling problem? 1-800-GAMBLER"
    )
    try:
        from discord_bot import is_configured as dc_ok, send as dc_send
        if dc_ok():
            dc_send(content=msg)
    except Exception as e:
        print(f"[watchlist] Discord alert error: {e}")

    try:
        from telegram_bot import is_configured as tg_ok, broadcast as tg_broadcast
        if tg_ok():
            tg_broadcast(msg)
    except Exception as e:
        print(f"[watchlist] Telegram alert error: {e}")
