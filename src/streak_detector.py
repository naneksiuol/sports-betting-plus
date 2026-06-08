"""
streak_detector.py — Hot streak detection for player props.

Fetches recent game logs via free public APIs (same sources as result_grader.py)
and counts how many of the last N games a player exceeded a given line.

Public API:
  get_player_streak(player, market, sport, line, n_games=5) -> dict
  get_streaks_for_df(df, sport) -> pd.DataFrame (adds "streak" and "hot" columns)
"""

import re
import unicodedata
import requests
import pandas as pd

# ── Reuse normalisation + market maps from result_grader ─────────────────────

_SUFFIX_RE = re.compile(r"\b(jr\.?|sr\.?|ii|iii|iv)\s*$", re.I)
_HYPHEN_RE = re.compile(r"-")
_APOS_RE   = re.compile(r"['\.]")


def _normalize(name: str) -> str:
    nfd = unicodedata.normalize("NFD", name)
    ascii_approx = "".join(c for c in nfd if unicodedata.category(c) != "Mn")
    s = ascii_approx.lower().strip()
    s = _SUFFIX_RE.sub("", s).strip()
    s = _HYPHEN_RE.sub(" ", s)
    s = _APOS_RE.sub("", s)
    return " ".join(s.split())


# ── Stat-field mappings (market → stat key) ──────────────────────────────────

_MLB_STAT_MAP: dict[str, tuple[str, str]] = {
    "pitcher_strikeouts":    ("pitching", "strikeOuts"),
    "pitcher_hits_allowed":  ("pitching", "hits"),
    "pitcher_outs_recorded": ("pitching", "outs"),
    "pitcher_walks":         ("pitching", "baseOnBalls"),
    "pitcher_saves":         ("pitching", "saves"),
    "batter_hits":           ("batting", "hits"),
    "batter_home_runs":      ("batting", "homeRuns"),
    "batter_total_bases":    ("batting", "totalBases"),
    "batter_rbis":           ("batting", "rbi"),
    "batter_runs_scored":    ("batting", "runs"),
    "batter_stolen_bases":   ("batting", "stolenBases"),
    "batter_strikeouts":     ("batting", "strikeOuts"),
    "hits":                  ("batting", "hits"),
    "home_run":              ("batting", "homeRuns"),
    "total_bases":           ("batting", "totalBases"),
    "stolen_bases":          ("batting", "stolenBases"),
    "runs":                  ("batting", "runs"),
    "rbi":                   ("batting", "rbi"),
    "rbis":                  ("batting", "rbi"),
    "saves":                 ("pitching", "saves"),
    "ks":                    ("pitching", "strikeOuts"),
    "hr":                    ("batting", "homeRuns"),
    "sb":                    ("batting", "stolenBases"),
    "tb":                    ("batting", "totalBases"),
    "bb":                    ("pitching", "baseOnBalls"),
    "sv":                    ("pitching", "saves"),
}

_NBA_STAT_MAP: dict[str, object] = {
    "player_points":                  "PTS",
    "player_rebounds":                "REB",
    "player_assists":                 "AST",
    "player_threes":                  "FG3M",
    "player_steals":                  "STL",
    "player_blocks":                  "BLK",
    "player_turnovers":               "TOV",
    "player_points_rebounds_assists": lambda r: r.get("PTS",0)+r.get("REB",0)+r.get("AST",0),
    "player_points_rebounds":         lambda r: r.get("PTS",0)+r.get("REB",0),
    "player_points_assists":          lambda r: r.get("PTS",0)+r.get("AST",0),
    "player_rebounds_assists":        lambda r: r.get("REB",0)+r.get("AST",0),
    "player_steals_blocks":           lambda r: r.get("STL",0)+r.get("BLK",0),
    "pts":  "PTS",
    "reb":  "REB",
    "ast":  "AST",
    "stl":  "STL",
    "blk":  "BLK",
    "tov":  "TOV",
}

_NHL_STAT_MAP: dict[str, object] = {
    "player_goals":         "goals",
    "player_assists":       "assists",
    "player_shots_on_goal": "shots",
    "player_saves":         "saves",
    "player_blocked_shots": "blockedShots",
    "player_hits":          "hits",
    "player_points":        lambda r: r.get("goals",0)+r.get("assists",0),
    "goals":   "goals",
    "assists": "assists",
    "shots":   "shots",
    "saves":   "saves",
}

