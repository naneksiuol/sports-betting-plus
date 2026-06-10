"""
Bet tracker — persists bets to Supabase `bets` table (RLS-protected).
Falls back to local data/bets.json when Supabase is not configured (dev/offline).
"""

import os
import json
import uuid
import math
import tempfile
import sys
from pathlib import Path
from datetime import datetime

if sys.platform != "win32":
    import fcntl
else:
    fcntl = None  # type: ignore

# ── Fallback file paths (used when Supabase not configured) ──────────────────

_BETS_FILE  = Path(__file__).parent.parent / "data" / "bets.json"
_LOCK_FILE  = Path(__file__).parent.parent / "data" / ".bets.lock"


# ── Supabase helpers ──────────────────────────────────────────────────────────

def _sb_url() -> str:
    return os.environ.get("SUPABASE_URL", "")


def _sb_anon_key() -> str:
    return os.environ.get("SUPABASE_ANON_KEY", "")


def _sb_service_key() -> str:
    return os.environ.get("SUPABASE_SERVICE_KEY", "")


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


def _service_client():
    """Service-role client for scripts running outside Streamlit (e.g. grader)."""
    if not _sb_url() or not _sb_service_key():
        return None
    try:
        from supabase import create_client
        return create_client(_sb_url(), _sb_service_key())
    except Exception:
        return None


# ── Row normalisation ─────────────────────────────────────────────────────────

def _row_to_bet(row: dict) -> dict:
    """Convert Supabase row dict to the canonical bet dict expected by the UI."""
    return {
        "id":           row.get("id", ""),
        "date":         str(row.get("date", "")),
        "time":         row.get("time", ""),
        "sport":        row.get("sport", ""),
        "player":       row.get("player", ""),
        "prop":         row.get("prop", ""),
        "line":         float(row["line"]) if row.get("line") is not None else None,
        "odds":         int(row["odds"]) if row.get("odds") is not None else 0,
        "stake":        float(row["stake"]) if row.get("stake") is not None else 0.0,
        "book":         row.get("book", ""),
        "result":       row.get("result", "pending"),
        "profit":       float(row["profit"]) if row.get("profit") is not None else None,
        "sharp_odds":   int(row["sharp_odds"]) if row.get("sharp_odds") is not None else None,
        "fair_est":     float(row["fair_est"]) if row.get("fair_est") is not None else None,
        "edge":         float(row["edge"]) if row.get("edge") is not None else None,
        "opening_clv":  float(row["opening_clv"]) if row.get("opening_clv") is not None else None,
        "closing_odds": int(row["closing_odds"]) if row.get("closing_odds") is not None else None,
        "clv":          float(row["clv"]) if row.get("clv") is not None else None,
        "notes":        row.get("notes", ""),
        "is_parlay":    bool(row.get("is_parlay", False)),
        "parlay_legs":  row.get("parlay_legs") or [],
    }


def _bet_to_row(bet: dict, user_id: str) -> dict:
    """Convert canonical bet dict to a Supabase upsert row."""
    return {
        "id":           bet["id"],
        "user_id":      user_id,
        "date":         bet.get("date") or datetime.now().strftime("%Y-%m-%d"),
        "time":         bet.get("time", ""),
        "sport":        bet.get("sport", ""),
        "player":       bet.get("player", ""),
        "prop":         bet.get("prop", ""),
        "line":         bet.get("line"),
        "odds":         bet.get("odds", 0),
        "stake":        bet.get("stake", 0.0),
        "book":         bet.get("book", ""),
        "result":       bet.get("result", "pending"),
        "profit":       bet.get("profit"),
        "sharp_odds":   bet.get("sharp_odds"),
        "fair_est":     bet.get("fair_est"),
        "edge":         bet.get("edge"),
        "opening_clv":  bet.get("opening_clv"),
        "closing_odds": bet.get("closing_odds"),
        "clv":          bet.get("clv"),
        "notes":        bet.get("notes", ""),
        "is_parlay":    bet.get("is_parlay", False),
        "parlay_legs":  bet.get("parlay_legs") or [],
    }


# ── JSON fallback helpers ─────────────────────────────────────────────────────

def _json_load() -> list[dict]:
    if not _BETS_FILE.exists():
        return []
    try:
        return json.loads(_BETS_FILE.read_text())
    except Exception:
        return []


def _json_save(bets: list[dict]):
    _BETS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.NamedTemporaryFile(
        mode="w", dir=_BETS_FILE.parent, delete=False, suffix=".tmp"
    )
    if fcntl is not None:
        _LOCK_FILE.touch(exist_ok=True)
        with open(_LOCK_FILE, "r") as _lf:
            fcntl.flock(_lf, fcntl.LOCK_EX)
            try:
                json.dump(bets, tmp, indent=2)
                tmp.flush()
                os.fsync(tmp.fileno())
                tmp.close()
                os.replace(tmp.name, _BETS_FILE)
            finally:
                fcntl.flock(_lf, fcntl.LOCK_UN)
    else:
        json.dump(bets, tmp, indent=2)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp.close()
        os.replace(tmp.name, _BETS_FILE)


