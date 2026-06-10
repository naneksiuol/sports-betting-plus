import os
import requests
import pandas as pd

ODDS_API_BASE = "https://api.the-odds-api.com/v4"

SPORTS_CONFIG = {
    "MLB": {
        "key": "baseball_mlb",
        "markets": [
            "batter_hits",
            "batter_home_runs",
            "batter_total_bases",
            "batter_rbis",
            "batter_runs_scored",
            "batter_stolen_bases",
            "batter_hits_runs_rbis",
            "pitcher_strikeouts",
            "pitcher_outs_recorded",
            "pitcher_hits_allowed",
            "pitcher_walks",
        ],
        "market_labels": {
            "batter_hits":          "1+ Hits",
            "batter_home_runs":     "Home Run",
            "batter_total_bases":   "Total Bases",
            "batter_rbis":          "RBIs",
            "batter_runs_scored":   "Runs Scored",
            "batter_stolen_bases":  "Stolen Bases",
            "batter_hits_runs_rbis":"Hits+Runs+RBIs",
            "pitcher_strikeouts":   "Pitcher Ks",
            "pitcher_outs_recorded":"Outs Recorded",
            "pitcher_hits_allowed": "Hits Allowed",
            "pitcher_walks":        "Pitcher Walks",
        },
        "icon": "⚾",
        "status": "live",
    },
    "NBA": {
        "key": "basketball_nba",
        "markets": [
            "player_points",
            "player_rebounds",
            "player_assists",
            "player_threes",
            "player_points_rebounds_assists",
            "player_points_rebounds",
            "player_points_assists",
            "player_rebounds_assists",
            "player_steals",
            "player_blocks",
            "player_turnovers",
            "player_double_double",
            "player_steals_blocks",
        ],
        "market_labels": {
            "player_points":                    "Points",
            "player_rebounds":                  "Rebounds",
            "player_assists":                   "Assists",
            "player_threes":                    "3-Pointers",
            "player_points_rebounds_assists":   "PRA",
            "player_points_rebounds":           "Pts+Reb",
            "player_points_assists":            "Pts+Ast",
            "player_rebounds_assists":          "Reb+Ast",
            "player_steals":                    "Steals",
            "player_blocks":                    "Blocks",
            "player_turnovers":                 "Turnovers",
            "player_double_double":             "Double-Double",
            "player_steals_blocks":             "Steals+Blocks",
        },
        "icon": "🏀",
        "status": "live",
    },
    "WNBA": {
        "key": "basketball_wnba",
        "markets": [
            "player_points",
            "player_rebounds",
            "player_assists",
            "player_threes",
            "player_points_rebounds_assists",
            "player_points_rebounds",
            "player_points_assists",
            "player_rebounds_assists",
        ],
        "market_labels": {
            "player_points":                    "Points",
            "player_rebounds":                  "Rebounds",
            "player_assists":                   "Assists",
            "player_threes":                    "3-Pointers",
            "player_points_rebounds_assists":   "PRA",
            "player_points_rebounds":           "Pts+Reb",
            "player_points_assists":            "Pts+Ast",
            "player_rebounds_assists":          "Reb+Ast",
        },
        "icon": "🏀",
        "status": "live",
    },
    "NHL": {
        "key": "icehockey_nhl",
        "markets": [
            "player_goals",
            "player_assists",
            "player_points",
            "player_shots_on_goal",
            "player_saves",
            "player_blocked_shots",
            "player_hits",
        ],
        "market_labels": {
            "player_goals":         "Goals",
            "player_assists":       "Assists",
            "player_points":        "Points (G+A)",
            "player_shots_on_goal": "Shots on Goal",
            "player_saves":         "Goalie Saves",
            "player_blocked_shots": "Blocked Shots",
            "player_hits":          "Hits",
        },
        "icon": "🏒",
        "status": "live",
    },
    "NFL": {
        "key": "americanfootball_nfl",
        "markets": ["player_pass_yds", "player_rush_yds", "player_reception_yds", "player_receptions", "player_pass_tds", "player_anytime_td"],
        "market_labels": {
            "player_pass_yds": "Pass Yards",
            "player_rush_yds": "Rush Yards",
            "player_reception_yds": "Rec Yards",
            "player_receptions": "Receptions",
            "player_pass_tds": "Pass TDs",
            "player_anytime_td": "Anytime TD",
        },
        "icon": "🏈",
        "status": "coming_soon",
        "coming_soon_msg": "NFL season starts September 2026. Player props will auto-populate when available.",
    },
    "NCAAF": {
        "key": "americanfootball_ncaaf",
        "markets": ["player_pass_yds", "player_rush_yds", "player_reception_yds", "player_receptions", "player_anytime_td"],
        "market_labels": {
            "player_pass_yds": "Pass Yards",
            "player_rush_yds": "Rush Yards",
            "player_reception_yds": "Rec Yards",
            "player_receptions": "Receptions",
            "player_anytime_td": "Anytime TD",
        },
        "icon": "🏈",
        "status": "coming_soon",
        "coming_soon_msg": "College Football season starts August 2026. Props will auto-populate at kickoff.",
    },
    "Horse Racing": {
        "key": None,
        "markets": [],
        "market_labels": {},
        "icon": "🏇",
        "status": "needs_api",
        "coming_soon_msg": "Horse racing requires a dedicated racing API (The Racing API ~$30/mo). See setup instructions below.",
    },
}


