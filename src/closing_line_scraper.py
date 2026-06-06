"""
Closing Line Auto-Scraper
=========================
Automatically fetches closing odds for pending bets and computes CLV.

How it works:
  1. Reads pending bets from bets.json
  2. For each bet, searches Action Network for the matching prop
  3. If the game is complete/final, records those odds as the closing line
  4. Falls back to the last known odds snapshot (odds_snapshots.json)
  5. Computes CLV via edge_model.closing_line_value and writes it back

Called by run_grader.bat nightly, or call manually:
    python src/closing_line_scraper.py
"""

import sys
import json
import time
import requests
from pathlib import Path
from datetime import datetime, date, timedelta

sys.path.insert(0, str(Path(__file__).parent))

from bet_tracker import load_bets, save_bets, _compute_clv
from scraper import SPORT_SLUG, PROP_TYPE_MAP, BOOK_IDS, HEADERS, _american_to_implied

SNAPSHOTS_FILE = Path(__file__).parent.parent / "data" / "odds_snapshots.json"


# ── Snapshot helpers ──────────────────────────────────────────────────────────

def _load_snapshots() -> dict:
    if not SNAPSHOTS_FILE.exists():
        return {}
    try:
        return json.loads(SNAPSHOTS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _snapshot_key(player: str, market: str, line: float) -> str:
    return f"{player.lower().strip()}|{market}|{line}"


def get_snapshot_odds(player: str, market: str, line: float) -> int | None:
    """Return last known odds from snapshots file for a player/market/line."""
    snaps = _load_snapshots()
    key   = _snapshot_key(player, market, line)
    # Search newest date first
    for day in sorted(snaps.keys(), reverse=True):
        if key in snaps[day]:
            return snaps[day][key].get("odds")
    return None


# ── Action Network closing odds fetch ────────────────────────────────────────

def _fetch_completed_games(sport: str) -> list[dict]:
    """Get yesterday's + today's games including completed ones."""
    slug = SPORT_SLUG.get(sport, sport.lower())
    try:
        r = requests.get(
            f"https://api.actionnetwork.com/web/v1/scoreboard/{slug}",
            params={"period": "game", "bookIds": BOOK_IDS},
            headers=HEADERS, timeout=12,
        )
        return r.json().get("games", [])
    except Exception:
        return []


def _fetch_closing_odds_for_game(game_id: int) -> dict:
    """
    Returns dict: {(player_lower, market, line): closing_over_odds}
    """
    try:
        r = requests.get(
            f"https://api.actionnetwork.com/web/v2/games/{game_id}/props",
            headers=HEADERS, timeout=10,
        )
        if r.status_code != 200:
            return {}
        data = r.json()
    except Exception:
        return {}

    result    = {}
    players   = data.get("players", {})
    pr_props  = data.get("player_props", {})
    CONSENSUS_ID = "15"
    OPEN_ID      = "30"

    for prop_key, prop_list in pr_props.items():
        market = PROP_TYPE_MAP.get(prop_key)
        if not market:
            continue
        if not isinstance(prop_list, list):
            prop_list = [prop_list]

        for prop in prop_list:
            pid = prop.get("player_id")
            if not pid:
                continue
            pid_str = str(pid)
            pinfo   = players.get(pid_str) or players.get(int(pid_str), {}) or {}
            name    = pinfo.get("full_name", "")
            if not name:
                continue

            lines     = prop.get("lines", {})
            line_val  = None
            best_odds = None

            for priority_id in [CONSENSUS_ID, OPEN_ID, "69", "68"]:
                blines = lines.get(priority_id) or lines.get(int(priority_id), [])
                if not isinstance(blines, list):
                    blines = [blines]
                for ln in blines:
                    if ln.get("side", "").lower() == "over" and ln.get("odds"):
                        line_val  = float(ln.get("value", 0.5))
                        best_odds = int(ln["odds"])
                        break
                if best_odds is not None:
                    break

            if best_odds is not None and line_val is not None:
                key = (name.lower(), market, line_val)
                result[key] = best_odds

    return result


def fetch_closing_odds(sport: str) -> dict:
    """
    Returns all available closing odds for a sport today.
    {(player_lower, market, line): closing_over_odds}
    """
    games      = _fetch_completed_games(sport)
    all_odds   = {}

    for game in games:
        status = game.get("status", "").lower()
        # Only use games that are final or in-progress (late) as closing reference
        if status not in ("complete", "final", "in-progress", "halftime"):
            continue
        gid     = game["id"]
        g_odds  = _fetch_closing_odds_for_game(gid)
        all_odds.update(g_odds)
        time.sleep(0.15)  # be polite to the API

    return all_odds


# ── Player name fuzzy match ───────────────────────────────────────────────────

def _name_match(bet_player: str, api_player: str) -> bool:
    """True if names are close enough to be the same player."""
    a = bet_player.lower().strip()
    b = api_player.lower().strip()
    if a == b:
        return True
    # Check if last name + first initial match
    a_parts = a.split()
    b_parts = b.split()
    if len(a_parts) >= 2 and len(b_parts) >= 2:
        if a_parts[-1] == b_parts[-1] and a_parts[0][0] == b_parts[0][0]:
            return True
    return False


def _extract_market_from_prop(prop_str: str) -> str:
    """Extract market key from prop string like 'pitcher_strikeouts O6.5 [3-leg parlay]'."""
    if not prop_str:
        return ""
    return prop_str.split(" ")[0].strip()


# ── Main updater ──────────────────────────────────────────────────────────────

def update_closing_lines(dry_run: bool = False) -> int:
    """
    Fetch closing odds for all pending/ungraded bets and write CLV.
    Returns count of bets updated.
    """
    bets    = load_bets()
    updated = 0

    # Group pending bets by sport
    by_sport: dict[str, list[dict]] = {}
    for b in bets:
        if b.get("clv") is not None:
            continue  # already has CLV
        sp = b.get("sport", "")
        if sp:
            by_sport.setdefault(sp, []).append(b)

    if not by_sport:
        print("No bets missing CLV data.")
        return 0

    for sport, sport_bets in by_sport.items():
        print(f"  {sport}: checking {len(sport_bets)} bets …")

        # Try live fetch from Action Network
        closing = {}
        try:
            closing = fetch_closing_odds(sport)
            print(f"    {len(closing)} closing lines fetched from Action Network")
        except Exception as e:
            print(f"    API fetch failed ({e}), falling back to snapshots")

        for bet in sport_bets:
            player  = bet.get("player", "")
            market  = _extract_market_from_prop(bet.get("prop", ""))
            line    = float(bet.get("line", 0.5))
            bet_odds = int(bet.get("odds", 0))

            # 1. Try live closing odds
            closing_odds = None
            for (ap, am, al), odds in closing.items():
                if _name_match(player, ap) and am == market and abs(al - line) < 0.1:
                    closing_odds = odds
                    break

            # 2. Fall back to snapshot (last recorded odds)
            if closing_odds is None:
                closing_odds = get_snapshot_odds(player, market, line)

            # 3. Fall back to sharp_odds stored at bet time
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
        save_bets(bets)
        print(f"\n✅ Updated CLV for {updated} bet(s).")
    elif dry_run:
        print(f"\n[DRY RUN] Would update {updated} bet(s).")

    return updated


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = p.parse_args()
    print(f"Closing Line Scraper — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    n = update_closing_lines(dry_run=args.dry_run)
    print(f"Done. {n} bets updated.")
