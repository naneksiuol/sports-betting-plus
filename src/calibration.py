"""
Edge Confidence Score Calibration Engine
=========================================
Fixes the Kelly sizing problem: raw Edge Confidence Scores (0-100) are not
calibrated probabilities, so they feed incorrect Kelly fractions.

This module:
  1. Loads graded bets from bets.json
  2. Builds a Platt-scaling (logistic regression) calibrator mapping
     raw model signals → calibrated win probability
  3. Saves/loads the calibrator from data/calibrator.pkl
  4. Exposes calibrate_edge_score(score) → float probability
  5. Reports calibration quality: Brier score, reliability diagram data

Calibration signals used (from bet record):
  - implied probability from bet odds (via power de-vig)
  - edge stored at bet time (from odds snapshot)
  - market type (categorical → encoded)
  - sport
  - line value

With <50 graded bets: returns uncalibrated fallback (score / 100).
With 50+ graded bets: trains Platt scaling on logit(implied_prob) → win.
With 200+ graded bets: upgrades to isotonic regression (more flexible).
"""

import json
import math
import pickle
from pathlib import Path
from datetime import datetime

import numpy as np

DATA_DIR   = Path(__file__).parent.parent / "data"
BETS_FILE  = DATA_DIR / "bets.json"
CAL_FILE   = DATA_DIR / "calibrator.pkl"

MIN_PLATT    = 50    # minimum graded bets for Platt scaling
MIN_ISOTONIC = 200   # minimum for isotonic regression


# ── Market encoding ───────────────────────────────────────────────────────────

MARKET_GROUPS = {
    # MLB pitching
    "pitcher_strikeouts": 0, "pitcher_outs_recorded": 0,
    "pitcher_hits_allowed": 1, "pitcher_walks": 1, "pitcher_earned_runs": 1,
    # MLB batting
    "batter_hits": 2, "batter_total_bases": 2, "batter_home_runs": 2,
    "batter_rbis": 2, "batter_runs_scored": 2, "batter_stolen_bases": 2,
    "batter_hits_runs_rbis": 2,
    # NBA/WNBA
    "player_points": 3, "player_rebounds": 4, "player_assists": 4,
    "player_threes": 4, "player_steals": 4, "player_blocks": 4,
    "player_points_rebounds_assists": 3,
    "player_points_rebounds": 3, "player_points_assists": 3,
    # NHL
    "player_goals": 5, "player_shots_on_goal": 5,
    "player_saves": 5, "player_points": 5,
}
SPORT_IDX = {"MLB": 0, "NBA": 1, "WNBA": 2, "NHL": 3}


def _american_to_implied(odds: float) -> float:
    if odds > 0:
        return 100 / (odds + 100)
    return abs(odds) / (abs(odds) + 100)


def _extract_features(bet: dict) -> list[float] | None:
    """
    Extract feature vector from a bet dict.
    Returns None if the bet can't be featurised (missing data).
    """
    try:
        odds      = float(bet.get("odds", 0))
        line      = float(bet.get("line", 0.5))
        sport     = bet.get("sport", "MLB")
        prop      = bet.get("prop", "")
        fair_est  = bet.get("fair_est")      # stored at bet time if available
        edge_snap = bet.get("opening_clv")   # CLV at placement

        if odds == 0:
            return None

        implied = _american_to_implied(odds)

        # Logit of implied probability (Platt scaling input)
        implied_c = min(max(implied, 0.001), 0.999)
        logit_imp = math.log(implied_c / (1 - implied_c))

        # Fair estimate if stored, else use implied
        fair = float(fair_est) if fair_est else implied
        fair_c = min(max(fair, 0.001), 0.999)
        logit_fair = math.log(fair_c / (1 - fair_c))

        # Edge feature
        edge = fair - implied
        clv_feat = float(edge_snap) if edge_snap is not None else 0.0

        # Market group
        market = prop.split(" ")[0] if prop else ""
        mgroup = float(MARKET_GROUPS.get(market, 6))

        # Sport
        sport_idx = float(SPORT_IDX.get(sport, 0))

        # Line bucket (over/under tendency)
        line_bucket = 0.0 if line < 1.0 else (1.0 if line < 3.0 else (2.0 if line < 6.0 else 3.0))

        # Odds category (-200 to +200 buckets)
        if odds <= -200:
            odds_bucket = 0.0
        elif odds <= -120:
            odds_bucket = 1.0
        elif odds <= -101:
            odds_bucket = 2.0
        elif odds <= 110:
            odds_bucket = 3.0
        elif odds <= 150:
            odds_bucket = 4.0
        else:
            odds_bucket = 5.0

        return [logit_imp, logit_fair, edge, clv_feat,
                mgroup, sport_idx, line_bucket, odds_bucket]

    except Exception:
        return None


def load_training_data() -> tuple[np.ndarray, np.ndarray]:
    """
    Load graded bets and build (X, y) arrays.
    y = 1 if win, 0 if loss. Pushes/voids excluded.
    """
    try:
        bets = json.loads(BETS_FILE.read_text())
    except Exception:
        return np.array([]), np.array([])

    X_rows, y_rows = [], []
    for bet in bets:
        result = bet.get("result", "pending")
        if result not in ("win", "loss"):
            continue
        feats = _extract_features(bet)
        if feats is None:
            continue
        X_rows.append(feats)
        y_rows.append(1.0 if result == "win" else 0.0)

    if not X_rows:
        return np.array([]), np.array([])

    return np.array(X_rows, dtype=np.float64), np.array(y_rows, dtype=np.float64)


