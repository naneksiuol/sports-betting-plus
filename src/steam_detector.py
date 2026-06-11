"""
Steam Move Detector — The Odds API
====================================
Detects sharp money signals by comparing a live snapshot of player props
against a session-cached baseline taken earlier in the same session.

A "steam move" is flagged when the best available over-odds for a
player/market/line shifts by >= threshold_pct percentage points
(in implied-probability terms) between the baseline and current fetch.

Directions:
  "sharp" — odds improved (implied prob dropped), suggesting sharp money
             bet into the market and the books moved the price favourably
             relative to when we last looked.
  "fade"  — odds worsened (implied prob rose), suggesting the market is
             drifting against bettors (book steaming up the price, or public
             money pushing the implied prob higher).

Public API
----------
  snapshot_props(sport)          — save a baseline to the in-process cache
  detect_steam_moves(sport, ...) — compare live props against baseline
  get_steam_alerts(sport)        — auto-snapshot on first call, returns moves
                                   on subsequent calls within the session

Module-level cache
------------------
  _snapshots: dict  — keyed by sport, value is a DataFrame snapshot
"""

from __future__ import annotations

import os
import time
import warnings
from datetime import datetime

import pandas as pd

import odds_client
from odds_client import ODDS_API_BASE, SPORTS_CONFIG

# ── In-process snapshot cache ─────────────────────────────────────────────────
_snapshots: dict = {}   # sport → {"df": pd.DataFrame, "ts": float}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _american_to_implied(odds: float) -> float:
    if odds == 0:
        return 0.5
    if odds > 0:
        return 100.0 / (odds + 100.0)
    return abs(odds) / (abs(odds) + 100.0)


def _implied_to_american(p: float) -> int:
    p = min(max(p, 0.001), 0.999)
    if p >= 0.5:
        return int(round(-100 * p / (1 - p)))
    return int(round(100 * (1 - p) / p))


def _fetch_current(sport: str) -> pd.DataFrame:
    """Fetch live player props for *sport* using odds_client."""
    cfg = SPORTS_CONFIG.get(sport.upper())
    if not cfg or not cfg.get("key"):
        warnings.warn(f"steam_detector: unknown sport or no API key configured for '{sport}'")
        return pd.DataFrame()
    return odds_client._fetch_props_for_sport(cfg["key"], cfg["markets"])


# ── Core public functions ──────────────────────────────────────────────────────

def snapshot_props(sport: str) -> pd.DataFrame:
    """
    Fetch current props for *sport* and save them as the baseline snapshot.

    Returns the snapshot DataFrame (or empty DataFrame on failure).
    Called automatically by get_steam_alerts on the first invocation per sport.
    """
    df = _fetch_current(sport)
    _snapshots[sport.upper()] = {"df": df.copy(), "ts": time.time()}
    return df


