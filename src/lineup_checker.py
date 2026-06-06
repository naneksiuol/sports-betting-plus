"""
Lineup confirmation and injury status.
Sources:
  - MLB Stats API: probable pitchers
  - ESPN API: injury reports (all sports)
  - Caches for 30 min to avoid hammering APIs
"""

import requests
import json
from datetime import datetime, date
from pathlib import Path

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
CACHE_FILE = Path(__file__).parent.parent / "data" / "lineup_cache.json"
CACHE_TTL_MIN = 30

SPORT_ESPN = {
    "MLB": ("baseball", "mlb"),
    "NBA": ("basketball", "nba"),
    "WNBA": ("basketball", "wnba"),
    "NHL": ("icehockey", "nhl"),
}


# ── Cache helpers ─────────────────────────────────────────────────────────────

def _load_cache() -> dict:
    if not CACHE_FILE.exists():
        return {}
    try:
        data = json.loads(CACHE_FILE.read_text())
        ts = data.get("_ts", "")
        if ts:
            age_min = (datetime.now() - datetime.fromisoformat(ts)).total_seconds() / 60
            if age_min > CACHE_TTL_MIN:
                return {}
        return data
    except Exception:
        return {}


def _save_cache(data: dict):
    data["_ts"] = datetime.now().isoformat()
    CACHE_FILE.write_text(json.dumps(data, indent=2))


# ── MLB: Probable pitchers ────────────────────────────────────────────────────

def get_mlb_pitchers() -> dict:
    """Returns {team_abbr: pitcher_name} for today's games."""
    cache = _load_cache()
    if "mlb_pitchers" in cache:
        return cache["mlb_pitchers"]

    today = date.today().strftime("%Y-%m-%d")
    result = {}

    try:
        r = requests.get(
            "https://statsapi.mlb.com/api/v1/schedule",
            params={"sportId": 1, "date": today, "hydrate": "probablePitcher,team"},
            timeout=12,
        )
        r.raise_for_status()
        dates = r.json().get("dates", [])
        for d in dates:
            for game in d.get("games", []):
                for side in ("home", "away"):
                    team = game.get("teams", {}).get(side, {})
                    team_abbr = team.get("team", {}).get("abbreviation", "")
                    pitcher = team.get("probablePitcher", {}).get("fullName", "TBD")
                    if team_abbr:
                        result[team_abbr.upper()] = pitcher
    except Exception as e:
        print(f"MLB pitcher fetch error: {e}")

    cache["mlb_pitchers"] = result
    _save_cache(cache)
    return result


# ── ESPN: Injury reports ──────────────────────────────────────────────────────

def _get_espn_injuries(sport: str) -> dict:
    """Returns {player_name_lower: {status, type, team}} for a sport."""
    cache = _load_cache()
    cache_key = f"injuries_{sport}"
    if cache_key in cache:
        return cache[cache_key]

    espn_sport, espn_league = SPORT_ESPN.get(sport, (None, None))
    if not espn_sport:
        return {}

    today = date.today().strftime("%Y%m%d")
    result = {}

    try:
        r = requests.get(
            f"https://site.api.espn.com/apis/site/v2/sports/{espn_sport}/{espn_league}/scoreboard",
            params={"dates": today},
            headers=HEADERS, timeout=12,
        )
        events = r.json().get("events", [])
    except Exception:
        return {}

    for event in events[:10]:
        try:
            r2 = requests.get(
                f"https://site.api.espn.com/apis/site/v2/sports/{espn_sport}/{espn_league}/summary",
                params={"event": event["id"]},
                headers=HEADERS, timeout=12,
            )
            data = r2.json()
            injuries = data.get("injuries", [])
            for team_inj in injuries:
                team_name = team_inj.get("team", {}).get("abbreviation", "")
                for p in team_inj.get("injuries", []):
                    name = p.get("athlete", {}).get("displayName", "")
                    status = p.get("status", "")
                    inj_type = p.get("details", {}).get("type", "")
                    if name:
                        result[name.lower()] = {
                            "status": status,
                            "type": inj_type,
                            "team": team_name,
                        }
        except Exception:
            continue

    cache[cache_key] = result
    _save_cache(cache)
    return result


# ── Public API ────────────────────────────────────────────────────────────────

def get_player_status(player_name: str, sport: str) -> dict:
    """
    Returns player status dict:
    {
      'status': 'active' | 'questionable' | 'out' | 'il' | 'unknown',
      'label': '✅ Active' | '⚠️ Questionable' | '❌ Out/IL',
      'detail': str,
    }
    """
    injuries = _get_espn_injuries(sport)
    name_lower = player_name.lower()

    # Exact match
    info = injuries.get(name_lower)

    # Fuzzy: last name match
    if not info:
        last = name_lower.split()[-1] if name_lower.split() else ""
        matches = [k for k in injuries if last in k]
        if len(matches) == 1:
            info = injuries[matches[0]]

    if not info:
        return {"status": "active", "label": "", "detail": ""}

    raw_status = info.get("status", "").lower()
    inj_type = info.get("type", "")

    if any(x in raw_status for x in ["out", "il", "injured reserve", "dnp"]):
        return {"status": "out", "label": "OUT", "detail": inj_type}
    elif any(x in raw_status for x in ["questionable", "day-to-day", "dtd", "probable"]):
        return {"status": "questionable", "label": "Q", "detail": inj_type or raw_status}
    else:
        return {"status": "active", "label": "", "detail": ""}


def enrich_df_with_status(df, sport: str):
    """Add 'status' and 'status_label' columns to the DataFrame."""
    import pandas as pd
    if df.empty:
        df["status"] = ""
        df["status_label"] = ""
        return df

    statuses = df["player"].apply(lambda p: get_player_status(p, sport))
    df = df.copy()
    df["status"] = statuses.apply(lambda s: s["status"])
    df["status_label"] = statuses.apply(
        lambda s: s["label"] + (f" ({s['detail']})" if s["detail"] else "")
    )
    return df


def get_mlb_pitcher_alert(matchup: str, sport: str) -> str:
    """Return probable pitcher string for a matchup like 'SD @ PHI'."""
    if sport != "MLB":
        return ""
    pitchers = get_mlb_pitchers()
    parts = matchup.replace(" @ ", "|").split("|")
    if len(parts) == 2:
        away_team = parts[0].strip().upper()
        home_team = parts[1].strip().upper()
        away_p = pitchers.get(away_team, "TBD")
        home_p = pitchers.get(home_team, "TBD")
        return f"{away_p} vs {home_p}"
    return ""
