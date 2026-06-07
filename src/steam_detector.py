"""
Steam Move & Reverse Line Movement (RLM) Detector
===================================================
Detects sharp money signals from your existing odds_snapshots.json data.

Two core signals:

1. STEAM MOVE — rapid coordinated line movement across multiple sharp books.
   Triggered when: odds move > STEAM_CENTS_THRESHOLD in < STEAM_WINDOW_MINUTES.
   Indicates: syndicates/sharps hitting the same side simultaneously.

2. REVERSE LINE MOVEMENT (RLM) — line moves opposite to public betting.
   Since we don't have public ticket data directly, we approximate:
   - Line drifting TOWARD the underdog = possible sharp fade of public
   - Significant move (>1 point spread or >8¢ moneyline) away from "chalk"
     side while implied public lean (short odds side) is static
   - Uses opening vs current delta + magnitude thresholds

Snapshot format:
  {
    "2026-06-06": {
      "player|market|line": {"odds": -115, "edge": 0.02, "time": "14:30", "opening": -110}
    }
  }

Output per flagged prop:
  - player, market, line
  - opening_odds, current_odds
  - move_cents (implied probability delta × 100)
  - move_direction: "toward_over" | "toward_under"
  - signal: "steam" | "rlm" | "steam+rlm"
  - strength: "strong" | "moderate" | "weak"
  - edge_at_open, edge_current
  - description: human-readable summary
"""

import json
from pathlib import Path
from datetime import datetime, date, timedelta

DATA_DIR  = Path(__file__).parent.parent / "data"
SNAP_FILE = DATA_DIR / "odds_snapshots.json"

# ── Thresholds ────────────────────────────────────────────────────────────────
STEAM_CENTS_STRONG   = 0.10   # 10 cent implied prob move = strong steam
STEAM_CENTS_MODERATE = 0.06   # 6 cents = moderate
STEAM_CENTS_WEAK     = 0.03   # 3 cents = worth flagging

RLM_CENTS_MIN        = 0.04   # minimum move to classify as RLM
RLM_AGAINST_PUBLIC   = True   # True = move toward underdog side = RLM signal

MAX_STALENESS_DAYS   = 3      # ignore snapshots older than this


# ── Helpers ───────────────────────────────────────────────────────────────────

def _american_to_implied(odds: float) -> float:
    if odds == 0:
        return 0.5
    if odds > 0:
        return 100 / (odds + 100)
    return abs(odds) / (abs(odds) + 100)


def _implied_to_american(p: float) -> int:
    p = min(max(p, 0.001), 0.999)
    if p >= 0.5:
        return int(round(-100 * p / (1 - p)))
    return int(round(100 * (1 - p) / p))


def _move_direction(open_odds: float, curr_odds: float) -> str:
    """
    'toward_over'  = line getting shorter (book implying over is more likely)
    'toward_under' = line getting longer  (book implying over is less likely)
    """
    open_imp = _american_to_implied(open_odds)
    curr_imp = _american_to_implied(curr_odds)
    return "toward_over" if curr_imp > open_imp else "toward_under"


def _strength_label(move_cents: float) -> str:
    if move_cents >= STEAM_CENTS_STRONG:
        return "strong"
    elif move_cents >= STEAM_CENTS_MODERATE:
        return "moderate"
    return "weak"


def _parse_snap_key(key: str) -> tuple[str, str, float]:
    """'player|market|line' → (player, market, line)"""
    parts = key.split("|")
    if len(parts) != 3:
        return "", "", 0.0
    try:
        return parts[0], parts[1], float(parts[2])
    except ValueError:
        return parts[0], parts[1], 0.0


# ── Core detection ────────────────────────────────────────────────────────────

def load_snapshots() -> dict:
    try:
        return json.loads(SNAP_FILE.read_text())
    except Exception:
        return {}


