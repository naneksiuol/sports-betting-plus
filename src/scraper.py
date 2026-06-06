"""
Fallback scraper using Action Network's public API.
Used automatically when The Odds API quota is exhausted.
No API key required.
"""

import requests
import pandas as pd

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

# FanDuel NJ (69) and DraftKings NJ (68) — bet targets, must have over to be shown
# Consensus (15) — market consensus line, posts BOTH sides on every prop: best fair-prob calibrator
# Open (30)      — opening/sharp line, also posts both sides: second-best calibrator
# BetMGM NJ (75), Caesars NV (49), BetRivers NJ (71) — extra books for depth
BOOK_IDS = "69,68,15,30,75,49,71"
FD_ID          = "69"
DK_ID          = "68"
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


def scrape_game_lines(sport: str) -> "pd.DataFrame":
    """
    Scrape consensus game lines from Action Network scoreboard.
    Returns one row per game with:
      matchup, time, away, home,
      away_ml, home_ml,
      away_spread, away_spread_odds, home_spread, home_spread_odds,
      total, over_odds, under_odds,
      away_team_total, home_team_total,          ← team totals (bonus)
      ml_away_public, ml_home_public,            ← public % when available
      ml_away_money, ml_home_money               ← money % when available
    """
    games = _get_games(sport)
    if not games:
        return pd.DataFrame()

    rows = []
    for game in games:
        teams = game.get("teams", [])
        away_id = game.get("away_team_id")
        away, home = "", ""
        for t in teams:
            if t.get("id") == away_id:
                away = t.get("abbr", t.get("display_name", ""))
            else:
                home = t.get("abbr", t.get("display_name", ""))

        matchup = f"{away} @ {home}" if away and home else f"Game {game['id']}"
        start = game.get("start_time", "")
        if start:
            start = start[:16].replace("T", " ")

        odds_list = game.get("odds", [])
        if not odds_list:
            continue

        # Aggregate across all books
        away_mls, home_mls = [], []
        away_spreads, away_spread_lines = [], []
        home_spreads, home_spread_lines = [], []
        totals, overs, unders = [], [], []
        away_totals, home_totals = [], []
        away_pub, home_pub = [], []
        away_money, home_money = [], []

        for o in odds_list:
            if not isinstance(o, dict):
                continue
            if o.get("ml_away"):    away_mls.append(o["ml_away"])
            if o.get("ml_home"):    home_mls.append(o["ml_home"])
            if o.get("spread_away") is not None: away_spreads.append(o["spread_away"])
            if o.get("spread_away_line"):        away_spread_lines.append(o["spread_away_line"])
            if o.get("spread_home") is not None: home_spreads.append(o["spread_home"])
            if o.get("spread_home_line"):        home_spread_lines.append(o["spread_home_line"])
            if o.get("total"):      totals.append(o["total"])
            if o.get("over"):       overs.append(o["over"])
            if o.get("under"):      unders.append(o["under"])
            if o.get("away_total"): away_totals.append(o["away_total"])
            if o.get("home_total"): home_totals.append(o["home_total"])
            if o.get("ml_away_public"):  away_pub.append(o["ml_away_public"])
            if o.get("ml_home_public"):  home_pub.append(o["ml_home_public"])
            if o.get("ml_away_money"):   away_money.append(o["ml_away_money"])
            if o.get("ml_home_money"):   home_money.append(o["ml_home_money"])

        rows.append({
            "matchup":          matchup,
            "time":             start,
            "away":             away,
            "home":             home,
            "away_ml":          _avg_odds(away_mls),
            "home_ml":          _avg_odds(home_mls),
            "away_spread":      _avg_line(away_spreads),
            "away_spread_odds": _avg_odds(away_spread_lines),
            "home_spread":      _avg_line(home_spreads),
            "home_spread_odds": _avg_odds(home_spread_lines),
            "total":            _avg_line(totals),
            "over_odds":        _avg_odds(overs),
            "under_odds":       _avg_odds(unders),
            "away_team_total":  _avg_line(away_totals),
            "home_team_total":  _avg_line(home_totals),
            "ml_away_public":   _avg_line(away_pub),
            "ml_home_public":   _avg_line(home_pub),
            "ml_away_money":    _avg_line(away_money),
            "ml_home_money":    _avg_line(home_money),
        })

    return pd.DataFrame(rows) if rows else pd.DataFrame()


