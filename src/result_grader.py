"""
Fetches MLB game results from the official MLB Stats API (free, no key needed)
and automatically grades pending bets in the tracker.
"""

import requests
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
import sys

# Force UTF-8 output so emoji print statements don't crash on Windows (cp1252)
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

sys.path.insert(0, str(Path(__file__).parent))
from bet_tracker import load_bets, update_result, save_bets

MLB_API = "https://statsapi.mlb.com/api/v1"

# Prop label → (stat_group, stat_field)
# IMPORTANT: longer/more-specific keys must come BEFORE shorter ones that are
# substrings of them (e.g. "pitcher_hits_allowed" before "hits"), because
# _parse_prop iterates in order and returns on first match.
PROP_STAT_MAP = {
    # ── Pitching (specific — must precede batting "hits", "runs", etc.) ──
    "pitcher_hits_allowed": ("pitching", "hits"),
    "hits allowed":         ("pitching", "hits"),
    "pitcher_strikeouts":   ("pitching", "strikeOuts"),
    "pitcher ks":           ("pitching", "strikeOuts"),
    "pitcher_outs_recorded":("pitching", "outs"),
    "outs recorded":        ("pitching", "outs"),
    "pitcher_saves":        ("pitching", "saves"),
    "pitcher_walks":        ("pitching", "baseOnBalls"),
    "pitcher walks":        ("pitching", "baseOnBalls"),
    # ── Batting ──
    "batter_hits":          ("batting", "hits"),
    "batter_home_runs":     ("batting", "homeRuns"),
    "batter_total_bases":   ("batting", "totalBases"),
    "batter_rbis":          ("batting", "rbi"),
    "batter_runs_scored":   ("batting", "runs"),
    "batter_stolen_bases":  ("batting", "stolenBases"),
    "batter_strikeouts":    ("batting", "strikeOuts"),
    "batter hits runs rbis":("batting", "hits"),   # composite — grade on hits component
    "1+ hits":              ("batting", "hits"),
    "home run":             ("batting", "homeRuns"),
    "total bases":          ("batting", "totalBases"),
    "stolen bases":         ("batting", "stolenBases"),
    "runs scored":          ("batting", "runs"),
    "hitter strikeouts":    ("batting", "strikeOuts"),
    "hits+runs+rbis":       ("batting", "hits"),
    "hits":                 ("batting", "hits"),
    "rbis":                 ("batting", "rbi"),
    "rbi":                  ("batting", "rbi"),
    "runs":                 ("batting", "runs"),
    "saves":                ("pitching", "saves"),
    "walks":                ("pitching", "baseOnBalls"),
    "outs":                 ("pitching", "outs"),
    "ks":                   ("pitching", "strikeOuts"),
    "sb":                   ("batting", "stolenBases"),
    "tb":                   ("batting", "totalBases"),
    "hr":                   ("batting", "homeRuns"),
    "bb":                   ("pitching", "baseOnBalls"),
    "sv":                   ("pitching", "saves"),
}


def _get_games_for_date(date_str: str) -> list[dict]:
    """Return list of Final games for a given date (YYYY-MM-DD)."""
    r = requests.get(f"{MLB_API}/schedule",
                     params={"sportId": 1, "date": date_str},
                     timeout=15)
    r.raise_for_status()
    dates = r.json().get("dates", [])
    if not dates:
        return []
    return [g for g in dates[0].get("games", [])
            if g.get("status", {}).get("abstractGameState") == "Final"]


def _get_player_stats(game_pk: int) -> dict[str, dict]:
    """
    Returns dict keyed by normalized player name → stats dict.
    Stats dict has 'batting' and 'pitching' sub-dicts.
    """
    r = requests.get(f"{MLB_API}/game/{game_pk}/boxscore", timeout=15)
    r.raise_for_status()
    bs = r.json()
    stats = {}
    for side in ("home", "away"):
        players = bs.get("teams", {}).get(side, {}).get("players", {})
        for pid, p in players.items():
            name = p.get("person", {}).get("fullName", "")
            if not name:
                continue
            batting = p.get("stats", {}).get("batting", {})
            pitching = p.get("stats", {}).get("pitching", {})
            # Calculate totalBases if not present
            if batting and "totalBases" not in batting:
                batting["totalBases"] = (
                    batting.get("hits", 0)
                    + batting.get("doubles", 0)
                    + batting.get("triples", 0) * 2
                    + batting.get("homeRuns", 0) * 3
                )
            stats[_normalize(name)] = {
                "batting": batting,
                "pitching": pitching,
                "full_name": name,
            }
    return stats