def _api_key():
    key = os.environ.get("ODDS_API_KEY", "")
    if not key:
        raise ValueError("ODDS_API_KEY not set")
    return key


def _american_to_implied(odds: float) -> float:
    if odds > 0:
        return 100 / (odds + 100)
    return abs(odds) / (abs(odds) + 100)


def _fetch_event_odds(event: dict, sport_key: str, markets_str: str, api_key: str) -> list[dict]:
    """Fetch odds for a single event. Designed for parallel execution."""
    event_id = event["id"]
    home = event.get("home_team", "")
    away = event.get("away_team", "")
    matchup = f"{away} @ {home}"
    try:
        resp = requests.get(
            f"{ODDS_API_BASE}/sports/{sport_key}/events/{event_id}/odds",
            params={
                "apiKey": api_key,
                "markets": markets_str,
                "oddsFormat": "american",
                "regions": "us",
                # Include extra books for accurate fair-prob calculation.
                # Fair prob uses all books' over+under pairs (Shin de-vig).
                # We show FD/DK odds in the UI but use consensus for fair estimate.
                # Pinnacle has the lowest vig in the industry — best "true price" calibrator.
                # FD/DK are the bet targets; Pinnacle + BetMGM + Caesars sharpen the fair estimate.
                "bookmakers": "pinnacle,fanduel,draftkings,betmgm,caesars,pointsbet",
            },
            timeout=10,
        )
        if resp.status_code in (422, 404):
            return []
        resp.raise_for_status()
    except Exception:
        return []

    # Collect over AND under per book so fair-prob calculation has both sides.
    # Key: (player, market, line) → {"over_odds": ..., "under_odds": ...}
    by_player: dict = {}
    data = resp.json()
    for book in data.get("bookmakers", []):
        book_key = book.get("key", book.get("title", "unk"))
        for market in book.get("markets", []):
            market_key = market["key"]
            # Group over/under pairs by player+line
            player_lines: dict = {}
            for outcome in market.get("outcomes", []):
                name = outcome.get("name", "")
                player_name = outcome.get("description", name)
                line = outcome.get("point", 0.5)
                price = outcome["price"]
                key = (player_name, market_key, line)
                if key not in player_lines:
                    player_lines[key] = {}
                if name == "Over":
                    player_lines[key]["over"] = price
                elif name == "Under":
                    player_lines[key]["under"] = price

            is_fd_dk = book_key in ("fanduel", "draftkings")
            for (player_name, mkt, line), sides in player_lines.items():
                pk = (player_name, mkt, line)
                if pk not in by_player:
                    by_player[pk] = {"over_list": [], "under_list": [], "fd_dk_over_list": []}
                if "over" in sides:
                    by_player[pk]["over_list"].append(sides["over"])
                    if is_fd_dk:
                        by_player[pk]["fd_dk_over_list"].append(sides["over"])
                if "under" in sides:
                    by_player[pk]["under_list"].append(sides["under"])

    rows = []
    for (player_name, market_key, line), data_d in by_player.items():
        if not data_d["over_list"]:
            continue
        # Best odds across ALL books (for fair-prob denominator)
        best_over_all = max(data_d["over_list"])
        # Best odds from FD or DK only (for displaying/betting)
        fd_dk_overs = data_d.get("fd_dk_over_list", [])
        if not fd_dk_overs:
            continue  # prop not on FD or DK — skip
        best_fd_dk_over = max(fd_dk_overs)
        rows.append({
            "player": player_name,
            "team": matchup,
            "market": market_key,
            "line": line,
            "over_odds": best_fd_dk_over,   # best FD/DK odds (what bettor uses)
            "all_over_odds": best_over_all,  # best odds any book (for fair prob)
            "under_odds": (sum(data_d["under_list"]) / len(data_d["under_list"])) if data_d["under_list"] else None,
            "book_implied": round(_american_to_implied(best_fd_dk_over), 4),
        })
    return rows