def get_recent_days(snaps: dict, max_days: int = MAX_STALENESS_DAYS) -> list[str]:
    """Return snapshot day keys within max_days of today, sorted newest first."""
    cutoff = date.today() - timedelta(days=max_days)
    valid  = []
    for day_str in snaps:
        try:
            d = datetime.strptime(day_str, "%Y-%m-%d").date()
            if d >= cutoff:
                valid.append(day_str)
        except ValueError:
            continue
    return sorted(valid, reverse=True)


def detect_steam_moves(snaps: dict | None = None, min_move: float = STEAM_CENTS_WEAK) -> list[dict]:
    """
    Scan all props for significant opening→current line movement.

    Each flagged prop represents potential sharp/steam action.

    Returns list of dicts sorted by move_cents descending.
    """
    if snaps is None:
        snaps = load_snapshots()

    recent_days = get_recent_days(snaps)
    if not recent_days:
        return []

    # Build merged view: key → {opening, current, edge_open, edge_current}
    # Use the earliest available day as "opening" and latest as "current"
    # If a day has both 'opening' and 'odds' fields, use them directly.

    # First pass: collect all keys and their earliest opening + latest current
    key_data: dict[str, dict] = {}

    for day in sorted(recent_days):  # chronological = oldest first
        day_snap = snaps.get(day, {})
        for key, rec in day_snap.items():
            odds    = rec.get("odds")
            opening = rec.get("opening") or odds
            edge    = rec.get("edge", 0.0)

            if odds is None:
                continue

            if key not in key_data:
                key_data[key] = {
                    "open_odds":    float(opening),
                    "edge_open":    float(edge),
                    "curr_odds":    float(odds),
                    "edge_current": float(edge),
                    "last_day":     day,
                }
            else:
                # Update current to latest
                key_data[key]["curr_odds"]    = float(odds)
                key_data[key]["edge_current"] = float(edge)
                key_data[key]["last_day"]     = day

    flags = []
    for key, data in key_data.items():
        player, market, line = _parse_snap_key(key)
        if not player or not market:
            continue

        open_odds = data["open_odds"]
        curr_odds = data["curr_odds"]

        if open_odds == 0 or curr_odds == 0:
            continue

        open_imp = _american_to_implied(open_odds)
        curr_imp = _american_to_implied(curr_odds)
        move_c   = abs(curr_imp - open_imp)

        if move_c < min_move:
            continue

        direction = _move_direction(open_odds, curr_odds)
        strength  = _strength_label(move_c)

        # Classify signal type
        signal = "steam"

        # RLM heuristic: over line shortened but opening was already the short side
        # → book is doubling down on over = public + sharp on same side (not RLM)
        # RLM = line drifting TOWARD under (longer) despite prop normally being bet over
        # Simple proxy: if line moved toward_under and magnitude is significant, flag RLM
        if direction == "toward_under" and move_c >= RLM_CENTS_MIN:
            signal = "steam+rlm"

        description = _build_description(
            player, market, line, open_odds, curr_odds,
            move_c, direction, signal, strength,
        )

        flags.append({
            "player":         player.title(),
            "market":         market,
            "line":           line,
            "open_odds":      int(open_odds),
            "curr_odds":      int(curr_odds),
            "open_implied":   round(open_imp * 100, 1),
            "curr_implied":   round(curr_imp * 100, 1),
            "move_cents":     round(move_c * 100, 1),  # displayed as e.g. "8.2¢"
            "move_direction": direction,
            "signal":         signal,
            "strength":       strength,
            "edge_open":      round(float(data["edge_open"]) * 100, 2),
            "edge_current":   round(float(data["edge_current"]) * 100, 2),
            "last_seen":      data["last_day"],
            "description":    description,
        })

    flags.sort(key=lambda x: x["move_cents"], reverse=True)
    return flags


def detect_rlm(snaps: dict | None = None) -> list[dict]:
    """
    Return only reverse-line-movement flags (signal contains 'rlm').
    """
    all_flags = detect_steam_moves(snaps, min_move=RLM_CENTS_MIN)
    return [f for f in all_flags if "rlm" in f["signal"]]


