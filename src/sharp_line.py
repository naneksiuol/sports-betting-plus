"""
Sharp line benchmark using consensus book (book ID 15 on Action Network).
Book 15 = Consensus line — the market's best estimate of fair value.
Pinnacle (book 3) is included when available for extra validation.

CLV = your odds - closing/consensus line. Positive = you beat the market.
"""

import requests
import json
from pathlib import Path
from datetime import datetime

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

# Sharp books to prioritize as benchmarks
SHARP_BOOK_IDS = {
    "15": "Consensus",
    "3": "Pinnacle",
    "78": "Circa",
    "34": "Bookmaker",
}

SPORT_SLUG = {
    "MLB": "mlb",
    "NBA": "nba",
    "WNBA": "wnba",
    "NHL": "nhl",
}

# All book IDs including sharp books
ALL_BOOK_IDS = "3,15,30,34,49,68,69,71,75,78,123,247"


def _american_to_implied(odds: float) -> float:
    if odds > 0:
        return 100 / (odds + 100)
    return abs(odds) / (abs(odds) + 100)


def get_sharp_lines(sport: str) -> dict:
    """
    Returns dict keyed by (player, market, line) ->
    {
      'consensus_odds': int,
      'consensus_implied': float,
      'sharp_book': str,
      'all_books': {book_name: odds}
    }
    """
    from scraper import PROP_TYPE_MAP, _get_games, _get_props_for_game

    slug = SPORT_SLUG.get(sport, sport.lower())

    try:
        r = requests.get(
            f"https://api.actionnetwork.com/web/v1/scoreboard/{slug}",
            params={"period": "game", "bookIds": ALL_BOOK_IDS},
            headers=HEADERS, timeout=12
        )
        games = r.json().get("games", [])
    except Exception:
        return {}

    sharp_lines = {}

    for game in games:
        game_id = game["id"]

        try:
            r2 = requests.get(
                f"https://api.actionnetwork.com/web/v2/games/{game_id}/props",
                headers=HEADERS, timeout=12
            )
            if r2.status_code != 200:
                continue
            data = r2.json()
        except Exception:
            continue

        player_props = data.get("player_props", {})
        players = data.get("players", {})

        for prop_type_key, prop_list in player_props.items():
            market = PROP_TYPE_MAP.get(prop_type_key)
            if not market:
                continue
            if not isinstance(prop_list, list):
                prop_list = [prop_list]

            for prop in prop_list:
                player_id = prop.get("player_id")
                player_name = "Unknown"
                if player_id:
                    pid_str = str(player_id)
                    pid_int = int(player_id) if str(player_id).isdigit() else None
                    pinfo = players.get(pid_str) or players.get(pid_int) or {}
                    player_name = pinfo.get("full_name", "Unknown")

                if player_name == "Unknown":
                    continue

                lines = prop.get("lines", {})
                line_val = 0.5
                book_over_odds = {}

                for book_id, book_lines in lines.items():
                    if not isinstance(book_lines, list):
                        continue
                    for line in book_lines:
                        if line.get("side", "").lower() != "over":
                            continue
                        odds = line.get("odds")
                        val = line.get("value", 0.5)
                        if odds and odds != 0:
                            book_name = SHARP_BOOK_IDS.get(book_id, f"Book_{book_id}")
                            book_over_odds[book_name] = float(odds)
                            if val:
                                line_val = float(val)

                if not book_over_odds:
                    continue

                # Prefer Consensus > Pinnacle > Circa > best available
                consensus_odds = None
                sharp_book = None
                for preferred in ["Consensus", "Pinnacle", "Circa", "Bookmaker"]:
                    if preferred in book_over_odds:
                        consensus_odds = book_over_odds[preferred]
                        sharp_book = preferred
                        break

                if consensus_odds is None:
                    # Use average of all available
                    consensus_odds = sum(book_over_odds.values()) / len(book_over_odds)
                    sharp_book = "Market Avg"

                key = (player_name.lower(), market, line_val)
                sharp_lines[key] = {
                    "consensus_odds": round(consensus_odds),
                    "consensus_implied": round(_american_to_implied(consensus_odds), 4),
                    "sharp_book": sharp_book,
                    "all_books": book_over_odds,
                    "n_books": len(book_over_odds),
                }

    return sharp_lines


def compute_clv(placed_odds: float, consensus_odds: float) -> float:
    """
    CLV in percentage points.
    Positive = you beat the market (good).
    """
    p_imp = _american_to_implied(placed_odds)
    c_imp = _american_to_implied(consensus_odds)
    return round((c_imp - p_imp) * 100, 2)
