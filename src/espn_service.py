"""
ESPN public API service — injuries, news, scores, and prop grading.
No API key required.
"""

import re
import time
import unicodedata
from datetime import datetime
from typing import Optional

import requests
import pandas as pd

# ---------------------------------------------------------------------------
# Sport/league slug mappings
# ---------------------------------------------------------------------------

_SPORT_SLUGS: dict[str, str] = {
    "MLB":  "baseball/mlb",
    "NBA":  "basketball/nba",
    "WNBA": "basketball/wnba",
    "NHL":  "hockey/nhl",
}

_ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports"

# ---------------------------------------------------------------------------
# Module-level cache:  key → (data, fetched_at_epoch)
# ---------------------------------------------------------------------------

_cache: dict = {}


def _cache_get(key: str, ttl: int):
    """Return cached value if still fresh, else None."""
    entry = _cache.get(key)
    if entry is None:
        return None
    data, ts = entry
    if time.time() - ts < ttl:
        return data
    return None


def _cache_set(key: str, data) -> None:
    _cache[key] = (data, time.time())


# ---------------------------------------------------------------------------
# Name normalisation (mirrors result_grader._normalize)
# ---------------------------------------------------------------------------

_SUFFIX_RE = re.compile(r"\b(jr\.?|sr\.?|ii|iii|iv)\s*$", re.I)
_HYPHEN_RE = re.compile(r"-")
_APOS_RE   = re.compile(r"['\.]")
_PUNCT_RE  = re.compile(r"[^\w\s]")


def _normalize(name: str) -> str:
    nfd = unicodedata.normalize("NFD", name)
    ascii_approx = "".join(c for c in nfd if unicodedata.category(c) != "Mn")
    s = ascii_approx.lower().strip()
    s = _SUFFIX_RE.sub("", s).strip()
    s = _HYPHEN_RE.sub(" ", s)
    s = _APOS_RE.sub("", s)
    s = _PUNCT_RE.sub("", s)
    return " ".join(s.split())


def _fuzzy_name_match(a: str, b: str) -> bool:
    """True if either normalised name contains the other."""
    na, nb = _normalize(a), _normalize(b)
    return na in nb or nb in na


# ---------------------------------------------------------------------------
# ESPN stat maps for grading
# ---------------------------------------------------------------------------

# NBA/WNBA: ESPN box-score athlete stat keys
_NBA_ESPN_STAT_MAP: dict[str, object] = {
    "player_points":                  "points",
    "player_rebounds":                "rebounds",
    "player_assists":                 "assists",
    "player_threes":                  "threePointFieldGoalsMade",
    "player_steals":                  "steals",
    "player_blocks":                  "blocks",
    "player_turnovers":               "turnovers",
    "player_points_rebounds_assists": lambda s: s.get("points", 0) + s.get("rebounds", 0) + s.get("assists", 0),
    "player_points_rebounds":         lambda s: s.get("points", 0) + s.get("rebounds", 0),
    "player_points_assists":          lambda s: s.get("points", 0) + s.get("assists", 0),
    "player_rebounds_assists":        lambda s: s.get("rebounds", 0) + s.get("assists", 0),
    "player_steals_blocks":           lambda s: s.get("steals", 0) + s.get("blocks", 0),
    "player_double_double":           lambda s: int(
        (s.get("points", 0) >= 10 and s.get("rebounds", 0) >= 10)
        or (s.get("points", 0) >= 10 and s.get("assists", 0) >= 10)
        or (s.get("rebounds", 0) >= 10 and s.get("assists", 0) >= 10)
    ),
    "pra": lambda s: s.get("points", 0) + s.get("rebounds", 0) + s.get("assists", 0),
    "pts": "points",
    "reb": "rebounds",
    "ast": "assists",
    "stl": "steals",
    "blk": "blocks",
    "tov": "turnovers",
}

