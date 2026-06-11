"""
Closing Line Updater
====================
Fetches closing odds for pending bets and computes CLV.

Data source: The Odds API (licensed) — no Action Network dependency.

How it works:
  1. Loads pending bets from Supabase (or bets.json fallback)
  2. For each sport, fetches current/recent odds from The Odds API
  3. Matches props to bets using fuzzy player name matching
  4. Computes CLV via edge_model.closing_line_value and writes it back
  5. Falls back to sharp_odds stored at bet time if no live data available

Run nightly:  python src/closing_line_scraper.py
"""

import os
import sys
import time
import requests
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

from bet_tracker import load_bets, save_bets, _compute_clv

# ── Odds API helpers ──────────────────────────────────────────────────────────

_ODDS_API_BASE = "https://api.the-odds-api.com/v4"
_SPORT_KEYS = {
    "MLB":  "baseball_mlb",
    "NBA":  "basketball_nba",
    "WNBA": "basketball_wnba",
    "NHL":  "icehockey_nhl",
    "NFL":  "americanfootball_nfl",
}
_SHARP_BOOKS = ["pinnacle", "betfair_ex_eu", "bookmaker"]
_MARKET_MAP = {
    "batter_hits":            "batter_hits",
    "batter_home_runs":       "batter_home_runs",
    "batter_total_bases":     "batter_total_bases",
    "batter_rbis":            "batter_rbis",
    "batter_runs_scored":     "batter_runs_scored",
    "batter_stolen_bases":    "batter_stolen_bases",
    "pitcher_strikeouts":     "pitcher_strikeouts",
    "pitcher_hits_allowed":   "pitcher_hits_allowed",
    "pitcher_outs_recorded":  "pitcher_outs_recorded",
    "pitcher_walks":          "pitcher_walks",
    "player_points":          "player_points",
    "player_rebounds":        "player_rebounds",
    "player_assists":         "player_assists",
    "player_threes":          "player_threes",
    "player_points_rebounds_assists": "player_points_rebounds_assists",
    "player_goals":           "player_goals",
    "player_shots_on_goal":   "player_shots_on_goal",
    "player_saves":           "player_saves",
}


def _api_key() -> str:
    return os.environ.get("ODDS_API_KEY", "")


def _fetch_player_props(sport: str, event_id: str, market: str) -> dict:
    """
    Fetch player prop odds from The Odds API for a specific event + market.
    Returns {(player_lower, line): sharp_odds} dict.
    """
    key = _api_key()
    if not key:
        return {}
    sport_key = _SPORT_KEYS.get(sport)
    if not sport_key:
        return {}
    try:
        r = requests.get(
            f"{_ODDS_API_BASE}/sports/{sport_key}/events/{event_id}/odds",
            params={
                "apiKey":       key,
                "regions":      "us",
                "markets":      market,
                "bookmakers":   ",".join(_SHARP_BOOKS),
                "oddsFormat":   "american",
            },
            timeout=10,
        )
        if r.status_code != 200:
            return {}
        data = r.json()
    except Exception:
        return {}

    result: dict = {}
    for bm in data.get("bookmakers", []):
        for mkt in bm.get("markets", []):
            if mkt.get("key") != market:
                continue
            for outcome in mkt.get("outcomes", []):
                if outcome.get("name", "").lower() != "over":
                    continue
                player = outcome.get("description", "").lower().strip()
                line   = outcome.get("point")
                price  = outcome.get("price")
                if player and line is not None and price is not None:
                    k = (player, float(line))
                    if k not in result:
                        result[k] = int(price)
    return result


def _fetch_events(sport: str) -> list[dict]:
    """Fetch today's + recent events for a sport from The Odds API."""
    key      = _api_key()
    sport_key = _SPORT_KEYS.get(sport)
    if not key or not sport_key:
        return []
    try:
        r = requests.get(
            f"{_ODDS_API_BASE}/sports/{sport_key}/events",
            params={"apiKey": key},
            timeout=10,
        )
        if r.status_code != 200:
            return []
        return r.json()
    except Exception:
        return []


