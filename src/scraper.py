"""
Constants and helper functions shared across the sports-betting-plus codebase.

Action Network scraping has been removed. Game lines and props now come from
odds_client.py (The Odds API). scrape_game_lines() and scrape_props() are kept
as thin shims so legacy import sites continue to work without errors.
"""

import pandas as pd

# FanDuel NJ (69) and DraftKings NJ (68) — bet targets, must have over to be shown
# Consensus (15) — market consensus line, posts BOTH sides on every prop: best fair-prob calibrator
# Open (30)      — opening/sharp line, also posts both sides: second-best calibrator
# BetMGM NJ (75), Caesars NV (49), BetRivers NJ (71) — extra books for depth
# ESPN BET (45)  — additional bet target for line shopping
BOOK_IDS = "69,68,15,30,75,49,71,45,34,123"  # added BetOnline(34), Bookmaker(123)
FD_ID          = "69"
DK_ID          = "68"
ESPN_ID        = "45"
CONSENSUS_ID   = "15"   # market consensus — posts both over + under, most accurate
OPEN_ID        = "30"   # opening/sharp line — also both sides
SHARP_IDS      = {"15", "30"}  # these always have both sides → priority for Shin de-vig
BET_IDS        = {"69", "68"}  # books where bettors place the actual bet

# Action Network prop type key → our market key
PROP_TYPE_MAP = {
    # ── MLB ──
    "core_bet_type_36_hits":               "batter_hits",
    "core_bet_type_33_hr":                 "batter_home_runs",
    "core_bet_type_77_total_bases":        "batter_total_bases",
    "core_bet_type_34_rbi":               "batter_rbis",
    "core_bet_type_78_runs_scored":        "batter_runs_scored",
    "core_bet_type_73_stolen_bases":       "batter_stolen_bases",
    "core_bet_type_37_strikeouts":         "pitcher_strikeouts",
    "core_bet_type_42_pitching_outs":      "pitcher_outs_recorded",
    "core_bet_type_72_hits_allowed":       "pitcher_hits_allowed",
    "core_bet_type_76_walks":              "pitcher_walks",
    "core_bet_type_431_hits_runs_rbis":    "batter_hits_runs_rbis",
    # ── NBA ──
    "core_bet_type_27_points":             "player_points",
    "core_bet_type_23_rebounds":           "player_rebounds",
    "core_bet_type_26_assists":            "player_assists",
    "core_bet_type_21_3fgm":              "player_threes",
    "core_bet_type_85_points_rebounds_assists": "player_points_rebounds_assists",
    "core_bet_type_86_points_rebounds":    "player_points_rebounds",
    "core_bet_type_87_points_assists":     "player_points_assists",
    "core_bet_type_88_rebounds_assists":   "player_rebounds_assists",
    "core_bet_type_24_steals":            "player_steals",
    "core_bet_type_25_blocks":            "player_blocks",
    "core_bet_type_580_turnovers":        "player_turnovers",
    "core_bet_type_113_double-double":    "player_double_double",
    "core_bet_type_89_steals_blocks":     "player_steals_blocks",
    # ── NHL ──
    "core_bet_type_280_points":            "player_points",
    "core_bet_type_55_goals":              "player_goals",
    "core_bet_type_279_assists":           "player_assists",
    "core_bet_type_31_shots_on_goal":      "player_shots_on_goal",
    "core_bet_type_38_goaltender_saves":   "player_saves",
    "core_bet_type_277_blocks":            "player_blocked_shots",
}

SPORT_SLUG = {
    "MLB":  "mlb",
    "NBA":  "nba",
    "WNBA": "wnba",
    "NHL":  "nhl",
    "NFL":  "nfl",
}


def _american_to_implied(odds: float) -> float:
    if odds > 0:
        return 100 / (odds + 100)
    return abs(odds) / (abs(odds) + 100)


def _avg_odds(values: list) -> int | None:
    """Average a list of american odds, return rounded int or None."""
    clean = [v for v in values if v is not None and v != 0]
    return round(sum(clean) / len(clean)) if clean else None


def _avg_line(values: list) -> float | None:
    clean = [v for v in values if v is not None]
    return round(sum(clean) / len(clean), 1) if clean else None


def scrape_game_lines(sport: str) -> pd.DataFrame:
    """
    Game lines now come from odds_client.get_game_lines(). This shim exists
    so legacy import sites continue to work. Returns an empty DataFrame.
    """
    print(f"[scraper] scrape_game_lines({sport!r}) is deprecated — use odds_client.get_game_lines() instead.")
    return pd.DataFrame()


def scrape_props(sport: str) -> pd.DataFrame:
    """
    Delegate to odds_client._fetch_props_for_sport() if available.
    Falls back to an empty DataFrame if odds_client cannot be imported.
    """
    try:
        from odds_client import _fetch_props_for_sport, SPORTS_CONFIG
        cfg = SPORTS_CONFIG.get(sport)
        if not cfg or not cfg.get("key") or not cfg.get("markets"):
            print(f"[scraper] scrape_props({sport!r}): no config found in odds_client — returning empty DataFrame.")
            return pd.DataFrame()
        return _fetch_props_for_sport(cfg["key"], cfg["markets"])
    except ImportError:
        print("[scraper] scrape_props: could not import odds_client — returning empty DataFrame.")
        return pd.DataFrame()