# NBA stats API headers (same as result_grader)
_NBA_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer":    "https://www.nba.com",
    "Accept":     "application/json",
    "x-nba-stats-origin": "stats",
    "x-nba-stats-token":  "true",
}

_EMPTY = {"hits": None, "games": 0, "pct": None, "hot": False}
_TIMEOUT = 3


# ── MLB player lookup + game log ──────────────────────────────────────────────

def _mlb_player_id(name_norm: str) -> int | None:
    """Search MLB API for player ID by full name."""
    try:
        parts = name_norm.split()
        last  = parts[-1].title() if parts else ""
        r = requests.get(
            "https://statsapi.mlb.com/api/v1/people/search",
            params={"names": name_norm.title(), "sportIds": 1},
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        people = r.json().get("people", [])
        if people:
            return people[0]["id"]
        # Fallback: search by last name
        r2 = requests.get(
            "https://statsapi.mlb.com/api/v1/people/search",
            params={"names": last, "sportIds": 1},
            timeout=_TIMEOUT,
        )
        r2.raise_for_status()
        for p in r2.json().get("people", []):
            if _normalize(p.get("fullName","")) == name_norm:
                return p["id"]
        return None
    except Exception:
        return None


def _mlb_game_log(player_id: int, stat_group: str) -> list[dict]:
    """Return list of game-log stat dicts for 2025, newest first."""
    try:
        r = requests.get(
            f"https://statsapi.mlb.com/api/v1/people/{player_id}/stats",
            params={"stats": "gameLog", "season": "2025", "group": stat_group},
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        groups = r.json().get("stats", [])
        for g in groups:
            splits = g.get("splits", [])
            # Newest game first
            return [s.get("stat", {}) for s in reversed(splits)]
        return []
    except Exception:
        return []


def _mlb_streak(player: str, market: str, line: float, n_games: int) -> dict:
    stat_cfg = None
    mkt_lower = market.lower()
    for key in sorted(_MLB_STAT_MAP.keys(), key=len, reverse=True):
        if key in mkt_lower:
            stat_cfg = _MLB_STAT_MAP[key]
            break
    if stat_cfg is None:
        return _EMPTY

    stat_group, stat_field = stat_cfg
    name_norm = _normalize(player)
    pid = _mlb_player_id(name_norm)
    if pid is None:
        return _EMPTY

    logs = _mlb_game_log(pid, stat_group)
    if not logs:
        return _EMPTY

    recent = logs[:n_games]
    games  = len(recent)
    if games == 0:
        return _EMPTY

    # totalBases not in game-log directly — compute from components
    hits_field = stat_field == "totalBases"
    count = 0
    for g in recent:
        if hits_field:
            val = (g.get("hits",0) + g.get("doubles",0)
                   + g.get("triples",0)*2 + g.get("homeRuns",0)*3)
        else:
            val = g.get(stat_field, 0) or 0
        if float(val) > float(line):
            count += 1

    pct = round(count / games, 3)
    return {"hits": count, "games": games, "pct": pct, "hot": count >= 4 and games >= 5}


# ── NBA player lookup + game log ──────────────────────────────────────────────

def _nba_player_id(name_norm: str) -> int | None:
    """Find NBA player ID using the player list endpoint."""
    try:
        r = requests.get(
            "https://stats.nba.com/stats/commonallplayers",
            params={"LeagueID": "00", "Season": "2024-25", "IsOnlyCurrentSeason": 1},
            headers=_NBA_HEADERS,
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        rs = r.json().get("resultSets", [])
        for result in rs:
            if result["name"] != "CommonAllPlayers":
                continue
            h = result["headers"]
            id_idx   = h.index("PERSON_ID")
            name_idx = h.index("DISPLAY_FIRST_LAST")
            for row in result["rowSet"]:
                if _normalize(row[name_idx]) == name_norm:
                    return row[id_idx]
            # Fuzzy: last-name match
            for row in result["rowSet"]:
                parts_a = name_norm.split()
                parts_b = _normalize(row[name_idx]).split()
                if parts_a and parts_b and parts_a[-1] == parts_b[-1]:
                    return row[id_idx]
        return None
    except Exception:
        return None


def _nba_game_log(player_id: int) -> list[dict]:
    """Return list of game stat dicts for 2024-25, newest first."""
    try:
        r = requests.get(
            "https://stats.nba.com/stats/playergamelog",
            params={
                "PlayerID":   player_id,
                "Season":     "2024-25",
                "SeasonType": "Regular Season",
            },
            headers=_NBA_HEADERS,
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        rs = r.json().get("resultSets", [])
        for result in rs:
            if result["name"] != "PlayerGameLog":
                continue
            h = result["headers"]
            rows = []
            for row in result["rowSet"]:
                d = {col: row[i] for i, col in enumerate(h)}
                rows.append({
                    "PTS":  d.get("PTS") or 0,
                    "REB":  d.get("REB") or 0,
                    "AST":  d.get("AST") or 0,
                    "FG3M": d.get("FG3M") or 0,
                    "STL":  d.get("STL") or 0,
                    "BLK":  d.get("BLK") or 0,
                    "TOV":  d.get("TOV") or 0,
                })
            return rows  # already newest-first from API
        return []
    except Exception:
        return []


def _nba_streak(player: str, market: str, line: float, n_games: int) -> dict:
    stat_cfg = None
    mkt_lower = market.lower()
    for key in sorted(_NBA_STAT_MAP.keys(), key=len, reverse=True):
        if key in mkt_lower:
            stat_cfg = _NBA_STAT_MAP[key]
            break
    if stat_cfg is None:
        return _EMPTY

    name_norm = _normalize(player)
    pid = _nba_player_id(name_norm)
    if pid is None:
        return _EMPTY

    logs = _nba_game_log(pid)
    if not logs:
        return _EMPTY

    recent = logs[:n_games]
    games  = len(recent)
    if games == 0:
        return _EMPTY

    count = 0
    for g in recent:
        val = stat_cfg(g) if callable(stat_cfg) else (g.get(stat_cfg) or 0)
        if float(val) > float(line):
            count += 1

    pct = round(count / games, 3)
    return {"hits": count, "games": games, "pct": pct, "hot": count >= 4 and games >= 5}


# ── NHL player lookup + game log ──────────────────────────────────────────────

def _nhl_player_id(name_norm: str) -> int | None:
    """Find NHL player ID via web API search."""
    try:
        r = requests.get(
            f"https://api-web.nhle.com/v1/player/search?query={name_norm.replace(' ', '+')}",
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        players = r.json()
        if isinstance(players, list) and players:
            return players[0].get("playerId")
        # Try alternate key structure
        for item in (players if isinstance(players, list) else players.get("players", [])):
            fn = item.get("firstName", {}).get("default", "")
            ln = item.get("lastName", {}).get("default", "")
            full = _normalize(f"{fn} {ln}")
            if full == name_norm:
                return item.get("playerId")
        return None
    except Exception:
        return None


def _nhl_game_log(player_id: int) -> list[dict]:
    """Return list of NHL game stat dicts, newest first."""
    try:
        r = requests.get(
            f"https://api-web.nhle.com/v1/player/{player_id}/game-log/2024-20205/2/false",
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        games_data = r.json().get("gameLog", [])
        rows = []
        for g in reversed(games_data):  # reverse to get newest first
            rows.append({
                "goals":        g.get("goals", 0) or 0,
                "assists":      g.get("assists", 0) or 0,
                "shots":        g.get("shots", 0) or 0,
                "saves":        (g.get("saveShotsAgainst", 0) or 0) - (g.get("goalsAgainst", 0) or 0),
                "blockedShots": g.get("blockedShots", 0) or 0,
                "hits":         g.get("hits", 0) or 0,
            })
        return rows
    except Exception:
        return []


def _nhl_streak(player: str, market: str, line: float, n_games: int) -> dict:
    stat_cfg = None
    mkt_lower = market.lower()
    for key in sorted(_NHL_STAT_MAP.keys(), key=len, reverse=True):
        if key in mkt_lower:
            stat_cfg = _NHL_STAT_MAP[key]
            break
    if stat_cfg is None:
        return _EMPTY

    name_norm = _normalize(player)
    pid = _nhl_player_id(name_norm)
    if pid is None:
        return _EMPTY

    logs = _nhl_game_log(pid)
    if not logs:
        return _EMPTY

    recent = logs[:n_games]
    games  = len(recent)
    if games == 0:
        return _EMPTY

    count = 0
    for g in recent:
        val = stat_cfg(g) if callable(stat_cfg) else (g.get(stat_cfg) or 0)
        if float(val) > float(line):
            count += 1

    pct = round(count / games, 3)
    return {"hits": count, "games": games, "pct": pct, "hot": count >= 4 and games >= 5}


# ── ESPN fallback ─────────────────────────────────────────────────────────────

# ESPN sport/league slugs for the two endpoints used below
_ESPN_SPORT_LEAGUE = {
    "MLB":  ("baseball", "mlb"),
    "NBA":  ("basketball", "nba"),
    "WNBA": ("basketball", "wnba"),
    "NHL":  ("hockey", "nhl"),
}

# ESPN stat-field maps: market → stat key in ESPN game-log response
# We reuse the existing maps where field names match; ESPN uses slightly
# different names for some fields so we define a dedicated ESPN map.
_ESPN_STAT_MAP: dict[str, object] = {
    # MLB batting
    "batter_hits":           "hits",
    "batter_home_runs":      "homeRuns",
    "batter_total_bases":    "totalBases",
    "batter_rbis":           "RBIs",
    "batter_runs_scored":    "runs",
    "batter_stolen_bases":   "stolenBases",
    "batter_strikeouts":     "strikeouts",
    # MLB pitching
    "pitcher_strikeouts":    "strikeouts",
    "pitcher_hits_allowed":  "hitsAllowed",
    "pitcher_outs_recorded": "outsPitched",
    "pitcher_walks":         "walks",
    "pitcher_saves":         "saves",
    # NBA
    "player_points":                  "points",
    "player_rebounds":                "rebounds",
    "player_assists":                 "assists",
    "player_threes":                  "threePointFieldGoalsMade",
    "player_steals":                  "steals",
    "player_blocks":                  "blockedShots",
    "player_turnovers":               "turnovers",
    "player_points_rebounds_assists": lambda r: (r.get("points",0) or 0)
                                                + (r.get("rebounds",0) or 0)
                                                + (r.get("assists",0) or 0),
    "player_points_rebounds":         lambda r: (r.get("points",0) or 0)
                                                + (r.get("rebounds",0) or 0),
    "player_points_assists":          lambda r: (r.get("points",0) or 0)
                                                + (r.get("assists",0) or 0),
    "player_rebounds_assists":        lambda r: (r.get("rebounds",0) or 0)
                                                + (r.get("assists",0) or 0),
    "player_steals_blocks":           lambda r: (r.get("steals",0) or 0)
                                                + (r.get("blockedShots",0) or 0),
    # NHL
    "player_goals":          "goals",
    "player_assists":        "assists",
    "player_shots_on_goal":  "shots",
    "player_saves":          "saves",
    "player_blocked_shots":  "blockedShots",
    "player_points":         lambda r: (r.get("goals",0) or 0)
                                       + (r.get("assists",0) or 0),
}


def _espn_player_id(player: str, sport: str) -> str | None:
    """Search ESPN for a player ID by name."""
    slugs = _ESPN_SPORT_LEAGUE.get(sport.upper())
    if slugs is None:
        return None
    sport_slug, league_slug = slugs
    try:
        r = requests.get(
            f"https://site.api.espn.com/apis/site/v2/sports/{sport_slug}/{league_slug}/athletes",
            params={"search": player, "limit": 5},
            timeout=5,
        )
        if r.status_code != 200:
            return None
        athletes = r.json().get("athletes", [])
        if not athletes:
            return None
        name_norm = _normalize(player)
        # Try exact normalized match first
        for a in athletes:
            if _normalize(a.get("fullName", a.get("displayName", ""))) == name_norm:
                return str(a["id"])
        # Fall back to first result
        return str(athletes[0]["id"])
    except Exception:
        return None


def _espn_game_log(player_id: str, sport: str) -> list[dict]:
    """Fetch ESPN game-log stats for a player; returns list newest-first."""
    slugs = _ESPN_SPORT_LEAGUE.get(sport.upper())
    if slugs is None:
        return []
    sport_slug, league_slug = slugs
    try:
        r = requests.get(
            f"https://site.web.api.espn.com/apis/common/v3/sports/{sport_slug}/{league_slug}/athletes/{player_id}/stats",
            timeout=5,
        )
        if r.status_code != 200:
            return []
        data = r.json()
        # ESPN returns stats under "splits" > "categories" > "stats" per game
        # The game-log is under data["splitCategories"] or data["stats"]["splits"]
        # Try the splits path used by the athlete stats endpoint
        splits = data.get("splits", {})
        categories = splits.get("categories", [])
        rows = []
        for cat in categories:
            for event in cat.get("events", []):
                stat_names  = cat.get("labels", [])
                stat_values = event.get("stats", [])
                row = {stat_names[i]: stat_values[i]
                       for i in range(min(len(stat_names), len(stat_values)))}
                rows.append(row)
        # Reverse so newest is first (ESPN returns oldest-first in this endpoint)
        return list(reversed(rows))
    except Exception:
        return []


def _espn_streak(player: str, market: str, sport: str,
                 line: float, n_games: int = 5) -> dict:
    """
    ESPN fallback streak detector.
    Looks up player ID via ESPN search, fetches game-log stats, and counts
    how many of the last n_games the player exceeded `line` in `market`.
    Returns same dict shape as _mlb_streak / _nba_streak / _nhl_streak.
    """
    mkt_lower = market.lower()
    stat_cfg = None
    for key in sorted(_ESPN_STAT_MAP.keys(), key=len, reverse=True):
        if key in mkt_lower:
            stat_cfg = _ESPN_STAT_MAP[key]
            break
    if stat_cfg is None:
        return _EMPTY

    pid = _espn_player_id(player, sport)
    if pid is None:
        return _EMPTY

    logs = _espn_game_log(pid, sport)
    if not logs:
        return _EMPTY

    recent = logs[:n_games]
    games  = len(recent)
    if games == 0:
        return _EMPTY

    count = 0
    for g in recent:
        val = stat_cfg(g) if callable(stat_cfg) else (g.get(stat_cfg) or 0)
        try:
            if float(val) > float(line):
                count += 1
        except (TypeError, ValueError):
            pass

    pct = round(count / games, 3)
    return {"hits": count, "games": games, "pct": pct, "hot": count >= 4 and games >= 5}


# ── Public API ────────────────────────────────────────────────────────────────

def get_player_streak(player: str, market: str, sport: str,
                      line: float, n_games: int = 5) -> dict:
    """
    Fetch recent game logs and count how many of the last n_games the player
    exceeded `line` in the given `market`.

    Returns:
        {
            "hits":  int | None,   # games exceeded line
            "games": int,          # games found (may be < n_games near season start)
            "pct":   float | None, # hits / games
            "hot":   bool,         # True if hits >= 4 out of 5
        }
    Returns _EMPTY on any error or missing data.
    """
    try:
        sport_up = sport.upper()
        if sport_up == "MLB":
            result = _mlb_streak(player, market, line, n_games)
        elif sport_up in ("NBA", "WNBA"):
            result = _nba_streak(player, market, line, n_games)
        elif sport_up == "NHL":
            result = _nhl_streak(player, market, line, n_games)
        else:
            result = _EMPTY

        # ESPN fallback: use when primary API returned no data
        if result["hits"] is None:
            result = _espn_streak(player, market, sport, line, n_games)

        return result
    except Exception:
        try:
            return _espn_streak(player, market, sport, line, n_games)
        except Exception:
            return _EMPTY


def get_streaks_for_df(df: pd.DataFrame, sport: str) -> pd.DataFrame:
    """
    Adds two columns to a copy of `df`:
        "streak"  — display string: "🔥 4/5", "3/5", "" if unavailable
        "hot"     — bool: True when streak is hot (>=4/5)

    Results are cached in st.session_state["streak_cache"] keyed by
    (player, market, line) to avoid re-fetching on every Streamlit rerun.
    """
    import streamlit as st

    if "streak_cache" not in st.session_state:
        st.session_state["streak_cache"] = {}

    cache = st.session_state["streak_cache"]

    df = df.copy()
    streak_labels = []
    hot_flags     = []

    for _, row in df.iterrows():
        player = str(row.get("player", ""))
        market = str(row.get("market", ""))
        try:
            line = float(row.get("line", 0.5))
        except (TypeError, ValueError):
            line = 0.5

        cache_key = (player, market, line, sport.upper())

        if cache_key not in cache:
            result = get_player_streak(player, market, sport, line)
            cache[cache_key] = result
        else:
            result = cache[cache_key]

        hits  = result.get("hits")
        games = result.get("games", 0)
        hot   = result.get("hot", False)

        if hits is None or games == 0:
            streak_labels.append("")
            hot_flags.append(False)
        elif hot:
            streak_labels.append(f"🔥 {hits}/{games}")
            hot_flags.append(True)
        else:
            streak_labels.append(f"{hits}/{games}")
            hot_flags.append(False)

    df["streak"] = streak_labels
    df["hot"]    = hot_flags
    return df