# ── Public API ────────────────────────────────────────────────────────────────

def load_bets(user_id: str = None) -> list[dict]:
    """
    Load all bets for the given user (or current session user).
    Falls back to local JSON when Supabase is not configured.
    """
    uid = user_id or _session_user_id()

    if not _supabase_configured() or not uid:
        return _json_load()

    try:
        client = _authed_client()
        if client is None:
            return _json_load()
        resp = (
            client.table("bets")
            .select("*")
            .eq("user_id", uid)
            .order("date", desc=True)
            .order("time", desc=True)
            .execute()
        )
        return [_row_to_bet(r) for r in (resp.data or [])]
    except Exception:
        return _json_load()


def save_bets(bets: list[dict], user_id: str = None):
    """
    Upsert a full list of bets (used by closing_line_scraper and bulk ops).
    Falls back to local JSON when Supabase is not configured.
    """
    uid = user_id or _session_user_id()

    if not _supabase_configured() or not uid:
        _json_save(bets)
        return

    try:
        client = _authed_client()
        if client is None:
            _json_save(bets)
            return
        rows = [_bet_to_row(b, uid) for b in bets]
        if rows:
            client.table("bets").upsert(rows).execute()
    except Exception:
        _json_save(bets)


def _american_to_dec(odds: float) -> float:
    if odds > 0:
        return (odds / 100) + 1
    return (100 / abs(odds)) + 1


def _compute_clv(placed_odds: float, reference_odds: float) -> float:
    """
    CLV = log(p_ref / p_placed) × 100 in percentage points.
    Positive = you got better odds than the sharp/closing line.
    """
    try:
        from edge_model import closing_line_value
        return closing_line_value(placed_odds, reference_odds)
    except Exception:
        try:
            def _imp(o):
                o = float(o)
                return 100 / (100 + abs(o)) if o < 0 else o / (100 + o)
            p_ref    = _imp(reference_odds)
            p_placed = _imp(placed_odds)
            if p_ref <= 0 or p_placed <= 0:
                return 0.0
            return round(math.log(p_ref / p_placed) * 100, 2)
        except Exception:
            return 0.0


def add_bet(sport: str, player: str, prop: str, line: float, odds: int,
            stake: float, book: str = "", notes: str = "",
            sharp_odds: int = None, fair_est: float = None,
            is_parlay: bool = False, edge: float = None,
            parlay_legs: list = None) -> dict:
    """
    Log a new bet.  Automatically computes opening CLV if sharp_odds provided.
    """
    uid = _session_user_id()

    opening_clv = None
    if sharp_odds and sharp_odds != 0:
        opening_clv = _compute_clv(odds, sharp_odds)

    bet = {
        "id":           str(uuid.uuid4())[:8],
        "date":         datetime.now().strftime("%Y-%m-%d"),
        "time":         datetime.now().strftime("%H:%M"),
        "sport":        sport,
        "player":       player,
        "prop":         prop,
        "line":         line,
        "odds":         odds,
        "stake":        stake,
        "book":         book,
        "result":       "pending",
        "profit":       None,
        "sharp_odds":   sharp_odds,
        "fair_est":     fair_est,
        "edge":         round(edge, 4) if edge is not None else None,
        "opening_clv":  opening_clv,
        "closing_odds": None,
        "clv":          None,
        "notes":        notes,
        "is_parlay":    is_parlay,
        "parlay_legs":  parlay_legs or [],
    }

    if _supabase_configured() and uid:
        try:
            client = _authed_client()
            if client:
                client.table("bets").insert(_bet_to_row(bet, uid)).execute()
                return bet
        except Exception:
            pass

    # Fallback: append to JSON
    bets = _json_load()
    bets.append(bet)
    _json_save(bets)
    return bet