def _get_games(sport: str) -> list[dict]:
    slug = SPORT_SLUG.get(sport, sport.lower())
    r = requests.get(
        f"https://api.actionnetwork.com/web/v1/scoreboard/{slug}",
        params={"period": "game", "bookIds": BOOK_IDS},
        headers=HEADERS, timeout=12,
    )
    r.raise_for_status()
    return r.json().get("games", [])


def _get_props_for_game(game_id: int) -> dict:
    try:
        r = requests.get(
            f"https://api.actionnetwork.com/web/v2/games/{game_id}/props",
            headers=HEADERS, timeout=8,
        )
        if r.status_code != 200:
            return {}
        return r.json()
    except Exception:
        return {}


def _process_game_props(game: dict) -> tuple[str, dict]:
    """Fetch and return (matchup, props_data) for one game. For parallel use."""
    game_id = game["id"]
    teams = game.get("teams", [])
    away_id = game.get("away_team_id")
    away, home = "", ""
    for t in teams:
        if t.get("id") == away_id:
            away = t.get("abbr", t.get("display_name", ""))
        else:
            home = t.get("abbr", t.get("display_name", ""))
    matchup = f"{away} @ {home}" if away and home else f"Game {game_id}"
    data = _get_props_for_game(game_id)
    return matchup, data


