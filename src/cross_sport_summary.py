"""
cross_sport_summary.py — Aggregate top-edge plays across ALL active sports in parallel.

Fetches props for every sport with status == "live" in SPORTS_CONFIG,
computes edge confidence scores, and returns the best plays ranked by
confidence desc then edge desc.
"""
from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

# ── Module-level TTL cache ────────────────────────────────────────────────────
_CACHE_TTL_SECONDS = 300  # 5 minutes

_cache: dict[str, Any] = {
    "timestamp": 0.0,
    "df": None,
}

# ── Required output columns ───────────────────────────────────────────────────
_OUTPUT_COLS = [
    "sport",
    "player",
    "team",
    "market",
    "line",
    "over_odds",
    "fair_est",
    "edge",
    "confidence",
]


def _live_sports() -> list[str]:
    """Return sport names whose SPORTS_CONFIG status is 'live'."""
    from odds_client import SPORTS_CONFIG
    return [sport for sport, cfg in SPORTS_CONFIG.items() if cfg.get("status") == "live"]


def _fetch_sport(sport: str) -> pd.DataFrame:
    """
    Fetch props for a single sport and attach the 'sport' column.
    The DataFrame returned by odds_client.get_props already contains
    edge and fair_est; we only add the sport label here.
    """
    from odds_client import get_props
    df = get_props(sport)
    if df.empty:
        return pd.DataFrame()
    df = df.copy()
    df["sport"] = sport
    return df


def _compute_confidence(row: pd.Series) -> int:
    """
    Compute a 0-100 confidence score for a prop row.
    Uses edge_confidence_score from edge_model if available; falls back
    to edge * 100 (clamped to 0-100).
    """
    try:
        from edge_model import edge_confidence_score
        return edge_confidence_score(
            edge=float(row.get("edge", 0.0)),
            fair_est=float(row.get("fair_est", 0.5)),
            edge_confirmed=False,
            n_books=1,
            over_odds=float(row.get("over_odds", -110)),
            clv_avg=None,
        )
    except Exception:
        raw = float(row.get("edge", 0.0)) * 100
        return int(min(max(raw, 0), 100))


def _build_df(min_confidence: int = 50) -> pd.DataFrame:
    """
    Fetch all live sports in parallel, combine, score, and filter.
    Returns a DataFrame with all output columns.
    """
    sports = _live_sports()
    if not sports:
        return pd.DataFrame(columns=_OUTPUT_COLS)

    frames: list[pd.DataFrame] = []

    with ThreadPoolExecutor(max_workers=min(len(sports), 8)) as pool:
        future_to_sport = {pool.submit(_fetch_sport, s): s for s in sports}
        for future in as_completed(future_to_sport):
            sport = future_to_sport[future]
            try:
                df = future.result()
                if not df.empty:
                    frames.append(df)
            except Exception as exc:
                logger.warning("cross_sport_summary: failed to fetch %s — %s", sport, exc)

    if not frames:
        return pd.DataFrame(columns=_OUTPUT_COLS)

    combined = pd.concat(frames, ignore_index=True)

    # Ensure required columns exist with sensible defaults
    for col in ("player", "team", "market", "line", "over_odds", "fair_est", "edge"):
        if col not in combined.columns:
            combined[col] = None

    # Compute confidence score for every row
    combined["confidence"] = combined.apply(_compute_confidence, axis=1)

    # Filter by min_confidence and positive edge
    combined = combined[
        (combined["confidence"] >= min_confidence) & (combined["edge"] > 0)
    ].copy()

    return combined


def _get_cached_df(min_confidence: int = 50) -> pd.DataFrame:
    """Return cached DataFrame if still fresh, otherwise rebuild."""
    now = time.time()
    if _cache["df"] is not None and (now - _cache["timestamp"]) < _CACHE_TTL_SECONDS:
        df: pd.DataFrame = _cache["df"]
        # Re-apply min_confidence filter on the cached full set
        return df[df["confidence"] >= min_confidence].copy()

    df = _build_df(min_confidence=0)  # cache unfiltered, filter on read
    _cache["df"] = df
    _cache["timestamp"] = now
    return df[df["confidence"] >= min_confidence].copy()


# ── Public API ────────────────────────────────────────────────────────────────

def get_best_plays(n: int = 20, min_confidence: int = 50) -> list[dict]:
    """
    Return the top-n edge plays across all active sports.

    Parameters
    ----------
    n:
        Maximum number of plays to return.
    min_confidence:
        Minimum composite confidence score (0-100). Plays below this are excluded.

    Returns
    -------
    list[dict]
        Each dict contains: sport, player, team, market, line, over_odds,
        fair_est, edge, confidence.  Sorted by confidence desc then edge desc.
    """
    df = get_best_plays_df(n=n, min_confidence=min_confidence)
    if df.empty:
        return []
    return df.to_dict(orient="records")


def get_best_plays_df(n: int = 20, min_confidence: int = 50) -> pd.DataFrame:
    """
    Return the top-n edge plays as a DataFrame.

    Columns guaranteed: sport, player, team, market, line, over_odds,
    fair_est, edge, confidence.

    Parameters
    ----------
    n:
        Maximum number of rows to return.
    min_confidence:
        Minimum composite confidence score (0-100).

    Returns
    -------
    pd.DataFrame
        Sorted by confidence desc then edge desc; at most n rows.
    """
    df = _get_cached_df(min_confidence=min_confidence)
    if df.empty:
        # Return empty frame with correct schema
        return pd.DataFrame(columns=_OUTPUT_COLS)

    df = df.sort_values(["confidence", "edge"], ascending=[False, False])

    # Ensure all output columns are present
    for col in _OUTPUT_COLS:
        if col not in df.columns:
            df[col] = None

    return df[_OUTPUT_COLS].head(n).reset_index(drop=True)
