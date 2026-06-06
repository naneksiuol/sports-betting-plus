"""
Line movement tracker.
Snapshots odds every scrape cycle and flags significant moves.

Steam move = multiple books moving the same direction quickly.
Reverse line = line moves opposite to public betting %.
"""

import json
from pathlib import Path
from datetime import datetime, date

SNAPSHOTS_FILE = Path(__file__).parent.parent / "data" / "odds_snapshots.json"
MOVEMENT_THRESHOLD = 5   # cents (American odds points) to flag as notable
STEAM_THRESHOLD = 10     # cents to flag as steam move


def load_snapshots() -> dict:
    if not SNAPSHOTS_FILE.exists():
        return {}
    try:
        return json.loads(SNAPSHOTS_FILE.read_text())
    except Exception:
        return {}


def save_snapshots(snapshots: dict):
    SNAPSHOTS_FILE.write_text(json.dumps(snapshots, indent=2))


def snapshot_key(player: str, market: str, line: float) -> str:
    return f"{player.lower()}|{market}|{line}"


def record_snapshot(df) -> dict:
    """
    Store current odds for all props.
    Returns movement dict for props that have moved since last snapshot.
    """
    today = date.today().isoformat()
    now = datetime.now().strftime("%H:%M")
    snapshots = load_snapshots()

    if today not in snapshots:
        snapshots[today] = {}

    movements = {}

    for _, row in df.iterrows():
        key = snapshot_key(row["player"], row["market"], row["line"])
        current_odds = int(row["over_odds"])
        current_edge = float(row.get("edge", 0))

        if key in snapshots[today]:
            prev = snapshots[today][key]
            prev_odds = prev.get("odds", current_odds)
            diff = current_odds - prev_odds  # positive = odds improved (less negative)

            if abs(diff) >= MOVEMENT_THRESHOLD:
                direction = "up" if diff > 0 else "down"
                is_steam = abs(diff) >= STEAM_THRESHOLD
                movements[key] = {
                    "player": row["player"],
                    "market": row["market"],
                    "line": row["line"],
                    "prev_odds": prev_odds,
                    "curr_odds": current_odds,
                    "diff": diff,
                    "direction": direction,
                    "is_steam": is_steam,
                    "time": now,
                }

        # Update snapshot
        snapshots[today][key] = {
            "odds": current_odds,
            "edge": current_edge,
            "time": now,
            "opening": snapshots[today].get(key, {}).get("opening", current_odds),
        }

    save_snapshots(snapshots)

    # Clean old days (keep last 3 days)
    all_dates = sorted(snapshots.keys())
    if len(all_dates) > 3:
        for old_date in all_dates[:-3]:
            del snapshots[old_date]
        save_snapshots(snapshots)

    return movements


def get_movement_for_df(df) -> dict:
    """
    Returns movement info for each prop in the current df.
    Key = snapshot_key, value = {diff, direction, opening_odds, is_steam}
    """
    today = date.today().isoformat()
    snapshots = load_snapshots()
    day_snaps = snapshots.get(today, {})
    result = {}

    for _, row in df.iterrows():
        key = snapshot_key(row["player"], row["market"], row["line"])
        snap = day_snaps.get(key, {})
        opening = snap.get("opening")
        current = int(row["over_odds"])

        if opening and opening != current:
            diff = current - opening
            result[key] = {
                "opening": opening,
                "current": current,
                "diff": diff,
                "direction": "up" if diff > 0 else "down",
                "is_steam": abs(diff) >= STEAM_THRESHOLD,
            }

    return result


def get_steam_alerts(df) -> list[dict]:
    """Return list of steam moves from current snapshot comparison."""
    movements = record_snapshot(df)
    return [m for m in movements.values() if m.get("is_steam")]


def format_movement(diff: int) -> str:
    """Format movement as arrow + number for display."""
    if diff == 0:
        return ""
    arrow = "📈" if diff > 0 else "📉"
    sign = "+" if diff > 0 else ""
    return f"{arrow} {sign}{diff}"