def train_calibrator(force: bool = False) -> dict:
    """
    Train and save calibration model. Returns status dict.
    force=True retrains even if calibrator.pkl is fresh.
    """
    try:
        from sklearn.linear_model import LogisticRegression
        from sklearn.isotonic import IsotonicRegression
        from sklearn.calibration import calibration_curve
        from sklearn.metrics import brier_score_loss
    except ImportError:
        return {"status": "error", "msg": "scikit-learn not installed"}

    X, y = load_training_data()
    n = len(y)

    if n < MIN_PLATT:
        return {
            "status": "insufficient_data",
            "n_graded": n,
            "msg": f"Need {MIN_PLATT} graded bets, have {n}. Using raw implied probability.",
        }

    # Choose method based on sample size
    method = "isotonic" if n >= MIN_ISOTONIC else "platt"

    if method == "platt":
        # Platt scaling: logistic regression on logit(implied_prob)
        cal = LogisticRegression(C=1.0, max_iter=1000)
        cal.fit(X, y)
        preds = cal.predict_proba(X)[:, 1]
    else:
        # Isotonic regression: more flexible, needs more data
        base = LogisticRegression(C=1.0, max_iter=1000)
        base.fit(X, y)
        raw_preds = base.predict_proba(X)[:, 1]
        cal = IsotonicRegression(out_of_bounds="clip")
        cal.fit(raw_preds, y)
        preds = cal.predict(raw_preds)
        # Store base model too so we can chain them at prediction time
        cal = {"base": base, "isotonic": cal}

    brier = float(brier_score_loss(y, preds))

    # Reliability curve (fraction of positives per predicted bin)
    try:
        frac_pos, mean_pred = calibration_curve(y, preds, n_bins=8)
        reliability = {
            "mean_pred": mean_pred.tolist(),
            "frac_pos":  frac_pos.tolist(),
        }
    except Exception:
        reliability = {}

    payload = {
        "model":       cal,
        "method":      method,
        "n_trained":   n,
        "brier_score": brier,
        "trained_at":  datetime.now().isoformat(),
        "reliability": reliability,
    }

    CAL_FILE.write_bytes(pickle.dumps(payload))

    return {
        "status":      "ok",
        "method":      method,
        "n_trained":   n,
        "brier_score": round(brier, 4),
        "msg":         f"Calibrator trained ({method}, n={n}, Brier={brier:.4f})",
    }


def _load_calibrator() -> dict | None:
    if not CAL_FILE.exists():
        return None
    try:
        return pickle.loads(CAL_FILE.read_bytes())
    except Exception:
        return None


def calibrate_score(raw_implied: float, edge: float = 0.0,
                    fair_est: float | None = None,
                    market: str = "", sport: str = "MLB",
                    line: float = 1.5, odds: float = -110) -> float:
    """
    Convert raw model signals → calibrated win probability.

    If calibrator is trained: runs through Platt/isotonic model.
    Otherwise: falls back to fair_est if available, else power de-vig implied.

    Args:
        raw_implied: Book implied probability (after de-vig not applied yet)
        edge:        Model edge (fair - implied)
        fair_est:    De-vigged fair probability
        market:      Market key string
        sport:       Sport string
        line:        Prop line value
        odds:        American odds

    Returns:
        Calibrated probability float [0.001, 0.999]
    """
    # Build feature vector
    fair = fair_est if fair_est is not None else (raw_implied + edge)
    bet_proxy = {
        "odds":     odds,
        "line":     line,
        "sport":    sport,
        "prop":     market,
        "fair_est": fair,
        "opening_clv": edge * 100,  # approximate
    }
    feats = _extract_features(bet_proxy)

    cal_data = _load_calibrator()

    if cal_data and feats is not None:
        try:
            model  = cal_data["model"]
            method = cal_data["method"]
            X      = np.array([feats], dtype=np.float64)

            if method == "isotonic":
                raw_prob = model["base"].predict_proba(X)[0, 1]
                prob     = float(model["isotonic"].predict([raw_prob])[0])
            else:
                prob = float(model.predict_proba(X)[0, 1])

            return round(min(max(prob, 0.001), 0.999), 4)
        except Exception:
            pass

    # Fallback: return fair_est if available, else implied
    fallback = fair_est if fair_est is not None else raw_implied
    return round(min(max(fallback, 0.001), 0.999), 4)


def calibration_status() -> dict:
    """Return current calibration metadata for display in the dashboard."""
    X, y = load_training_data()
    n = len(y)
    win_rate = float(np.mean(y)) if n > 0 else None

    cal_data = _load_calibrator()

    if cal_data is None:
        status = "untrained"
        brier   = None
        method  = None
        trained_at = None
        reliability = {}
    else:
        status     = "ok"
        brier      = cal_data.get("brier_score")
        method     = cal_data.get("method")
        trained_at = cal_data.get("trained_at")
        reliability = cal_data.get("reliability", {})

    return {
        "status":       status,
        "n_graded":     n,
        "win_rate":     round(win_rate * 100, 1) if win_rate is not None else None,
        "brier_score":  round(brier, 4) if brier else None,
        "method":       method,
        "trained_at":   trained_at,
        "reliability":  reliability,
        "min_platt":    MIN_PLATT,
        "min_isotonic": MIN_ISOTONIC,
    }


def brier_interpretation(brier: float) -> str:
    if brier <= 0.20:
        return "🔥 Excellent calibration"
    elif brier <= 0.22:
        return "✅ Good calibration"
    elif brier <= 0.24:
        return "🟡 Fair — model improving"
    elif brier <= 0.25:
        return "🟠 Near coin-flip baseline"
    else:
        return "🔴 Worse than coin-flip — needs more data"


if __name__ == "__main__":
    print("Training calibrator…")
    result = train_calibrator(force=True)
    print(result)
    status = calibration_status()
    print("\nCalibration Status:")
    for k, v in status.items():
        if k != "reliability":
            print(f"  {k}: {v}")