def scrape_props(sport: str) -> pd.DataFrame:
    """
    Scrape player props from Action Network — all games fetched in parallel.
    Only returns props available on FanDuel (69) or DraftKings (68).
    Uses Shin de-vig for fair probability.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from edge_model import consensus_fair_prob, american_to_implied as _imp

    games = _get_games(sport)
    if not games:
        return pd.DataFrame()

    rows = []

    # Fetch all games in parallel
    game_results = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(_process_game_props, g): g for g in games}
        for future in as_completed(futures):
            try:
                matchup, data = future.result()
                if data:
                    game_results[matchup] = data
            except Exception:
                pass

    for matchup, data in game_results.items():

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
                player_name = prop.get("player_abbr", "Unknown")
                if player_id:
                    pid_str = str(player_id)
                    pid_int = int(player_id) if str(player_id).isdigit() else None
                    player_info = players.get(pid_str) or players.get(pid_int) or {}
                    if player_info:
                        player_name = player_info.get("full_name", player_name)

                # Collect Over and Under per book — ALL books for fair-prob,
                # but require FD or DK to have the over to show the prop.
                lines = prop.get("lines", {})
                book_over: dict = {}
                book_under: dict = {}
                line_val = 0.5
                fd_over: float | None = None
                dk_over: float | None = None
                consensus_over: float | None = None   # book 15 — market consensus
                consensus_under: float | None = None
                open_over: float | None = None        # book 30 — opening/sharp line
                open_under: float | None = None

                # Pass 1: find the canonical line value from Consensus (15) or Open (30).
                # This anchors all books to the same line, avoiding alt-line pollution.
                canonical_val: float | None = None
                for bid_check in [CONSENSUS_ID, OPEN_ID, FD_ID, DK_ID]:
                    blines = lines.get(bid_check) or lines.get(
                        int(bid_check) if str(bid_check).isdigit() else bid_check, [])
                    if not isinstance(blines, list):
                        blines = [blines]
                    for l in blines:
                        if l.get("side", "").lower() == "over" and l.get("value") is not None:
                            canonical_val = float(l["value"])
                            break
                    if canonical_val is not None:
                        break
                if canonical_val is None:
                    continue  # can't determine line, skip

                line_val = canonical_val

                # Pass 2: collect over/under odds at the canonical line value only.
                for book_id, book_lines in lines.items():
                    if not isinstance(book_lines, list):
                        continue
                    for line in book_lines:
                        odds = line.get("odds")
                        val = line.get("value")
                        side = line.get("side", "").lower()
                        if odds is None or odds == 0:
                            continue
                        # Only accept lines that match the canonical value
                        if val is not None and float(val) != canonical_val:
                            continue
                        if side == "over":
                            # Keep first occurrence per book — first entry is the standard line
                            if book_id not in book_over:
                                book_over[book_id] = float(odds)
                            if str(book_id) == FD_ID and fd_over is None:
                                fd_over = float(odds)
                            elif str(book_id) == DK_ID and dk_over is None:
                                dk_over = float(odds)
                            elif str(book_id) == CONSENSUS_ID and consensus_over is None:
                                consensus_over = float(odds)
                            elif str(book_id) == OPEN_ID and open_over is None:
                                open_over = float(odds)
                        elif side == "under":
                            if book_id not in book_under:
                                book_under[book_id] = float(odds)
                            if str(book_id) == CONSENSUS_ID and consensus_under is None:
                                consensus_under = float(odds)
                            elif str(book_id) == OPEN_ID and open_under is None:
                                open_under = float(odds)

                # Only include prop if FanDuel OR DraftKings has it
                if fd_over is None and dk_over is None:
                    continue

                # Use best FD/DK odds for the bettor
                fd_dk_odds = [o for o in [fd_over, dk_over] if o is not None]
                best_over_odds = max(fd_dk_odds)
                best_over_implied = _imp(best_over_odds)

                # Tag which book(s) have it
                books_available = []
                if fd_over is not None:
                    books_available.append("FD")
                if dk_over is not None:
                    books_available.append("DK")
                book_tag = "/".join(books_available)

                # Fair probability — three-tier approach:
                # 1. Consensus (15) both sides → market consensus, best calibrator
                # 2. Open (30) both sides → sharp opening line, second best
                # 3. All books Shin de-vig → broad consensus from whatever is available
                # 4. Fallback: average implied / 1.07
                from edge_model import shin_devig
                if consensus_over is not None and consensus_under is not None:
                    fair_est = shin_devig(_imp(consensus_over), _imp(consensus_under))
                elif open_over is not None and open_under is not None:
                    fair_est = shin_devig(_imp(open_over), _imp(open_under))
                else:
                    fair_est = consensus_fair_prob(book_over, book_under, method="shin")
                    if fair_est is None:
                        if book_over:
                            all_imps = [_imp(o) for o in book_over.values()]
                            fair_est = (sum(all_imps) / len(all_imps)) / 1.07
                        else:
                            continue
                fair_est = min(fair_est, 0.99)

                # NegBin correction is a supplementary signal — useful when we have
                # an independent count model.  Applied to a devigged line alone it
                # over-corrects (especially for rare events like HRs with r=2),
                # pulling fair_est below book_implied and generating false negatives.
                # Keep it as a reference column; Shin-devig is the primary signal.
                from edge_model import negbin_fair_prob, MARKET_DISPERSION, DEFAULT_DISPERSION
                r_disp = MARKET_DISPERSION.get(market, DEFAULT_DISPERSION)
                fair_est_nb = negbin_fair_prob(line_val, fair_est, r_disp)

                # Primary edge: Shin devig vs best available over line
                edge         = round(fair_est - best_over_implied, 4)
                edge_negbin  = round(fair_est_nb - best_over_implied, 4)

                rows.append({
                    "player":           player_name,
                    "team":             matchup,
                    "market":           market,
                    "line":             line_val,
                    "over_odds":        round(best_over_odds),
                    "book_implied":     round(best_over_implied, 4),
                    "fair_est":         round(fair_est, 4),       # Shin-only (primary)
                    "fair_est_negbin":  round(fair_est_nb, 4),    # NegBin-corrected (reference)
                    "edge":             edge,                      # Shin-based (primary)
                    "edge_negbin":      edge_negbin,               # NegBin-based (reference)
                    "negbin_delta":     round(fair_est_nb - fair_est, 4),
                    "n_books":          len(fd_dk_odds),
                    "books":            book_tag,
                    "fd_odds":          round(fd_over) if fd_over is not None else None,
                    "dk_odds":          round(dk_over) if dk_over is not None else None,
                })

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df = df[df["player"] != "Unknown"]
    df = df.drop_duplicates(subset=["player", "market", "line"])
    cols = ["player", "team", "market", "line", "over_odds",
            "book_implied", "fair_est", "fair_est_negbin", "edge", "edge_negbin",
            "negbin_delta", "n_books", "books", "fd_odds", "dk_odds"]
    return df[[c for c in cols if c in df.columns]]
