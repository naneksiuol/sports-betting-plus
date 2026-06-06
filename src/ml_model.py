"""
LightGBM Prop Prediction Model
================================
Per-sport gradient boosting models that replace / augment manual edge scores.

Architecture:
  - One LightGBM binary classifier per sport (MLB / NBA / WNBA / NHL)
  - Features engineered from:
      * Historical bet results (bets.json)
      * Odds snapshot history (odds_snapshots.json) — rolling line movement
      * Market / sport / line / odds metadata
  - Output: calibrated win probability per leg
  - Falls back to de-vigged fair probability when model not trained

Feature set (per bet/prop):
  1.  Implied probability (from American odds)
  2.  Fair estimate (de-vigged)
  3.  Edge (fair - implied)
  4.  Line value
  5.  Opening odds vs current odds delta (line movement signal)
  6.  Opening odds implied probability
  7.  Market group (encoded)
  8.  Odds bucket
  9.  CLV at placement (if known)
  10. Is odds positive (underdog flag)

Model persistence: data/lgbm_{sport}.pkl
Minimum training samples per sport: 30 graded bets
"""

import json
import math
import pickle
from pathlib import Path
from datetime import datetime

import warnings
import numpy as np

warnings.filterwarnings("ignore", message="X does not have valid feature names")

DATA_DIR  = Path(__file__).parent.parent / "data"
BETS_FILE = DATA_DIR / "bets.json"
SNAP_FILE = DATA_DIR / "odds_snapshots.json"
MODEL_DIR = DATA_DIR

MIN_TRAIN_SAMPLES = 30   # per sport

SPORT_LIST = ["MLB", "NBA", "WNBA", "NHL"]

MARKET_GROUPS = {
    "pitcher_strikeouts": 0, "pitcher_outs_recorded": 0,
    "pitcher_hits_allowed": 1, "pitcher_walks": 1, "pitcher_earned_runs": 1,
    "batter_hits": 2, "batter_total_bases": 2, "batter_home_runs": 2,
    "batter_rbis": 2, "batter_runs_scored": 2, "batter_stolen_bases": 2,
    "batter_hits_runs_rbis": 2,
    "player_points": 3, "player_rebounds": 4, "player_assists": 4,
    "player_threes": 4, "player_steals": 4, "player_blocks": 4,
    "player_points_rebounds_assists": 3,
    "player_points_rebounds": 3, "player_points_assists": 3,
    "player_goals": 5, "player_shots_on_goal": 5,
    "player_saves": 5,
}