# MLB: ESPN box-score athlete stat keys (batting / pitching subobject)
_MLB_ESPN_STAT_MAP: dict[str, tuple] = {
    "pitcher_hits_allowed":  ("pitching", "hits"),
    "hits allowed":          ("pitching", "hits"),
    "pitcher_strikeouts":    ("pitching", "strikeouts"),
    "pitcher ks":            ("pitching", "strikeouts"),
    "pitcher_outs_recorded": ("pitching", "outs"),
    "outs recorded":         ("pitching", "outs"),
    "pitcher_saves":         ("pitching", "saves"),
    "pitcher_walks":         ("pitching", "walks"),
    "pitcher walks":         ("pitching", "walks"),
    "batter_hits":           ("batting", "hits"),
    "batter_home_runs":      ("batting", "homeRuns"),
    "batter_total_bases":    ("batting", "totalBases"),
    "batter_rbis":           ("batting", "RBI"),
    "batter_runs_scored":    ("batting", "runs"),
    "batter_stolen_bases":   ("batting", "stolenBases"),
    "batter_strikeouts":     ("batting", "strikeouts"),
    "1+ hits":               ("batting", "hits"),
    "home run":              ("batting", "homeRuns"),
    "total bases":           ("batting", "totalBases"),
    "stolen bases":          ("batting", "stolenBases"),
    "runs scored":           ("batting", "runs"),
    "hitter strikeouts":     ("batting", "strikeouts"),
    "hits+runs+rbis":        ("batting", "hits"),
    "hits":                  ("batting", "hits"),
    "rbis":                  ("batting", "RBI"),
    "rbi":                   ("batting", "RBI"),
    "runs":                  ("batting", "runs"),
    "saves":                 ("pitching", "saves"),
    "walks":                 ("pitching", "walks"),
    "outs":                  ("pitching", "outs"),
    "ks":                    ("pitching", "strikeouts"),
    "sb":                    ("batting", "stolenBases"),
    "tb":                    ("batting", "totalBases"),
    "hr":                    ("batting", "homeRuns"),
    "bb":                    ("pitching", "walks"),
    "sv":                    ("pitching", "saves"),
}

# NHL: ESPN box-score athlete stat keys
_NHL_ESPN_STAT_MAP: dict[str, object] = {
    "player_goals":         "goals",
    "player_assists":       "assists",
    "player_shots_on_goal": "shots",
    "player_saves":         "saves",
    "player_blocked_shots": "blockedShots",
    "player_hits":          "hits",
    "player_points":        lambda s: s.get("goals", 0) + s.get("assists", 0),
    "goals":   "goals",
    "assists": "assists",
    "shots":   "shots",
    "saves":   "saves",
}


def _sport_stat_map(sport: str) -> dict:
    su = sport.upper()
    if su in ("NBA", "WNBA"):
        return _NBA_ESPN_STAT_MAP
    if su == "NHL":
        return _NHL_ESPN_STAT_MAP
    return _MLB_ESPN_STAT_MAP


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slug(sport: str) -> Optional[str]:
    return _SPORT_SLUGS.get(sport.upper())


def _get(url: str, params: dict = None) -> Optional[dict]:
    try:
        r = requests.get(url, params=params, timeout=5)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# 1. get_injuries
# ---------------------------------------------------------------------------

def get_injuries(sport: str) -> list[dict]:
    """
    Returns list of injury records for the given sport.
    Each record: {"player", "team", "status", "detail", "sport"}
    5-minute in-memory cache.
    """
    cache_key = f"injuries:{sport.upper()}"
    cached = _cache_get(cache_key, ttl=300)
    if cached is not None:
        return cached

    slug = _slug(sport)
    if not slug:
        return []

    data = _get(f"{_ESPN_BASE}/{slug}/injuries")
    if not data:
        return []

    results: list[dict] = []
    for item in data.get("injuries", []):
        team_info = item.get("team", {})
        team_name = team_info.get("displayName") or team_info.get("abbreviation", "")
        for injury in item.get("injuries", []):
            athlete = injury.get("athlete", {})
            player_name = athlete.get("displayName") or athlete.get("fullName", "")
            if not player_name:
                continue
            raw_status = injury.get("status", "")
            # Normalise to canonical status values
            status_map = {
                "out":          "Out",
                "doubtful":     "Doubtful",
                "questionable": "Questionable",
                "day-to-day":   "Day-To-Day",
                "dtd":          "Day-To-Day",
                "probable":     "Probable",
            }
            status = status_map.get(raw_status.lower(), raw_status.title())
            detail = injury.get("shortComment") or injury.get("longComment") or ""
            results.append({
                "player": player_name,
                "team":   team_name,
                "status": status,
                "detail": detail,
                "sport":  sport.upper(),
            })

    _cache_set(cache_key, results)
    return results