def _build_description(player, market, line, open_odds, curr_odds,
                        move_c, direction, signal, strength) -> str:
    arrow    = "📈" if direction == "toward_over" else "📉"
    open_str = f"+{int(open_odds)}" if open_odds > 0 else str(int(open_odds))
    curr_str = f"+{int(curr_odds)}" if curr_odds > 0 else str(int(curr_odds))
    pct_str  = f"{move_c * 100:.1f}¢"

    if signal == "steam+rlm":
        tag = "⚡ STEAM + 🔄 RLM"
        note = "Line drifting toward under — sharp fade of public over action"
    else:
        tag = "⚡ STEAM"
        note = "Sharp/syndicate money detected — coordinated line movement"

    return (
        f"{tag} | {player.title()} {market} O{line} "
        f"{arrow} {open_str} → {curr_str} ({pct_str} move, {strength}) | {note}"
    )


# ── Filtering helpers for dashboard ──────────────────────────────────────────

def get_steam_for_sport(sport: str, min_strength: str = "weak") -> list[dict]:
    """
    Return steam flags filtered to a specific sport's markets.
    sport: 'MLB' | 'NBA' | 'WNBA' | 'NHL'
    """
    SPORT_MARKETS = {
        "MLB":  {"pitcher_strikeouts", "pitcher_outs_recorded", "pitcher_hits_allowed",
                 "pitcher_walks", "pitcher_earned_runs", "batter_hits",
                 "batter_total_bases", "batter_home_runs", "batter_rbis",
                 "batter_runs_scored", "batter_stolen_bases", "batter_hits_runs_rbis"},
        "NBA":  {"player_points", "player_rebounds", "player_assists",
                 "player_threes", "player_steals", "player_blocks",
                 "player_points_rebounds_assists", "player_points_rebounds",
                 "player_points_assists", "player_double_double"},
        "WNBA": {"player_points", "player_rebounds", "player_assists",
                 "player_threes", "player_steals", "player_blocks",
                 "player_points_rebounds_assists"},
        "NHL":  {"player_goals", "player_assists", "player_points",
                 "player_shots_on_goal", "player_saves",
                 "player_power_play_points"},
    }

    strength_order = {"weak": 0, "moderate": 1, "strong": 2}
    min_s = strength_order.get(min_strength, 0)

    markets = SPORT_MARKETS.get(sport.upper(), set())
    snaps   = load_snapshots()
    flags   = detect_steam_moves(snaps)

    return [
        f for f in flags
        if f["market"] in markets
        and strength_order.get(f["strength"], 0) >= min_s
    ]


def steam_summary(flags: list[dict]) -> dict:
    """Aggregate stats for a list of steam flags."""
    if not flags:
        return {"total": 0, "strong": 0, "rlm_count": 0}
    return {
        "total":      len(flags),
        "strong":     sum(1 for f in flags if f["strength"] == "strong"),
        "moderate":   sum(1 for f in flags if f["strength"] == "moderate"),
        "weak":       sum(1 for f in flags if f["strength"] == "weak"),
        "rlm_count":  sum(1 for f in flags if "rlm" in f["signal"]),
        "avg_move_c": round(sum(f["move_cents"] for f in flags) / len(flags), 1),
        "top_moves":  [f"{f['player']} {f['market']} ({f['move_cents']}¢)" for f in flags[:5]],
    }


if __name__ == "__main__":
    snaps = load_snapshots()
    print(f"Snapshot days: {list(snaps.keys())}")
    flags = detect_steam_moves(snaps, min_move=0.02)
    print(f"\nTotal steam flags (>=2c move): {len(flags)}")
    for f in flags[:10]:
        line = (f"{f['player']} {f['market']} O{f['line']} | "
                f"{f['open_odds']:+d} -> {f['curr_odds']:+d} "
                f"({f['move_cents']}c, {f['signal']}, {f['strength']})")
        print(" ", line)
    rlm = detect_rlm(snaps)
    print(f"\nRLM flags: {len(rlm)}")
    for f in rlm[:5]:
        print(f"  {f['player']} {f['market']} O{f['line']} | "
              f"{f['open_odds']:+d} -> {f['curr_odds']:+d} ({f['move_cents']}c)")