def _fetch_props_for_sport(sport_key: str, markets: list[str], max_events: int = 10) -> pd.DataFrame:
    """Fetch player props for a sport. All events fetched in parallel."""
    import time
    from concurrent.futures import ThreadPoolExecutor, as_completed

    last_exc = None
    for _attempt, _delay in enumerate([0, 2, 4]):
        if _delay:
            time.sleep(_delay)
        try:
            events_resp = requests.get(
                f"{ODDS_API_BASE}/sports/{sport_key}/events",
                params={"apiKey": _api_key()},
                timeout=10,
            )
            events_resp.raise_for_status()
            events = events_resp.json()
            break
        except Exception as exc:
            last_exc = exc
    else:
        import warnings
        warnings.warn(f"odds_client: events fetch failed for {sport_key} after 3 attempts: {last_exc}")
        return pd.DataFrame()
    if not events:
        return pd.DataFrame()

    markets_str = ",".join(markets)
    api_key = _api_key()
    rows = []

    # Fetch all events in parallel — 8 threads, 10s timeout each
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {
            pool.submit(_fetch_event_odds, ev, sport_key, markets_str, api_key): ev
            for ev in events[:max_events]
        }
        for future in as_completed(futures):
            try:
                rows.extend(future.result())
            except Exception:
                pass

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)

    # Per-player, per-market consensus:
    # Group all books' over + under odds to get a proper Shin de-vigged fair prob.
    # Then edge = fair_est - best_FD_DK_over_implied.
    from edge_model import consensus_fair_prob, american_to_implied as _ai

    def _compute_fair(group_rows):
        """
        Fair prob from all-books over+under pairs (Shin de-vig).
        Falls back to average implied / 1.07 if no matched pairs found.
        """
        over_dict = {i: r.get("all_over_odds", r["over_odds"]) for i, r in enumerate(group_rows)}
        under_dict = {}
        for i, r in enumerate(group_rows):
            if r.get("under_odds") is not None:
                under_dict[i] = r["under_odds"]
        fp = consensus_fair_prob(over_dict, under_dict, method="shin")
        if fp is None:
            imps = [_ai(o) for o in over_dict.values()]
            fp = (sum(imps) / len(imps)) / 1.07
        return min(fp, 0.99)

    # Rebuild: use best FD/DK over odds as bet price
    grp = df.groupby(["player", "market", "line"])
    records = []
    for (player, market, line), g in grp:
        rows_list = g.to_dict("records")
        fair = _compute_fair(rows_list)
        best_over = g["over_odds"].max()  # already filtered to FD/DK in _fetch_event_odds
        best_imp = _ai(best_over)
        records.append({
            "player": player,
            "team": g["team"].iloc[0],
            "market": market,
            "line": line,
            "over_odds": best_over,
            "book_implied": round(best_imp, 4),
            "fair_est": round(fair, 4),
            "edge": round(fair - best_imp, 4),
        })
    consensus = pd.DataFrame(records)

    if consensus.empty:
        return consensus
    return consensus[["player", "team", "market", "line", "over_odds", "book_implied", "fair_est", "edge"]]


def get_props(sport: str) -> pd.DataFrame:
    """Fetch all props for a given sport. Falls back to scraper if API unavailable or quota exhausted."""
    cfg = SPORTS_CONFIG.get(sport)
    if not cfg:
        raise ValueError(f"Unknown sport: {sport}. Choose from {list(SPORTS_CONFIG)}")

    api_ok = bool(_api_key()) and not quota_exhausted()

    if api_ok:
        try:
            df = _fetch_props_for_sport(cfg["key"], cfg["markets"])
            if not df.empty:
                return df
        except Exception:
            pass  # fall through to scraper

    # Fallback: scrape Action Network (no API key needed)
    try:
        from scraper import scrape_props
        df = scrape_props(sport)
        if not df.empty:
            return df
    except Exception:
        pass

    return pd.DataFrame()


_quota_cache: dict = {"remaining": None, "checked_at": 0.0}
_QUOTA_TTL = 120  # re-check quota at most every 2 minutes