def detect_steam_moves(
    sport: str,
    threshold_pct: float = 3.0,
) -> pd.DataFrame:
    """
    Compare live props against the session-cached baseline and return steam moves.

    Parameters
    ----------
    sport          : sport key, e.g. "MLB", "NBA", "NHL", "WNBA"
    threshold_pct  : minimum implied-probability shift (in percentage points)
                     to flag as a steam move.  Default 3.0 pp.

    Returns
    -------
    pd.DataFrame with columns:
      player, team, market, line,
      prev_odds, curr_odds,
      move_pct,        # signed change in implied prob (pp); positive = odds improved
      direction,       # "sharp" | "fade"
      edge             # current edge (from odds_client fair_est - book_implied)
    """
    snap = _snapshots.get(sport.upper())
    if snap is None or snap["df"].empty:
        warnings.warn(
            f"steam_detector: no baseline snapshot for '{sport}'. "
            "Call snapshot_props(sport) first."
        )
        return pd.DataFrame()

    prev_df: pd.DataFrame = snap["df"]
    curr_df: pd.DataFrame = _fetch_current(sport)

    if curr_df.empty:
        return pd.DataFrame()

    # Merge on player / market / line
    merge_cols = ["player", "market", "line"]
    merged = prev_df.merge(
        curr_df,
        on=merge_cols,
        suffixes=("_prev", "_curr"),
    )
    if merged.empty:
        return pd.DataFrame()

    rows = []
    for _, row in merged.iterrows():
        prev_odds = float(row["over_odds_prev"])
        curr_odds = float(row["over_odds_curr"])

        prev_imp = _american_to_implied(prev_odds) * 100.0
        curr_imp = _american_to_implied(curr_odds) * 100.0

        # Positive move_pct → implied prob dropped → odds got better → "sharp"
        # Negative move_pct → implied prob rose   → odds got worse  → "fade"
        move_pct = round(prev_imp - curr_imp, 3)

        if abs(move_pct) < threshold_pct:
            continue

        direction = "sharp" if move_pct > 0 else "fade"

        # Prefer the current edge; fall back to 0.0 if column absent
        edge_val = float(row.get("edge_curr", row.get("edge", 0.0)) or 0.0)

        team_val = row.get("team_curr", row.get("team_prev", ""))

        rows.append(
            {
                "player": row["player"],
                "team": team_val,
                "market": row["market"],
                "line": row["line"],
                "prev_odds": int(prev_odds),
                "curr_odds": int(curr_odds),
                "move_pct": move_pct,
                "direction": direction,
                "edge": round(edge_val, 4),
            }
        )

    if not rows:
        return pd.DataFrame(
            columns=["player", "team", "market", "line",
                     "prev_odds", "curr_odds", "move_pct", "direction", "edge"]
        )

    result = pd.DataFrame(rows)
    result.sort_values("move_pct", key=abs, ascending=False, inplace=True)
    result.reset_index(drop=True, inplace=True)
    return result


def get_steam_alerts(sport: str, threshold_pct: float = 3.0) -> pd.DataFrame:
    """
    Convenience wrapper:
      - First call per sport within a session: snapshots current props and
        returns an empty DataFrame (nothing to compare against yet).
      - Subsequent calls: runs detect_steam_moves against the saved baseline
        and returns any flagged moves.

    Parameters
    ----------
    sport          : e.g. "MLB", "NBA"
    threshold_pct  : implied-prob shift threshold in percentage points.

    Returns
    -------
    pd.DataFrame of steam moves (same schema as detect_steam_moves).
    """
    key = sport.upper()
    if key not in _snapshots:
        snapshot_props(sport)
        return pd.DataFrame(
            columns=["player", "team", "market", "line",
                     "prev_odds", "curr_odds", "move_pct", "direction", "edge"]
        )
    return detect_steam_moves(sport, threshold_pct=threshold_pct)


# ── CLI smoke-test ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    sport_arg = sys.argv[1] if len(sys.argv) > 1 else "MLB"
    thresh = float(sys.argv[2]) if len(sys.argv) > 2 else 3.0

    print(f"[steam_detector] Snapshotting {sport_arg} props...")
    snap_df = snapshot_props(sport_arg)
    print(f"  Snapshot captured: {len(snap_df)} rows")
    print(f"  Waiting 30 s before comparing...")
    time.sleep(30)

    print(f"[steam_detector] Detecting steam moves (threshold={thresh}pp)...")
    moves = detect_steam_moves(sport_arg, threshold_pct=thresh)
    if moves.empty:
        print("  No steam moves detected.")
    else:
        print(f"  {len(moves)} steam move(s) found:")
        for _, r in moves.iterrows():
            sign = "+" if r["move_pct"] > 0 else ""
            print(
                f"  [{r['direction'].upper():5s}] {r['player']} {r['market']} "
                f"O{r['line']} | {r['prev_odds']:+d} -> {r['curr_odds']:+d} "
                f"({sign}{r['move_pct']:.1f}pp) edge={r['edge']:.3f}"
            )