# ---------------------------------------------------------------------------
# 2. get_news
# ---------------------------------------------------------------------------

def get_news(sport: str, limit: int = 10) -> list[dict]:
    """
    Returns list of news items for the given sport.
    Each record: {"headline", "description", "link", "published"}
    10-minute in-memory cache.
    """
    cache_key = f"news:{sport.upper()}:{limit}"
    cached = _cache_get(cache_key, ttl=600)
    if cached is not None:
        return cached

    slug = _slug(sport)
    if not slug:
        return []

    data = _get(f"{_ESPN_BASE}/{slug}/news", params={"limit": limit})
    if not data:
        return []

    results: list[dict] = []
    for article in data.get("articles", [])[:limit]:
        link = ""
        for lnk in article.get("links", {}).get("web", {}).values():
            if isinstance(lnk, dict):
                link = lnk.get("href", "")
            elif isinstance(lnk, str):
                link = lnk
            if link:
                break
        results.append({
            "headline":    article.get("headline", ""),
            "description": article.get("description", ""),
            "link":        link,
            "published":   article.get("published", ""),
        })

    _cache_set(cache_key, results)
    return results


# ---------------------------------------------------------------------------
# 3. flag_injured_props
# ---------------------------------------------------------------------------

def flag_injured_props(df: pd.DataFrame, sport: str) -> pd.DataFrame:
    """
    Adds an `injury_status` column to df (which must have a `player` column).
    Values: "Out", "Doubtful", "Questionable", "Day-To-Day", "Probable", ""
    Uses fuzzy name matching (either name contains the other after normalisation).
    """
    df = df.copy()
    injuries = get_injuries(sport)

    # Build normalised lookup: norm_name → status
    inj_lookup: dict[str, str] = {
        _normalize(inj["player"]): inj["status"]
        for inj in injuries
    }

    def _lookup_status(player_name: str) -> str:
        norm = _normalize(player_name)
        # Exact match first
        if norm in inj_lookup:
            return inj_lookup[norm]
        # Containment fuzzy match
        for inj_norm, status in inj_lookup.items():
            if norm in inj_norm or inj_norm in norm:
                return status
        return ""

    df["injury_status"] = df["player"].apply(_lookup_status)
    return df


# ---------------------------------------------------------------------------
# 4. get_scores
# ---------------------------------------------------------------------------

def get_scores(sport: str, date: str = None) -> list[dict]:
    """
    Returns list of game score records for the given sport and date.
    date format: "YYYYMMDD" (defaults to today).
    Each record: {"game_id", "home", "away", "home_score", "away_score",
                  "status", "completed"}
    """
    if date is None:
        date = datetime.now().strftime("%Y%m%d")

    cache_key = f"scores:{sport.upper()}:{date}"
    cached = _cache_get(cache_key, ttl=120)  # 2-min cache for live scores
    if cached is not None:
        return cached

    slug = _slug(sport)
    if not slug:
        return []

    data = _get(f"{_ESPN_BASE}/{slug}/scoreboard", params={"dates": date})
    if not data:
        return []

    results: list[dict] = []
    for event in data.get("events", []):
        game_id = str(event.get("id", ""))
        competition = (event.get("competitions") or [{}])[0]

        # Teams
        home_team = away_team = ""
        home_score = away_score = 0
        for competitor in competition.get("competitors", []):
            name = (competitor.get("team") or {}).get("displayName", "")
            score_str = competitor.get("score", "0") or "0"
            try:
                score = int(score_str)
            except (ValueError, TypeError):
                score = 0
            if competitor.get("homeAway") == "home":
                home_team  = name
                home_score = score
            else:
                away_team  = name
                away_score = score

        # Status
        state = (competition.get("status") or {}).get("type") or {}
        state_name = state.get("name", "").lower()
        completed  = bool(state.get("completed", False))
        if completed or "final" in state_name:
            status = "final"
        elif "in" in state_name or "progress" in state_name:
            status = "in_progress"
        else:
            status = "scheduled"

        results.append({
            "game_id":    game_id,
            "home":       home_team,
            "away":       away_team,
            "home_score": home_score,
            "away_score": away_score,
            "status":     status,
            "completed":  completed,
        })

    _cache_set(cache_key, results)
    return results


