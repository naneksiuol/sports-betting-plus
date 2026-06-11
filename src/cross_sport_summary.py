"""
Cross-Sport Best Plays Summary
================================
Aggregates the top positive-edge props across all active sports into a single
ranked DataFrame.  Used by the "Best Plays" tab in props_dashboard.py and by
the daily email/Discord slip.

Module-level TTL cache (300 s) avoids hammering the odds API when the
function is called from multiple tabs in quick succession.
"""

import time
from pathlib import Path
import sys
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

# ── Module-level cache ────────────────────────────────────────────────────────
_CACHE: dict = {}       # key → {"ts": float, "data": pd.DataFrame}
_CACHE_TTL  = 300       # seconds


def _cached(key: str, fn, *args, **kwargs) -> pd.DataFrame:
    """Generic TTL-cache wrapper."""
    now = time.monotonic()
    entry = _CACHE.get(key)
    if entry and (now - entry["ts"]) < _CACHE_TTL:
        return entry["data"]
    result = fn(*args, **kwargs)
    _CACHE[key] = {"ts": now, "data": result}
    return result


# ── Core function ─────────────────────────────────────────────────────────────

def _build_best_plays_df(
    min_edge: float = 0.01,
    max_odds: int = 400,
    top_n: int = 50,
) -> pd.DataFrame:
    """
    Fetch live props for all active sports and return the top ``top_n`` plays
    sorted by edge descending.

    Parameters
    ----------
    min_edge : float
        Minimum edge (as a fraction, e.g. 0.01 = 1%) to include a play.
    max_odds : int
        Maximum American odds to include (avoids extreme long-shots).
    top_n : int
        Maximum number of rows to return.

    Returns
    -------
    pd.DataFrame with columns: sport, player, team, market, line,
        over_odds, fair_est, book_implied, edge, n_books, confidence
    """
    from odds_client import get_props, SPORTS_CONFIG
    from edge_model import edge_confidence_score, confidence_label

    frames: list[pd.DataFrame] = []

    live_sports = [s for s, cfg in SPORTS_CONFIG.items() if cfg.get("status", "live") == "live"]

    for sport in live_sports:
        try:
            df = get_props(sport)
            if df is None or df.empty:
                continue
            df = df.copy()
            df["sport"] = sport
            frames.append(df)
        except Exception:
            # Individual sport failure should not block the rest
            pass

    if not frames:
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)

    # Ensure required columns have sane defaults
    if "edge" not in combined.columns:
        return pd.DataFrame()

    combined["edge"] = pd.to_numeric(combined["edge"], errors="coerce").fillna(0.0)

    # Filter
    mask = (combined["edge"] >= min_edge)
    if "over_odds" in combined.columns:
        combined["over_odds"] = pd.to_numeric(combined["over_odds"], errors="coerce")
        mask &= combined["over_odds"] <= max_odds
    combined = combined[mask].copy()

    if combined.empty:
        return combined

    # Add confidence score
    def _conf(row):
        try:
            return edge_confidence_score(
                float(row.get("edge", 0)),
                float(row.get("fair_est", 0.5)),
                int(row.get("n_books", 1)),
            )
        except Exception:
            return 0

    combined["confidence"] = combined.apply(_conf, axis=1)
    combined["conf_label"] = combined["confidence"].apply(
        lambda c: confidence_label(c) if c else "—"
    )

    # Sort by edge descending, return top N
    combined = combined.sort_values("edge", ascending=False).head(top_n)
    combined = combined.reset_index(drop=True)

    return combined


def get_best_plays_df(
    min_edge: float = 0.01,
    max_odds: int = 400,
    top_n: int = 50,
    use_cache: bool = True,
) -> pd.DataFrame:
    """
    Public entry point.  Returns the top cross-sport plays as a DataFrame,
    backed by a 300-second module-level TTL cache.

    Parameters
    ----------
    min_edge : float
        Minimum edge fraction to include (default 1%).
    max_odds : int
        Maximum American moneyline to include (default +400).
    top_n : int
        Max rows to return (default 50).
    use_cache : bool
        Set False to force a fresh fetch (e.g. on manual refresh).
    """
    cache_key = f"best_plays_{min_edge}_{max_odds}_{top_n}"
    if use_cache:
        return _cached(cache_key, _build_best_plays_df, min_edge, max_odds, top_n)
    result = _build_best_plays_df(min_edge, max_odds, top_n)
    _CACHE[cache_key] = {"ts": time.monotonic(), "data": result}
    return result


def clear_cache() -> None:
    """Evict all cached data (call after a manual refresh)."""
    _CACHE.clear()


if __name__ == "__main__":
    df = get_best_plays_df(use_cache=False)
    if df.empty:
        print("No positive-edge plays found (check ODDS_API_KEY or scraper).")
    else:
        cols = ["sport", "player", "market", "line", "over_odds", "edge", "conf_label"]
        print(df[[c for c in cols if c in df.columns]].to_string(index=False))