def _normalize(name: str) -> str:
    return name.lower().strip()


def _parse_prop(prop_str: str) -> tuple[str | None, float | None]:
    """
    Parse prop string like 'pitcher_hits_allowed O5.5 [SGP]'
    Returns (market_key, line) or (None, None).
    """
    prop_lower = prop_str.lower()

    # Extract line from O{number}
    line_match = re.search(r'o([\d.]+)', prop_lower)
    line = float(line_match.group(1)) if line_match else None

    # Match market
    for key in PROP_STAT_MAP:
        if key in prop_lower:
            return key, line

    return None, line


def _grade_bet(actual_val: float, line: float) -> str:
    if actual_val > line:
        return "win"
    elif actual_val < line:
        return "loss"
    else:
        return "push"


def grade_pending_bets(target_date: str = None, dry_run: bool = False) -> dict:
    """
    Grade all pending bets for target_date (default: yesterday).
    Returns summary dict.
    """
    if target_date is None:
        target_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    print(f"🔍 Grading bets for {target_date}...")

    # Get all Final games
    games = _get_games_for_date(target_date)
    print(f"✅ Found {len(games)} Final games")

    if not games:
        return {"graded": 0, "skipped": 0, "date": target_date, "error": "No final games found"}

    # Build player stats from all games
    all_player_stats = {}
    for game in games:
        try:
            stats = _get_player_stats(game["gamePk"])
            all_player_stats.update(stats)
        except Exception as e:
            print(f"  ⚠️ Could not fetch game {game['gamePk']}: {e}")

    print(f"📊 Loaded stats for {len(all_player_stats)} players")

    # Load pending bets for target_date
    bets = load_bets()
    pending = [b for b in bets if b["result"] == "pending" and b.get("date") == target_date]
    print(f"📋 Found {len(pending)} pending bets for {target_date}")

    graded = 0
    skipped = []

    for bet in pending:
        player_norm = _normalize(bet["player"])
        prop_str = bet.get("prop", "")
        line = bet.get("line")

        # Parse prop
        market_key, parsed_line = _parse_prop(prop_str)
        if parsed_line is not None:
            line = parsed_line

        if not market_key or line is None:
            skipped.append(f"{bet['player']} — could not parse prop: {prop_str}")
            continue

        stat_group, stat_field = PROP_STAT_MAP[market_key]

        # Find player in stats
        player_stats = all_player_stats.get(player_norm)
        if not player_stats:
            # Fuzzy match: check if any key contains the last name
            last_name = player_norm.split()[-1] if player_norm.split() else ""
            matches = [k for k in all_player_stats if last_name in k]
            if len(matches) == 1:
                player_stats = all_player_stats[matches[0]]
            else:
                skipped.append(f"{bet['player']} — not found in boxscores")
                continue

        actual_val = player_stats.get(stat_group, {}).get(stat_field)
        if actual_val is None:
            skipped.append(f"{bet['player']} — stat {stat_group}.{stat_field} not found")
            continue

        result = _grade_bet(float(actual_val), float(line))

        if not dry_run:
            update_result(bet["id"], result)

        emoji = {"win": "✅", "loss": "❌", "push": "↩️"}.get(result, "?")
        print(f"  {emoji} {bet['player']} | {prop_str} | actual={actual_val} vs line={line} → {result.upper()}")
        graded += 1

    summary = {
        "date": target_date,
        "graded": graded,
        "skipped": len(skipped),
        "skipped_details": skipped,
        "total_player_stats": len(all_player_stats),
    }

    print(f"\n📈 Done: {graded} graded, {len(skipped)} skipped")
    if skipped:
        print("Skipped:")
        for s in skipped:
            print(f"  - {s}")

    return summary


if __name__ == "__main__":
    import sys
    dry = "--dry-run" in sys.argv
    date_arg = next((a for a in sys.argv[1:] if a.startswith("20")), None)
    result = grade_pending_bets(target_date=date_arg, dry_run=dry)
    print(json.dumps(result, indent=2))