# ---------------------------------------------------------------------------
# 5. grade_from_espn
# ---------------------------------------------------------------------------

def _get_event_summary(sport: str, game_id: str) -> Optional[dict]:
    slug = _slug(sport)
    if not slug:
        return None
    return _get(f"{_ESPN_BASE}/{slug}/summary", params={"event": game_id})


def _extract_player_stats_from_summary(summary: dict, sport: str) -> dict[str, dict]:
    """
    Parse ESPN game summary → normalised_name → stat_dict.
    Works for NBA/WNBA (boxscore.players), MLB (boxscore.players), NHL (boxscore.players).
    """
    all_stats: dict[str, dict] = {}
    sport_up = sport.upper()

    boxscore = summary.get("boxscore") or {}
    players_groups = boxscore.get("players") or []

    for group in players_groups:
        statistics = group.get("statistics") or []
        for stat_group in statistics:
            names   = stat_group.get("names")    or []
            keys    = stat_group.get("keys")     or names
            athletes = stat_group.get("athletes") or []
            for athlete_entry in athletes:
                athlete = athlete_entry.get("athlete") or {}
                display_name = athlete.get("displayName") or athlete.get("fullName") or ""
                if not display_name:
                    continue
                stats_vals = athlete_entry.get("stats") or []
                stat_dict: dict = {}
                for i, val in enumerate(stats_vals):
                    if i < len(keys):
                        try:
                            stat_dict[keys[i]] = float(val)
                        except (ValueError, TypeError):
                            stat_dict[keys[i]] = val
                norm = _normalize(display_name)
                if norm not in all_stats:
                    all_stats[norm] = {}
                all_stats[norm].update(stat_dict)

    return all_stats


def _resolve_stat_value(stat_cfg, player_stats: dict) -> Optional[float]:
    """Apply stat config (str key or callable) against player_stats dict."""
    if callable(stat_cfg):
        try:
            return float(stat_cfg(player_stats))
        except Exception:
            return None
    val = player_stats.get(stat_cfg)
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def grade_from_espn(
    player: str,
    market: str,
    line: float,
    sport: str,
    game_date: str = None,
) -> Optional[str]:
    """
    Grade a player prop using ESPN game summary data.

    Returns "win", "loss", "push", or None if data is unavailable.
    game_date: "YYYYMMDD" (defaults to today).
    """
    try:
        if game_date is None:
            game_date = datetime.now().strftime("%Y%m%d")
        # Normalize to YYYYMMDD — ESPN API rejects YYYY-MM-DD format
        game_date = game_date.replace("-", "")

        # 1. Find the game that includes this player
        scores = get_scores(sport, game_date)
        if not scores:
            return None

        player_norm = _normalize(player)
        stat_map = _sport_stat_map(sport)

        # Resolve market key
        market_lower = market.lower()
        market_key: Optional[str] = None
        for key in sorted(stat_map.keys(), key=len, reverse=True):
            if key in market_lower:
                market_key = key
                break

        if market_key is None:
            return None

        stat_cfg = stat_map[market_key]

        # 2. Try each completed game to find the player
        for game in scores:
            if not game.get("completed"):
                continue  # skip in-progress / scheduled

            game_id = game["game_id"]
            cache_key = f"summary:{sport.upper()}:{game_id}"
            summary = _cache_get(cache_key, ttl=3600)
            if summary is None:
                summary = _get_event_summary(sport, game_id)
                if summary:
                    _cache_set(cache_key, summary)

            if not summary:
                continue

            all_stats = _extract_player_stats_from_summary(summary, sport)

            # Exact match
            player_stats = all_stats.get(player_norm)

            # Containment fuzzy match
            if player_stats is None:
                for norm_key, pstats in all_stats.items():
                    if player_norm in norm_key or norm_key in player_norm:
                        player_stats = pstats
                        break

            if player_stats is None:
                continue

            val = _resolve_stat_value(stat_cfg, player_stats)
            if val is None:
                return None

            if val > line:
                return "win"
            elif val < line:
                return "loss"
            return "push"

        return None

    except Exception:
        return None
