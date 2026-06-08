"""
Line shopping — finds the best available odds across books for each prop.

The scraper currently captures FanDuel (fd_odds) and DraftKings (dk_odds).
get_best_lines() compares those two books and flags rows where the best
available line is 5+ American-odds points better than the displayed over_odds
(which is already the better of FD/DK, so "diff" here reflects how much
better the winning book is vs the other book).

If no book-specific columns exist the function returns df unchanged with
best_book=None columns added gracefully.
"""

from __future__ import annotations
import pandas as pd

# Threshold (American-odds points) to flag as a shop opportunity
SHOP_THRESHOLD = 5

# Human-readable labels for the book columns the scraper exposes
BOOK_COLS: dict[str, str] = {
    "fd_odds":   "FanDuel",
    "dk_odds":   "DraftKings",
    "espn_odds": "ESPN BET",
}


def _fmt_odds(v: float | None) -> str:
    """Format American odds as +115 / -110."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    iv = int(v)
    return f"+{iv}" if iv > 0 else str(iv)


def get_best_lines(df: pd.DataFrame) -> pd.DataFrame:
    """
    For each prop row find the best available American odds across known books.

    Adds columns:
      best_book        — short book name (e.g. "FanDuel") or None
      best_odds        — best American odds integer or None
      best_line_str    — formatted string e.g. "FanDuel: +115"
      best_vs_shown    — difference vs the displayed over_odds (positive = better)
      shop_alert       — True when best_vs_shown >= SHOP_THRESHOLD

    Returns df with added columns; original columns are untouched.
    If no recognised book columns exist the added columns are all None/False.
    """
    out = df.copy()

    # Discover which book columns are actually present
    present = {col: label for col, label in BOOK_COLS.items() if col in df.columns}

    if not present:
        out["best_book"] = None
        out["best_odds"] = None
        out["best_line_str"] = "—"
        out["best_vs_shown"] = 0
        out["shop_alert"] = False
        return out

    def _row_best(row):
        candidates: list[tuple[float, str]] = []
        for col, label in present.items():
            v = row.get(col)
            if v is not None and not (isinstance(v, float) and pd.isna(v)):
                candidates.append((float(v), label))

        if not candidates:
            return None, None, "—", 0, False

        # Higher American odds = better payout = preferred
        best_odds_val, best_label = max(candidates, key=lambda x: x[0])
        shown = row.get("over_odds")
        if shown is None or (isinstance(shown, float) and pd.isna(shown)):
            diff = 0
        else:
            diff = int(best_odds_val) - int(shown)

        line_str = f"{best_label}: {_fmt_odds(best_odds_val)}"
        alert = diff >= SHOP_THRESHOLD
        return best_label, int(best_odds_val), line_str, diff, alert

    results = out.apply(_row_best, axis=1, result_type="expand")
    results.columns = ["best_book", "best_odds", "best_line_str", "best_vs_shown", "shop_alert"]
    out = pd.concat([out, results], axis=1)
    return out


def build_shopping_summary(df: pd.DataFrame) -> pd.DataFrame:
    """
    Build a summary table for the Line Shopping expander.

    Input df should already have best_* columns from get_best_lines().
    Returns a display-ready DataFrame sorted by best_vs_shown descending,
    containing only rows with shop_alert == True (best line >= 5 pts better).
    """
    required = {"best_book", "best_odds", "best_vs_shown", "shop_alert"}
    if not required.issubset(df.columns):
        return pd.DataFrame()

    alerts = df[df["shop_alert"] == True].copy()
    if alerts.empty:
        return pd.DataFrame()

    rows = []
    for _, r in alerts.iterrows():
        shown = r.get("over_odds")
        rows.append({
            "Player":        r.get("player", "?"),
            "Prop":          r.get("market", "?"),
            "Your Line":     _fmt_odds(shown),
            "Best Available": _fmt_odds(r.get("best_odds")),
            "Book":          r.get("best_book", "?"),
            "Difference":    f"+{int(r['best_vs_shown'])} pts",
        })

    summary = pd.DataFrame(rows)
    # Sort by numeric difference descending
    summary["_diff_num"] = alerts["best_vs_shown"].values
    summary = summary.sort_values("_diff_num", ascending=False).drop(columns=["_diff_num"])
    return summary.reset_index(drop=True)
