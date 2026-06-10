"""
Auto-grades pending bets using free public stat APIs.
Supported sports: MLB, NBA, WNBA, NHL.
"""

import requests
import json
import re
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path
import sys

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

sys.path.insert(0, str(Path(__file__).parent))
from bet_tracker import load_bets, update_result, save_bets

MLB_API = "https://statsapi.mlb.com/api/v1"
NHL_API = "https://api-web.nhle.com/v1"
NBA_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://www.nba.com",
    "Accept": "application/json",
    "x-nba-stats-origin": "stats",
    "x-nba-stats-token": "true",
}

# ── MLB market → (stat_group, stat_field) ─────────────────────────────────────
# Longer/more-specific keys MUST come before substrings of them.
MLB_PROP_STAT_MAP = {
    "pitcher_hits_allowed": ("pitching", "hits"),
    "hits allowed":         ("pitching", "hits"),
    "pitcher_strikeouts":   ("pitching", "strikeOuts"),
    "pitcher ks":           ("pitching", "strikeOuts"),
    "pitcher_outs_recorded":("pitching", "outs"),
    "outs recorded":        ("pitching", "outs"),
    "pitcher_saves":        ("pitching", "saves"),
    "pitcher_walks":        ("pitching", "baseOnBalls"),
    "pitcher walks":        ("pitching", "baseOnBalls"),
    "batter_hits":          ("batting", "hits"),
    "batter_home_runs":     ("batting", "homeRuns"),
    "batter_total_bases":   ("batting", "totalBases"),
    "batter_rbis":          ("batting", "rbi"),
    "batter_runs_scored":   ("batting", "runs"),
    "batter_stolen_bases":  ("batting", "stolenBases"),
    "batter_strikeouts":    ("batting", "strikeOuts"),
    "batter hits runs rbis":("batting", "hits"),
    "1+ hits":              ("batting", "hits"),
    "home run":             ("batting", "homeRuns"),
    "total bases":          ("batting", "totalBases"),
    "stolen bases":         ("batting", "stolenBases"),
    "runs scored":          ("batting", "runs"),
    "hitter strikeouts":    ("batting", "strikeOuts"),
    "hits+runs+rbis":       None,  # computed below as hits+runs+rbi
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

# ── NBA/WNBA market → stat field or callable ──────────────────────────────────
# stat dict keys (from NBA stats API): pts, reb, ast, fg3m, stl, blk, tov
NBA_PROP_STAT_MAP = {
    "player_points":                    "pts",
    "player_rebounds":                  "reb",
    "player_assists":                   "ast",
    "player_threes":                    "fg3m",
    "player_steals":                    "stl",
    "player_blocks":                    "blk",
    "player_turnovers":                 "tov",
    "player_points_rebounds_assists":   lambda s: s.get("pts", 0) + s.get("reb", 0) + s.get("ast", 0),
    "player_points_rebounds":           lambda s: s.get("pts", 0) + s.get("reb", 0),
    "player_points_assists":            lambda s: s.get("pts", 0) + s.get("ast", 0),
    "player_rebounds_assists":          lambda s: s.get("reb", 0) + s.get("ast", 0),
    "player_steals_blocks":             lambda s: s.get("stl", 0) + s.get("blk", 0),
    "player_double_double":             lambda s: int(s.get("pts", 0) >= 10 and s.get("reb", 0) >= 10
                                                      or s.get("pts", 0) >= 10 and s.get("ast", 0) >= 10
                                                      or s.get("reb", 0) >= 10 and s.get("ast", 0) >= 10),
    "pra":         lambda s: s.get("pts", 0) + s.get("reb", 0) + s.get("ast", 0),
    "pts":         "pts",
    "reb":         "reb",
    "ast":         "ast",
    "stl":         "stl",
    "blk":         "blk",
    "tov":         "tov",
    "3-pointers":  "fg3m",
    "threes":      "fg3m",
    "3pm":         "fg3m",
    "three pointers": "fg3m",
    "points":      "pts",
    "rebounds":    "reb",
    "assists":     "ast",
    "steals":      "stl",
    "blocks":      "blk",
    "turnovers":   "tov",
}

# ── NHL market → stat field or callable ──────────────────────────────────────
# stat dict keys: goals, assists, shots, saves, pim, blockedShots, hits
NHL_PROP_STAT_MAP = {
    "player_goals":         "goals",
    "player_assists":       "assists",
    "player_shots_on_goal": "shots",
    "player_saves":         "saves",
    "player_blocked_shots": "blockedShots",
    "player_hits":          "hits",
    "player_points":        lambda s: s.get("goals", 0) + s.get("assists", 0),
    "goals":    "goals",
    "assists":  "assists",
    "shots":    "shots",
    "saves":    "saves",
}

# Combined map for prop parsing — all sports
PROP_STAT_MAP = {**MLB_PROP_STAT_MAP}  # legacy alias for MLB-only callers


# ── Name normalisation ────────────────────────────────────────────────────────

_SUFFIX_RE  = re.compile(r"\b(jr\.?|sr\.?|ii|iii|iv)\s*$", re.I)
_HYPHEN_RE  = re.compile(r"-")
_APOS_RE    = re.compile(r"['\.]")


def _normalize(name: str) -> str:
    nfd = unicodedata.normalize("NFD", name)
    ascii_approx = "".join(c for c in nfd if unicodedata.category(c) != "Mn")
    s = ascii_approx.lower().strip()
    s = _SUFFIX_RE.sub("", s).strip()
    s = _HYPHEN_RE.sub(" ", s)
    s = _APOS_RE.sub("", s)
    return " ".join(s.split())


def _fuzzy_match_player(name_norm: str, all_stats: dict, threshold: float = 0.82) -> dict | None:
    try:
        from rapidfuzz import fuzz as _fuzz
        def _score(a: str, b: str) -> float:
            ts = _fuzz.token_sort_ratio(a, b) / 100.0
            pr = _fuzz.partial_ratio(a, b) / 100.0
            last_a = a.split()[-1] if a.split() else ""
            last_b = b.split()[-1] if b.split() else ""
            ln = 1.0 if last_a == last_b else (_fuzz.ratio(last_a, last_b) / 100.0)
            return 0.5 * ts + 0.3 * pr + 0.2 * ln
    except ImportError:
        from difflib import SequenceMatcher
        def _score(a: str, b: str) -> float:
            ts = SequenceMatcher(None, a, b).ratio()
            last_a = a.split()[-1] if a.split() else ""
            last_b = b.split()[-1] if b.split() else ""
            ln = SequenceMatcher(None, last_a, last_b).ratio()
            return 0.6 * ts + 0.4 * ln

    best_key, best_score = None, 0.0
    for key in all_stats:
        s = _score(name_norm, key)
        if s > best_score:
            best_score = s
            best_key = key

    if best_key and best_score >= threshold:
        return all_stats[best_key]
    return None


def _parse_prop(prop_str: str, sport: str = "MLB") -> tuple[str | None, float | None]:
    """
    Parse 'batter_hits O0.5 [SGP]' → (market_key, line).
    Tries sport-specific map first, then falls back to all maps.
    Keys are checked longest-first so 'player_points_rebounds_assists'
    matches before its substring 'player_points'.
    """
    prop_lower = prop_str.lower()
    line_match = re.search(r'o([\d.]+)', prop_lower)
    line = float(line_match.group(1)) if line_match else None

    sport_maps = {
        "MLB":  MLB_PROP_STAT_MAP,
        "NBA":  NBA_PROP_STAT_MAP,
        "WNBA": NBA_PROP_STAT_MAP,
        "NHL":  NHL_PROP_STAT_MAP,
    }
    ordered_maps = [sport_maps.get(sport.upper(), {})]
    for s, m in sport_maps.items():
        if s != sport.upper():
            ordered_maps.append(m)

    for stat_map in ordered_maps:
        for key in sorted(stat_map.keys(), key=len, reverse=True):
            if key in prop_lower:
                return key, line

    return None, line


def _grade_bet(actual_val: float, line: float) -> str:
    if actual_val > line:
        return "win"
    elif actual_val < line:
        return "loss"
    return "push"


# ── MLB stats ─────────────────────────────────────────────────────────────────

def _get_mlb_games(date_str: str) -> list[dict]:
    r = requests.get(f"{MLB_API}/schedule",
                     params={"sportId": 1, "date": date_str}, timeout=15)
    r.raise_for_status()
    dates = r.json().get("dates", [])
    if not dates:
        return []
    return [g for g in dates[0].get("games", [])
            if g.get("status", {}).get("abstractGameState") == "Final"]


def _get_mlb_player_stats(game_pk: int) -> dict:
    r = requests.get(f"{MLB_API}/game/{game_pk}/boxscore", timeout=15)
    r.raise_for_status()
    bs = r.json()
    stats = {}
    for side in ("home", "away"):
        for pid, p in bs.get("teams", {}).get(side, {}).get("players", {}).items():
            name = p.get("person", {}).get("fullName", "")
            if not name:
                continue
            batting  = p.get("stats", {}).get("batting", {})
            pitching = p.get("stats", {}).get("pitching", {})
            if batting and "totalBases" not in batting:
                batting["totalBases"] = (
                    batting.get("hits", 0) + batting.get("doubles", 0)
                    + batting.get("triples", 0) * 2 + batting.get("homeRuns", 0) * 3
                )
            stats[_normalize(name)] = {"batting": batting, "pitching": pitching}
    return stats


def _grade_mlb(bets: list[dict], date_str: str, dry_run: bool) -> tuple[int, list[str]]:
    games = _get_mlb_games(date_str)
    if not games:
        return 0, [f"No final MLB games found for {date_str}"]

    all_stats: dict = {}
    for g in games:
        try:
            all_stats.update(_get_mlb_player_stats(g["gamePk"]))
        except Exception as e:
            print(f"  ⚠️  MLB game {g['gamePk']}: {e}")
    print(f"  MLB: loaded {len(all_stats)} players from {len(games)} games")

    graded, skipped = 0, []
    for bet in bets:
        player_norm = _normalize(bet["player"])
        market_key, line = _parse_prop(bet.get("prop", ""), "MLB")
        if bet.get("line") is not None and line is None:
            line = float(bet["line"])
        if not market_key or line is None:
            skipped.append(f"{bet['player']} — unparseable: {bet.get('prop')}")
            continue

        stat_cfg = MLB_PROP_STAT_MAP.get(market_key)
        # hits+runs+rbis uses None sentinel — handle before the unknown-market guard
        if market_key == "hits+runs+rbis":
            stat_cfg = "combo_hits_runs_rbis"  # sentinel to skip unknown-market exit
        elif stat_cfg is None:
            skipped.append(f"{bet['player']} — unknown market: {market_key}")
            continue

        pstats = all_stats.get(player_norm) or _fuzzy_match_player(player_norm, all_stats)
        if not pstats:
            # ESPN fallback
            try:
                from espn_service import grade_from_espn
                result = grade_from_espn(bet["player"], market_key, line, "MLB", date_str)
                if result:
                    if not dry_run:
                        update_result(bet["id"], result)
                    emoji = {"win": "✅", "loss": "❌", "push": "↩️"}.get(result, "?")
                    print(f"  {emoji} [MLB/ESPN] {bet['player']} | O{line} → {result.upper()}")
                    graded += 1
                    continue
            except Exception:
                pass
            skipped.append(f"{bet['player']} — not found in boxscores or ESPN")
            continue

        # hits+runs+rbis is a computed combination, not a single field
        if market_key == "hits+runs+rbis":
            b = pstats.get("batting") if pstats else None
            val = (b.get("hits", 0) + b.get("runs", 0) + b.get("rbi", 0)) if b is not None else None
        else:
            stat_group, stat_field = stat_cfg
            player_stats_group = pstats.get(stat_group, {})
            val = player_stats_group.get(stat_field)
        if val is None:
            # Player found but no stats for this market = DNP/no AB → void
            if not dry_run:
                update_result(bet["id"], "void")
            print(f"  ↩️  [MLB] {bet['player']} — DNP/no stats → VOID")
            graded += 1
            continue

        result = _grade_bet(float(val), float(line))
        if not dry_run:
            update_result(bet["id"], result)
        emoji = {"win": "✅", "loss": "❌", "push": "↩️"}.get(result, "?")
        print(f"  {emoji} [MLB] {bet['player']} | actual={val} vs O{line} → {result.upper()}")
        graded += 1

    return graded, skipped


# ── NBA / WNBA stats ──────────────────────────────────────────────────────────

def _get_espn_basketball_stats(date_str: str, league: str) -> dict:
    """
    Fetch NBA or WNBA box scores from ESPN public API.
    league: 'nba' or 'wnba'
    Returns dict: normalized_name → stat dict (pts, reb, ast, fg3m, stl, blk, tov)
    """
    all_stats: dict = {}
    date_compact = date_str.replace("-", "")
    try:
        sb = requests.get(
            f"https://site.api.espn.com/apis/site/v2/sports/basketball/{league}/scoreboard",
            params={"dates": date_compact},
            timeout=20,
        )
        sb.raise_for_status()
        sb_data = sb.json()
        events = sb_data.get("events", [])
        print(f"  ⚡ ESPN {league} scoreboard for {date_str}: {len(events)} events found")
        # If scoreboard is empty, try the core API (playoff games sometimes missing from site API)
        if not events:
            core_r = requests.get(
                f"https://sports.core.api.espn.com/v2/sports/basketball/leagues/{league}/events",
                params={"dates": date_compact, "limit": 10},
                timeout=20,
            )
            if core_r.ok:
                items = core_r.json().get("items", [])
                print(f"  ⚡ ESPN core API: {len(items)} event refs found")
                for item in items:
                    ref = item.get("$ref", "")
                    if ref:
                        try:
                            ev_r = requests.get(ref, timeout=15)
                            if ev_r.ok:
                                events.append(ev_r.json())
                        except Exception:
                            pass
        for event in events:
            status_type = event.get("status", {}).get("type", {})
            state = status_type.get("state", "")
            # Skip only explicitly pre-game events; accept post, in, completed, or unknown
            if state == "pre":
                continue
            event_id = event["id"]
            print(f"  ⚡ ESPN {league} event {event_id} state={state!r} completed={status_type.get('completed')}")
            try:
                box_r = requests.get(
                    f"https://site.api.espn.com/apis/site/v2/sports/basketball/{league}/summary",
                    params={"event": event_id},
                    timeout=20,
                )
                box_r.raise_for_status()
                data = box_r.json()
                for team in data.get("boxscore", {}).get("players", []):
                    for stat_entry in team.get("statistics", []):
                        keys = stat_entry.get("keys", [])
                        for athlete in stat_entry.get("athletes", []):
                            name = athlete.get("athlete", {}).get("displayName", "")
                            vals = athlete.get("stats", [])
                            if not name or not vals:
                                continue
                            stat_map = dict(zip(keys, vals))
                            try:
                                all_stats[_normalize(name)] = {
                                    "pts":  float(stat_map.get("PTS", 0) or 0),
                                    "reb":  float(stat_map.get("REB", 0) or 0),
                                    "ast":  float(stat_map.get("AST", 0) or 0),
                                    "fg3m": float(stat_map.get("3PM", 0) or 0),
                                    "stl":  float(stat_map.get("STL", 0) or 0),
                                    "blk":  float(stat_map.get("BLK", 0) or 0),
                                    "tov":  float(stat_map.get("TO", 0) or 0),
                                }
                            except Exception:
                                pass
            except Exception as e:
                print(f"  ⚠️  ESPN {league} box {event_id}: {e}")
    except Exception as e:
        raise RuntimeError(f"ESPN {league} fetch failed: {e}")
    return all_stats


def _get_nba_player_stats(date_str: str, league: str = "00") -> dict:
    """
    Fetch NBA/WNBA player stats via ESPN public API.
    league: '00' = NBA, '10' = WNBA
    """
    espn_league = "wnba" if league == "10" else "nba"
    return _get_espn_basketball_stats(date_str, espn_league)


def _grade_nba(bets: list[dict], date_str: str, league_id: str, label: str, dry_run: bool) -> tuple[int, list[str]]:
    try:
        all_stats = _get_nba_player_stats(date_str, league_id)
    except Exception as e:
        return 0, [f"{label} stats fetch failed: {e}"]
    print(f"  {label}: loaded {len(all_stats)} players")

    graded, skipped = 0, []
    for bet in bets:
        player_norm = _normalize(bet["player"])
        market_key, line = _parse_prop(bet.get("prop", ""), label)
        if bet.get("line") is not None and line is None:
            line = float(bet["line"])
        if not market_key or line is None:
            skipped.append(f"{bet['player']} — unparseable: {bet.get('prop')}")
            continue

        stat_cfg = NBA_PROP_STAT_MAP.get(market_key)
        if stat_cfg is None:
            skipped.append(f"{bet['player']} — unknown market: {market_key}")
            continue

        pstats = all_stats.get(player_norm) or _fuzzy_match_player(player_norm, all_stats)
        if not pstats:
            # ESPN fallback
            try:
                from espn_service import grade_from_espn
                result = grade_from_espn(bet["player"], market_key, line, label, date_str)
                if result:
                    if not dry_run:
                        update_result(bet["id"], result)
                    emoji = {"win": "✅", "loss": "❌", "push": "↩️"}.get(result, "?")
                    print(f"  {emoji} [{label}/ESPN] {bet['player']} | O{line} → {result.upper()}")
                    graded += 1
                    continue
            except Exception:
                pass
            skipped.append(f"{bet['player']} — not found in box scores or ESPN")
            continue

        if callable(stat_cfg):
            val = stat_cfg(pstats)
        else:
            val = pstats.get(stat_cfg)

        if val is None:
            # Player found but DNP → void
            if not dry_run:
                update_result(bet["id"], "void")
            print(f"  ↩️  [NBA/WNBA] {bet['player']} — DNP/no stats → VOID")
            graded += 1
            continue

        result = _grade_bet(float(val), float(line))
        if not dry_run:
            update_result(bet["id"], result)
        emoji = {"win": "✅", "loss": "❌", "push": "↩️"}.get(result, "?")
        print(f"  {emoji} [{label}] {bet['player']} | actual={val} vs O{line} → {result.upper()}")
        graded += 1

    return graded, skipped


# ── NHL stats ─────────────────────────────────────────────────────────────────

def _get_nhl_player_stats(date_str: str) -> dict:
    """
    Fetch NHL player stats for all games on date_str.
    Returns dict: normalized_name → stat dict
    """
    schedule = requests.get(f"{NHL_API}/schedule/{date_str}", timeout=15)
    schedule.raise_for_status()
    game_weeks = schedule.json().get("gameWeek", [])

    game_ids = []
    for day in game_weeks:
        if day.get("date") == date_str:
            for g in day.get("games", []):
                if g.get("gameState") in ("OFF", "FINAL"):
                    game_ids.append(g["id"])

    all_stats: dict = {}
    for gid in game_ids:
        try:
            box = requests.get(f"{NHL_API}/gamecenter/{gid}/boxscore", timeout=15)
            box.raise_for_status()
            data = box.json()
            for side in ("homeTeam", "awayTeam"):
                team = data.get(side, {})
                for category in ("forwards", "defensemen", "goalies"):
                    for p in team.get(category, []):
                        name = f"{p.get('firstName', {}).get('default', '')} {p.get('lastName', {}).get('default', '')}".strip()
                        if not name:
                            continue
                        stat: dict = {}
                        if category == "goalies":
                            stat["saves"] = p.get("saveShotsAgainst", 0) - p.get("goalsAgainst", 0)
                            stat["goals"]  = p.get("goals", 0)
                            stat["assists"] = p.get("assists", 0)
                        else:
                            stat["goals"]        = p.get("goals", 0)
                            stat["assists"]      = p.get("assists", 0)
                            stat["shots"]        = p.get("sog", 0)
                            stat["blockedShots"] = p.get("blockedShots", 0)
                            stat["hits"]         = p.get("hits", 0)
                        all_stats[_normalize(name)] = stat
        except Exception as e:
            print(f"  ⚠️  NHL game {gid}: {e}")

    return all_stats


def _grade_nhl(bets: list[dict], date_str: str, dry_run: bool) -> tuple[int, list[str]]:
    try:
        all_stats = _get_nhl_player_stats(date_str)
    except Exception as e:
        return 0, [f"NHL stats fetch failed: {e}"]
    print(f"  NHL: loaded {len(all_stats)} players")

    graded, skipped = 0, []
    for bet in bets:
        player_norm = _normalize(bet["player"])
        market_key, line = _parse_prop(bet.get("prop", ""), "NHL")
        if bet.get("line") is not None and line is None:
            line = float(bet["line"])
        if not market_key or line is None:
            skipped.append(f"{bet['player']} — unparseable: {bet.get('prop')}")
            continue

        stat_cfg = NHL_PROP_STAT_MAP.get(market_key)
        if stat_cfg is None:
            skipped.append(f"{bet['player']} — unknown market: {market_key}")
            continue

        pstats = all_stats.get(player_norm) or _fuzzy_match_player(player_norm, all_stats)
        if not pstats:
            # ESPN fallback
            try:
                from espn_service import grade_from_espn
                result = grade_from_espn(bet["player"], market_key, line, "NHL", date_str)
                if result:
                    if not dry_run:
                        update_result(bet["id"], result)
                    emoji = {"win": "✅", "loss": "❌", "push": "↩️"}.get(result, "?")
                    print(f"  {emoji} [NHL/ESPN] {bet['player']} | O{line} → {result.upper()}")
                    graded += 1
                    continue
            except Exception:
                pass
            skipped.append(f"{bet['player']} — not found in box scores or ESPN")
            continue

        if callable(stat_cfg):
            val = stat_cfg(pstats)
        else:
            val = pstats.get(stat_cfg)

        if val is None:
            skipped.append(f"{bet['player']} — stat {stat_cfg} not found")
            continue

        result = _grade_bet(float(val), float(line))
        if not dry_run:
            update_result(bet["id"], result)
        emoji = {"win": "✅", "loss": "❌", "push": "↩️"}.get(result, "?")
        print(f"  {emoji} [NHL] {bet['player']} | actual={val} vs O{line} → {result.upper()}")
        graded += 1

    return graded, skipped


# ── Main entry point ──────────────────────────────────────────────────────────

def grade_pending_bets(target_date: str = None, dry_run: bool = False) -> dict:
    """
    Grade all pending bets for target_date (default: yesterday).
    Dispatches to MLB / NBA / WNBA / NHL graders by bet sport.
    Returns summary dict.
    """
    if target_date is None:
        target_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    print(f"🔍 Grading bets for {target_date} (dry_run={dry_run})...")

    bets = load_bets()
    pending = [b for b in bets if b["result"] == "pending" and b.get("date") == target_date]
    print(f"📋 Found {len(pending)} pending bets for {target_date}")

    if not pending:
        return {"graded": 0, "skipped": 0, "date": target_date}

    # Partition by sport
    by_sport: dict[str, list] = {}
    for b in pending:
        s = b.get("sport", "MLB").upper()
        by_sport.setdefault(s, []).append(b)

    total_graded, total_skipped = 0, []

    for sport, sport_bets in by_sport.items():
        print(f"\n── {sport} ({len(sport_bets)} bets) ──")
        try:
            if sport == "MLB":
                g, s = _grade_mlb(sport_bets, target_date, dry_run)
            elif sport == "NBA":
                g, s = _grade_nba(sport_bets, target_date, "00", "NBA", dry_run)
            elif sport == "WNBA":
                g, s = _grade_nba(sport_bets, target_date, "10", "WNBA", dry_run)
            elif sport == "NHL":
                g, s = _grade_nhl(sport_bets, target_date, dry_run)
            else:
                g, s = 0, [f"Unsupported sport: {sport}"]
        except Exception as e:
            g, s = 0, [f"{sport} grader crashed: {e}"]

        total_graded += g
        total_skipped.extend(s)

    print(f"\n📈 Done: {total_graded} graded, {len(total_skipped)} skipped")
    if total_skipped:
        print("Skipped:")
        for s in total_skipped:
            print(f"  - {s}")

    return {
        "date": target_date,
        "graded": total_graded,
        "skipped": len(total_skipped),
        "skipped_details": total_skipped,
    }


def manual_grade(bet_id: str, result: str) -> None:
    """
    Manually grade a single bet by ID.
    result: 'win' | 'loss' | 'push' | 'void'
    """
    valid = {"win", "loss", "push", "void"}
    if result not in valid:
        print(f"❌ Invalid result '{result}'. Use: {', '.join(valid)}")
        return
    bets = load_bets()
    match = next((b for b in bets if b["id"] == bet_id), None)
    if not match:
        print(f"❌ Bet ID '{bet_id}' not found")
        return
    update_result(bet_id, result)
    emoji = {"win": "✅", "loss": "❌", "push": "↩️", "void": "🚫"}.get(result, "?")
    print(f"  {emoji} Manual: {match['player']} | {match.get('prop','')} → {result.upper()}")


def list_pending(date_str: str) -> None:
    """Print pending bets for a date with their IDs for manual grading."""
    bets = load_bets()
    pending = [b for b in bets if b["result"] == "pending" and b.get("date") == date_str]
    if not pending:
        print(f"No pending bets for {date_str}")
        return
    print(f"Pending bets for {date_str}:")
    for b in pending:
        print(f"  id={b['id']}  {b.get('sport','?')} | {b['player']} | {b.get('prop','')} | line={b.get('line')}")


if __name__ == "__main__":
    args = sys.argv[1:]
    dry = "--dry-run" in args

    # Manual grade: py result_grader.py --manual <bet_id> <win|loss|push|void>
    if "--manual" in args:
        idx = args.index("--manual")
        if idx + 2 < len(args):
            manual_grade(args[idx + 1], args[idx + 2])
        else:
            print("Usage: py result_grader.py --manual <bet_id> <win|loss|push|void>")
        sys.exit(0)

    # List pending: py result_grader.py --list 2026-06-04
    if "--list" in args:
        idx = args.index("--list")
        date_arg = args[idx + 1] if idx + 1 < len(args) else None
        if not date_arg:
            date_arg = next((a for a in args if a.startswith("20")), None)
        list_pending(date_arg or (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d"))
        sys.exit(0)

    date_arg = next((a for a in args if a.startswith("20")), None)
    result = grade_pending_bets(target_date=date_arg, dry_run=dry)
    print(json.dumps(result, indent=2))