def get_remaining_requests() -> dict:
    import time
    now = time.time()
    if _quota_cache["remaining"] is not None and now - _quota_cache["checked_at"] < _QUOTA_TTL:
        return {"requests_used": 0, "requests_remaining": _quota_cache["remaining"]}
    try:
        resp = requests.get(
            f"{ODDS_API_BASE}/sports",
            params={"apiKey": _api_key()},
            timeout=8,
        )
        remaining = int(resp.headers.get("x-requests-remaining", 500))
        used = int(resp.headers.get("x-requests-used", 0))
        _quota_cache["remaining"] = remaining
        _quota_cache["checked_at"] = now
        return {"requests_used": used, "requests_remaining": remaining}
    except Exception:
        return {"requests_used": 0, "requests_remaining": _quota_cache.get("remaining") or 0}


def quota_exhausted() -> bool:
    try:
        key = _api_key()
    except Exception:
        return True
    if not key:
        return True
    return get_remaining_requests().get("requests_remaining", 1) == 0


def get_game_lines(sport: str) -> pd.DataFrame:
    """
    Fetch consensus game lines (moneyline, spread, total) for a sport.
    Returns one row per game with columns:
      matchup, commence_time,
      away_ml, home_ml,
      away_spread, home_spread, spread_line,
      total_line, over_odds, under_odds
    Falls back to Action Network scoreboard for basic moneylines if API fails.
    """
    cfg = SPORTS_CONFIG.get(sport)
    if not cfg or not cfg.get("key"):
        return pd.DataFrame()

    try:
        resp = requests.get(
            f"{ODDS_API_BASE}/sports/{cfg['key']}/odds",
            params={
                "apiKey": _api_key(),
                "markets": "h2h,spreads,totals",
                "oddsFormat": "american",
                "regions": "us",
                "bookmakers": "fanduel,draftkings",
            },
            timeout=15,
        )
        resp.raise_for_status()
        events = resp.json()
    except Exception:
        # Fall back to Action Network scraper (no API key needed)
        try:
            from scraper import scrape_game_lines
            return scrape_game_lines(sport)
        except Exception:
            return pd.DataFrame()

    rows = []
    for event in events:
        home = event.get("home_team", "")
        away = event.get("away_team", "")
        matchup = f"{away} @ {home}"
        commence = event.get("commence_time", "")[:16].replace("T", " ") if event.get("commence_time") else ""

        # Aggregate odds across books
        ml: dict[str, list] = {"away": [], "home": []}
        spreads: dict[str, list] = {"away_line": [], "away_odds": [], "home_line": [], "home_odds": []}
        totals: dict[str, list] = {"line": [], "over": [], "under": []}

        for book in event.get("bookmakers", []):
            for mkt in book.get("markets", []):
                key = mkt["key"]
                outcomes = {o["name"]: o for o in mkt.get("outcomes", [])}

                if key == "h2h":
                    if away in outcomes:
                        ml["away"].append(outcomes[away]["price"])
                    if home in outcomes:
                        ml["home"].append(outcomes[home]["price"])

                elif key == "spreads":
                    if away in outcomes:
                        spreads["away_line"].append(outcomes[away].get("point", 0))
                        spreads["away_odds"].append(outcomes[away]["price"])
                    if home in outcomes:
                        spreads["home_line"].append(outcomes[home].get("point", 0))
                        spreads["home_odds"].append(outcomes[home]["price"])

                elif key == "totals":
                    if "Over" in outcomes:
                        totals["line"].append(outcomes["Over"].get("point", 0))
                        totals["over"].append(outcomes["Over"]["price"])
                    if "Under" in outcomes:
                        totals["under"].append(outcomes["Under"]["price"])

        def _avg(lst):
            return round(sum(lst) / len(lst)) if lst else None

        rows.append({
            "matchup":      matchup,
            "time":         commence,
            "away":         away,
            "home":         home,
            "away_ml":      _avg(ml["away"]),
            "home_ml":      _avg(ml["home"]),
            "away_spread":  round(sum(spreads["away_line"]) / len(spreads["away_line"]), 1) if spreads["away_line"] else None,
            "away_spread_odds": _avg(spreads["away_odds"]),
            "home_spread":  round(sum(spreads["home_line"]) / len(spreads["home_line"]), 1) if spreads["home_line"] else None,
            "home_spread_odds": _avg(spreads["home_odds"]),
            "total":        round(sum(totals["line"]) / len(totals["line"]), 1) if totals["line"] else None,
            "over_odds":    _avg(totals["over"]),
            "under_odds":   _avg(totals["under"]),
        })

    return pd.DataFrame(rows) if rows else pd.DataFrame()


# Legacy shim so send_daily_bets.py and any cached imports still work
def get_mlb_hits_props() -> pd.DataFrame:
    df = get_props("MLB")
    if df.empty:
        return df
    return df[df["market"] == "batter_hits"].drop(columns=["market"])