FEATURE_NAMES = [
    "logit_implied", "logit_fair", "edge",
    "line", "odds_move_delta", "open_implied",
    "market_group", "odds_bucket", "clv_at_placement", "is_dog",
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _american_to_implied(odds: float) -> float:
    if odds > 0:
        return 100 / (odds + 100)
    return abs(odds) / (abs(odds) + 100)


def _logit(p: float) -> float:
    p = min(max(p, 0.001), 0.999)
    return math.log(p / (1 - p))


def _load_snapshots() -> dict:
    try:
        return json.loads(SNAP_FILE.read_text())
    except Exception:
        return {}


def _snap_key(player: str, market: str, line: float) -> str:
    return f"{player.lower().strip()}|{market}|{line}"


def _get_opening_odds(player: str, market: str, line: float, snaps: dict) -> float | None:
    """Return the earliest recorded odds for a player/market/line."""
    key = _snap_key(player, market, line)
    for day in sorted(snaps.keys()):
        rec = snaps[day].get(key)
        if rec:
            return float(rec.get("opening", rec.get("odds", 0)) or 0)
    return None


def _extract_features(bet: dict, snaps: dict) -> list[float] | None:
    """Build feature vector from a bet dict + snapshot history."""
    try:
        odds     = float(bet.get("odds", 0))
        line     = float(bet.get("line", 0.5))
        prop     = bet.get("prop", "")
        fair_est = bet.get("fair_est")
        player   = bet.get("player", "")
        clv_raw  = bet.get("opening_clv")

        if odds == 0:
            return None

        market = prop.split(" ")[0] if prop else ""

        implied    = _american_to_implied(odds)
        fair       = float(fair_est) if fair_est else implied
        edge       = fair - implied
        logit_imp  = _logit(implied)
        logit_fair = _logit(fair)

        # Opening odds from snapshot (line movement signal)
        open_odds = _get_opening_odds(player, market, line, snaps)
        if open_odds and open_odds != 0:
            open_imp    = _american_to_implied(open_odds)
            move_delta  = implied - open_imp   # positive = line moved toward under
        else:
            open_imp   = implied
            move_delta = 0.0

        mgroup = float(MARKET_GROUPS.get(market, 6))

        if odds <= -200:   odds_bucket = 0.0
        elif odds <= -120: odds_bucket = 1.0
        elif odds <= -101: odds_bucket = 2.0
        elif odds <= 110:  odds_bucket = 3.0
        elif odds <= 150:  odds_bucket = 4.0
        else:              odds_bucket = 5.0

        clv_feat = float(clv_raw) if clv_raw is not None else 0.0
        is_dog   = 1.0 if odds > 0 else 0.0

        return [logit_imp, logit_fair, edge,
                line, move_delta, open_imp,
                mgroup, odds_bucket, clv_feat, is_dog]
    except Exception:
        return None


# ── Training ─────────────────────────────────────────────────────────────────

def train_models(force: bool = False) -> dict:
    """
    Train one LightGBM model per sport.
    Returns dict: {sport: {status, n_trained, auc, ...}}
    """
    try:
        import lightgbm as lgb
        from sklearn.metrics import roc_auc_score, brier_score_loss
        from sklearn.model_selection import StratifiedKFold
    except ImportError:
        return {"error": "lightgbm or scikit-learn not installed"}

    try:
        bets = json.loads(BETS_FILE.read_text())
    except Exception:
        return {"error": "Cannot load bets.json"}

    snaps = _load_snapshots()
    results = {}

    for sport in SPORT_LIST:
        model_path = MODEL_DIR / f"lgbm_{sport.lower()}.pkl"

        sport_bets = [
            b for b in bets
            if b.get("sport", "").upper() == sport
            and b.get("result") in ("win", "loss")
        ]
        n = len(sport_bets)

        if n < MIN_TRAIN_SAMPLES:
            results[sport] = {
                "status": "insufficient_data",
                "n_graded": n,
                "msg": f"Need {MIN_TRAIN_SAMPLES}, have {n}",
            }
            continue

        X_rows, y_rows = [], []
        for bet in sport_bets:
            feats = _extract_features(bet, snaps)
            if feats is None:
                continue
            X_rows.append(feats)
            y_rows.append(1.0 if bet["result"] == "win" else 0.0)

        if len(X_rows) < MIN_TRAIN_SAMPLES:
            results[sport] = {"status": "insufficient_features", "n_graded": n}
            continue

        X = np.array(X_rows, dtype=np.float64)
        y = np.array(y_rows, dtype=np.float64)

        # LightGBM params — conservative for small datasets
        params = {
            "objective":       "binary",
            "metric":          "auc",
            "n_estimators":    200,
            "learning_rate":   0.05,
            "num_leaves":      15,
            "min_child_samples": max(5, n // 10),
            "feature_fraction":  0.8,
            "bagging_fraction":  0.8,
            "bagging_freq":      5,
            "reg_alpha":         0.1,
            "reg_lambda":        0.1,
            "verbose":           -1,
            "random_state":      42,
        }

        model = lgb.LGBMClassifier(**params)

        # Cross-validation AUC (if enough samples)
        cv_auc = None
        if n >= 60:
            try:
                cv = StratifiedKFold(n_splits=3, shuffle=True, random_state=42)
                aucs = []
                for tr, val in cv.split(X, y):
                    m = lgb.LGBMClassifier(**params)
                    m.fit(X[tr], y[tr])
                    pv = m.predict_proba(X[val])[:, 1]
                    aucs.append(roc_auc_score(y[val], pv))
                cv_auc = round(float(np.mean(aucs)), 4)
            except Exception:
                pass

        # Final model on all data
        model.fit(X, y)
        preds  = model.predict_proba(X)[:, 1]
        brier  = float(brier_score_loss(y, preds))

        payload = {
            "model":        model,
            "feature_names": FEATURE_NAMES,
            "n_trained":    len(X_rows),
            "sport":        sport,
            "cv_auc":       cv_auc,
            "brier_score":  brier,
            "trained_at":   datetime.now().isoformat(),
            "win_rate":     float(np.mean(y)),
        }
        model_path.write_bytes(pickle.dumps(payload))

        results[sport] = {
            "status":     "ok",
            "n_trained":  len(X_rows),
            "cv_auc":     cv_auc,
            "brier_score": round(brier, 4),
            "win_rate":   round(float(np.mean(y)) * 100, 1),
        }

    return results


# ── Prediction ────────────────────────────────────────────────────────────────

def _load_model(sport: str) -> dict | None:
    path = MODEL_DIR / f"lgbm_{sport.lower()}.pkl"
    if not path.exists():
        return None
    try:
        return pickle.loads(path.read_bytes())
    except Exception:
        return None


def predict_win_prob(
    sport: str,
    odds: float,
    line: float,
    market: str = "",
    fair_est: float | None = None,
    player: str = "",
    clv_at_placement: float | None = None,
) -> dict:
    """
    Predict calibrated win probability for a single prop.

    Returns dict with:
      prob        — calibrated win probability
      source      — 'lgbm' | 'fair_est' | 'implied'
      edge_lgbm   — LightGBM edge vs book implied
      confidence  — 0-100 score based on LightGBM prob + edge
    """
    implied = _american_to_implied(odds)
    fair    = fair_est if fair_est is not None else implied

    model_data = _load_model(sport)
    snaps      = _load_snapshots()

    if model_data:
        try:
            # Build feature vector using a proxy bet dict
            proxy = {
                "odds": odds, "line": line,
                "prop": market, "fair_est": fair,
                "player": player, "opening_clv": clv_at_placement,
            }
            feats = _extract_features(proxy, snaps)
            if feats is not None:
                model = model_data["model"]
                X     = np.array([feats], dtype=np.float64)
                prob  = float(model.predict_proba(X)[0, 1])
                prob  = round(min(max(prob, 0.001), 0.999), 4)
                edge_lgbm = round(prob - implied, 4)
                conf = _prob_to_confidence(prob, implied)
                return {
                    "prob":       prob,
                    "source":     "lgbm",
                    "edge_lgbm":  edge_lgbm,
                    "confidence": conf,
                    "model_meta": {
                        "n_trained":  model_data.get("n_trained"),
                        "cv_auc":     model_data.get("cv_auc"),
                        "brier":      model_data.get("brier_score"),
                    },
                }
        except Exception:
            pass

    # Fallback
    prob = round(min(max(fair, 0.001), 0.999), 4)
    edge_fb = round(prob - implied, 4)
    return {
        "prob":       prob,
        "source":     "fair_est" if fair_est else "implied",
        "edge_lgbm":  edge_fb,
        "confidence": _prob_to_confidence(prob, implied),
        "model_meta": None,
    }


def _prob_to_confidence(prob: float, implied: float) -> int:
    """Convert LightGBM probability + implied to 0-100 confidence."""
    edge = prob - implied
    base = 0

    # Edge contribution (0-50)
    if edge >= 0.08:   base += 50
    elif edge >= 0.05: base += 40
    elif edge >= 0.03: base += 30
    elif edge >= 0.015: base += 20
    elif edge >= 0.01: base += 10
    elif edge > 0:     base += 4

    # Probability range contribution (0-30) — sweet spot 40-65%
    if 0.40 <= prob <= 0.65:   base += 30
    elif 0.30 <= prob <= 0.75: base += 20
    elif 0.20 <= prob <= 0.80: base += 10
    else:                       base += 3

    # Book implied reasonableness (0-20)
    if 0.35 <= implied <= 0.65: base += 20
    elif 0.25 <= implied <= 0.75: base += 12
    else:                          base += 5

    return min(int(base), 100)


# ── Model status ──────────────────────────────────────────────────────────────

def model_status() -> dict:
    """Return training status for all sports — for dashboard display."""
    try:
        bets = json.loads(BETS_FILE.read_text())
    except Exception:
        bets = []

    out = {}
    for sport in SPORT_LIST:
        n_graded = sum(
            1 for b in bets
            if b.get("sport", "").upper() == sport
            and b.get("result") in ("win", "loss")
        )
        model_data = _load_model(sport)
        if model_data:
            out[sport] = {
                "status":      "trained",
                "n_graded":    n_graded,
                "n_trained":   model_data.get("n_trained"),
                "cv_auc":      model_data.get("cv_auc"),
                "brier_score": model_data.get("brier_score"),
                "win_rate":    round(model_data.get("win_rate", 0) * 100, 1),
                "trained_at":  model_data.get("trained_at"),
            }
        else:
            out[sport] = {
                "status":   "untrained",
                "n_graded": n_graded,
                "msg":      f"Need {MIN_TRAIN_SAMPLES} graded bets, have {n_graded}",
            }
    return out


if __name__ == "__main__":
    print("Training LightGBM models…")
    results = train_models(force=True)
    for sport, info in results.items():
        print(f"\n  {sport}: {info}")