def update_result(bet_id: str, result: str, closing_odds: int = None,
                  user_id: str = None):
    """Update a bet result.  result: win | loss | push | void | pending"""
    uid = user_id or _session_user_id()

    # Compute profit
    def _profit(bet: dict, result: str) -> float | None:
        odds  = bet.get("odds", 0) or -110
        stake = bet.get("stake", 0)
        if result == "win":
            return round(
                stake * (100 / abs(odds)) if odds < 0 else stake * (odds / 100), 2
            )
        if result == "loss":
            return -round(stake, 2)
        if result == "push":
            return 0.0
        return None

    if _supabase_configured() and uid:
        try:
            client = _authed_client()
            if client:
                resp = (
                    client.table("bets")
                    .select("*")
                    .eq("id", bet_id)
                    .eq("user_id", uid)
                    .execute()
                )
                rows = resp.data or []
                if not rows:
                    return
                bet = _row_to_bet(rows[0])
                profit = _profit(bet, result)
                updates: dict = {"result": result, "profit": profit}
                if closing_odds and closing_odds != 0:
                    updates["closing_odds"] = closing_odds
                    updates["clv"] = _compute_clv(bet["odds"], closing_odds)
                elif bet.get("sharp_odds") and bet.get("clv") is None:
                    updates["clv"] = bet.get("opening_clv")
                client.table("bets").update(updates).eq("id", bet_id).eq("user_id", uid).execute()
                return
        except Exception:
            pass

    # Fallback: JSON
    bets = _json_load()
    for bet in bets:
        if bet["id"] == bet_id:
            bet["result"] = result
            bet["profit"] = _profit(bet, result)
            if closing_odds and closing_odds != 0:
                bet["closing_odds"] = closing_odds
                bet["clv"] = _compute_clv(bet["odds"], closing_odds)
            elif bet.get("sharp_odds") and bet.get("clv") is None:
                bet["clv"] = bet.get("opening_clv")
            break
    _json_save(bets)


def delete_bet(bet_id: str, user_id: str = None):
    uid = user_id or _session_user_id()

    if _supabase_configured() and uid:
        try:
            client = _authed_client()
            if client:
                client.table("bets").delete().eq("id", bet_id).eq("user_id", uid).execute()
                return
        except Exception:
            pass

    bets = [b for b in _json_load() if b["id"] != bet_id]
    _json_save(bets)


def get_clv_avg(n_recent: int = 30, user_id: str = None) -> float | None:
    """
    Return average CLV over the most recent n_recent settled bets.
    Returns None if fewer than 5 bets have CLV data.
    """
    bets    = load_bets(user_id)
    settled = [b for b in bets if b["result"] in ("win", "loss", "push")]
    clv_vals: list[float] = []
    for b in reversed(settled):
        clv = b.get("clv") if b.get("clv") is not None else b.get("opening_clv")
        if clv is not None:
            clv_vals.append(float(clv))
        if len(clv_vals) >= n_recent:
            break
    if len(clv_vals) < 5:
        return None
    return round(sum(clv_vals) / len(clv_vals), 3)


def get_stats(user_id: str = None) -> dict:
    bets    = load_bets(user_id)
    settled = [b for b in bets if b["result"] in ("win", "loss", "push")]
    voids   = [b for b in bets if b["result"] == "void"]
    wins    = [b for b in settled if b["result"] == "win"]
    losses  = [b for b in settled if b["result"] == "loss"]
    pending = [b for b in bets if b["result"] == "pending"]

    total_staked = sum(b["stake"] for b in settled)
    total_profit = sum(b["profit"] for b in settled if b["profit"] is not None)
    roi          = (total_profit / total_staked * 100) if total_staked > 0 else 0
    decisive     = [b for b in settled if b["result"] in ("win", "loss")]
    win_rate     = (len(wins) / len(decisive) * 100) if decisive else 0

    clv_bets   = [b for b in settled
                  if b.get("clv") is not None or b.get("opening_clv") is not None]
    clv_values = [
        b.get("clv") if b.get("clv") is not None else b.get("opening_clv")
        for b in clv_bets
    ]
    avg_clv = sum(clv_values) / len(clv_values) if clv_values else None

    pending_with_clv   = [b for b in pending if b.get("opening_clv") is not None]
    avg_opening_clv    = (
        sum(b["opening_clv"] for b in pending_with_clv) / len(pending_with_clv)
        if pending_with_clv else None
    )

    by_sport: dict[str, dict] = {}
    for b in settled:
        s = b["sport"]
        if s not in by_sport:
            by_sport[s] = {"wins": 0, "losses": 0, "profit": 0, "staked": 0}
        if b["result"] == "win":
            by_sport[s]["wins"] += 1
        elif b["result"] == "loss":
            by_sport[s]["losses"] += 1
        by_sport[s]["profit"] += b["profit"] or 0
        by_sport[s]["staked"] += b.get("stake", 0)
    for s in by_sport:
        stk = by_sport[s]["staked"]
        by_sport[s]["roi"] = round(by_sport[s]["profit"] / stk * 100, 1) if stk else 0

    return {
        "total_bets":      len(bets),
        "settled":         len(settled),
        "wins":            len(wins),
        "losses":          len(losses),
        "voids":           len(voids),
        "pending":         len(pending),
        "win_rate":        round(win_rate, 1),
        "total_staked":    round(total_staked, 2),
        "total_profit":    round(total_profit, 2),
        "roi":             round(roi, 2),
        "avg_clv":         round(avg_clv, 2) if avg_clv is not None else None,
        "avg_opening_clv": round(avg_opening_clv, 2) if avg_opening_clv is not None else None,
        "by_sport":        by_sport,
        "all_bets":        bets,
        "settled_bets":    settled,
    }