def _name_match(bet_player: str, api_player: str) -> bool:
    a = bet_player.lower().strip()
    b = api_player.lower().strip()
    if a == b:
        return True
    a_parts = a.split()
    b_parts = b.split()
    if len(a_parts) >= 2 and len(b_parts) >= 2:
        if a_parts[-1] == b_parts[-1] and a_parts[0][0] == b_parts[0][0]:
            return True
    # Containment check (handles "Jr.", accents, etc.)
    return (a in b) or (b in a)


def _extract_market(prop_str: str) -> str:
    return prop_str.split(" ")[0].strip() if prop_str else ""


# ── Main updater ──────────────────────────────────────────────────────────────

def update_closing_lines(dry_run: bool = False, user_id: str = None) -> int:
    """
    Fetch closing odds for all bets missing CLV and write results back.
    Returns count of bets updated.
    Uses The Odds API as the sole data source (no Action Network).
    """
    bets    = load_bets(user_id)
    updated = 0

    # Group bets missing CLV by sport
    by_sport: dict[str, list[dict]] = {}
    for b in bets:
        if b.get("clv") is not None:
            continue
        sp = b.get("sport", "")
        if sp:
            by_sport.setdefault(sp, []).append(b)

    if not by_sport:
        print("No bets missing CLV data.")
        return 0

    for sport, sport_bets in by_sport.items():
        print(f"  {sport}: checking {len(sport_bets)} bets…")

        if not _api_key():
            print("    ODDS_API_KEY not set — using sharp_odds fallback only")
        else:
            # Fetch events for this sport
            events = _fetch_events(sport)
            print(f"    {len(events)} events found")

            # Build a market→props lookup: market → {(player_lower, line): odds}
            market_props: dict[str, dict] = {}
            needed_markets = {_extract_market(b.get("prop", "")) for b in sport_bets}
            for market in needed_markets:
                if not market or market not in _MARKET_MAP:
                    continue
                combined: dict = {}
                for event in events[:20]:  # cap to avoid excessive API calls
                    props = _fetch_player_props(sport, event["id"], market)
                    combined.update(props)
                    time.sleep(0.1)
                if combined:
                    market_props[market] = combined

        for bet in sport_bets:
            player    = bet.get("player", "")
            market    = _extract_market(bet.get("prop", ""))
            line      = float(bet.get("line", 0.5))
            bet_odds  = int(bet.get("odds") or 0)
            closing_odds: int | None = None

            # 1. Try The Odds API closing props
            if _api_key() and market in market_props:
                for (api_player, api_line), odds in market_props[market].items():
                    if _name_match(player, api_player) and abs(api_line - line) < 0.1:
                        closing_odds = odds
                        break

            # 2. Fall back to sharp_odds stored at bet time
            if closing_odds is None and bet.get("sharp_odds"):
                closing_odds = int(bet["sharp_odds"])

            if closing_odds is None:
                continue

            clv = _compute_clv(bet_odds, closing_odds)
            print(f"    CLV  {player} {market}: {bet_odds:+d} vs close {closing_odds:+d} → CLV {clv:+.2f}%")

            if not dry_run:
                bet["closing_odds"] = closing_odds
                bet["clv"]          = clv
            updated += 1

    if not dry_run and updated:
        save_bets(bets, user_id)
        print(f"\n✅ Updated CLV for {updated} bet(s).")
    elif dry_run:
        print(f"\n[DRY RUN] Would update {updated} bet(s).")

    return updated


# ── Public alias expected by props_dashboard / test harness ──────────────────

def auto_close_pending_clv(dry_run: bool = False, user_id: str = None) -> int:
    """
    Alias for update_closing_lines() — fetches closing odds for all pending
    bets missing CLV and writes results back.

    Falls back to ``sharp_odds`` stored at bet time when ODDS_API_KEY is not
    set (handled transparently inside ``update_closing_lines``).

    Returns count of bets updated.
    """
    return update_closing_lines(dry_run=dry_run, user_id=user_id)


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run",  action="store_true", help="Preview without writing")
    p.add_argument("--user-id",  default=None,        help="Supabase user UUID (service-role mode)")
    args = p.parse_args()
    print(f"Closing Line Updater — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    n = update_closing_lines(dry_run=args.dry_run, user_id=args.user_id)
    print(f"Done. {n} bets updated.")
