"""
LightGBM Prop Prediction Model
================================
Per-sport LightGBM models that learn from historical bet results and
odds-snapshot data to produce a calibrated ML score (0-100) for each prop.

Why LightGBM:
  - Best-in-class on tabular sports data (beats neural nets without 100k+ rows)
  - Handles missing values natively (injured players, DNPs)
  - Fast enough to retrain on demand from the dashboard
  - Produces well-calibrated probabilities via built-in sigmoid output

Feature set (what we can build without external game logs):
  - implied_prob       : book's raw implied probability from current odds
  - opening_implied    : book's opening implied probability
  - odds_movement      : current_implied - opening_implied (+ = line shortened)
  - edge_at_open       : stored edge in snapshot at time of opening
  - edge_current       : stored edge in snapshot at current time
  - line_val           : prop line value (normalised per market)
  - market_bucket      : market category (0-8)
  - sport_code         : sport (0-4)
  - is_underdog        : 1 if over odds are positive
  - juice              : abs(odds) - 100 (proxy for book confidence)

Training data:
  - Primary: graded bets from bets.json (win/loss labels)
  - Augment: odds_snapshots for opening/movement features
  - With 115 graded bets: uses heavy regularisation + 5-fold CV
  - Grows more accurate as bets are graded

Usage:
    from prop_model import PropModel
    model = PropModel()
    model.train()

    # Score a single prop
    score = model.predict_score(
        odds=-125, opening_odds=-115, line=6.5,
        market='pitcher_strikeouts', sport='MLB',
        edge=0.03
    )  # → int 0-100

    # Score a batch (list of prop dicts)
    scored = model.score_props(props_df_or_list)
"""

import json
import math
import pickle
from pathlib import Path
from typing import Optional, Union

import numpy as np

DATA_DIR    = Path(__file__).parent.parent / "data"
BETS_FILE   = DATA_DIR / "bets.json"
SNAP_FILE   = DATA_DIR / "odds_snapshots.json"
MODEL_FILE  = DATA_DIR / "prop_lgbm_model.pkl"
STATS_FILE  = DATA_DIR / "prop_lgbm_stats.json"

ALL_SPORTS  = ["MLB", "NBA", "WNBA", "NHL"]


# ── Feature engineering ───────────────────────────────────────────────────────

MARKET_BUCKET = {
    "pitcher_strikeouts": 0, "pitcher_outs_recorded": 0,
    "pitcher_hits_allowed": 1, "pitcher_walks": 1, "pitcher_earned_runs": 1,
    "batter_hits": 2, "batter_total_bases": 2, "batter_home_runs": 2,
    "batter_rbis": 2, "batter_runs_scored": 2, "batter_stolen_bases": 2,
    "batter_hits_runs_rbis": 2,
    "player_points": 3, "player_rebounds": 4, "player_assists": 4,
    "player_threes": 4, "player_steals": 4, "player_blocks": 4,
    "player_points_rebounds_assists": 3, "player_points_rebounds": 3,
    "player_points_assists": 3, "player_double_double": 3,
    "player_goals": 5, "player_shots_on_goal": 5,
    "player_saves": 5, "player_power_play_points": 5,
}
SPORT_CODE = {"MLB": 0, "NBA": 1, "WNBA": 2, "NHL": 3}
FEATURE_NAMES = [
    "implied_prob", "opening_implied", "odds_movement",
    "edge_open", "edge_current", "line_norm",
    "market_bucket", "sport_code", "is_underdog", "juice_norm",
    "line_movement", "days_rest", "home_game",
]


def _imp(odds: float) -> float:
    if odds == 0:
        return 0.5
    if odds > 0:
        return 100.0 / (odds + 100.0)
    return abs(odds) / (abs(odds) + 100.0)


def _norm_line(line: float, market: str) -> float:
    """Normalise line to 0-1 based on typical market ranges."""
    ranges = {
        "pitcher_strikeouts": (2.5, 12.0),
        "pitcher_outs_recorded": (5.0, 24.0),
        "pitcher_hits_allowed": (3.5, 10.0),
        "batter_total_bases": (0.5, 5.0),
        "batter_hits": (0.5, 3.0),
        "player_points": (5.0, 40.0),
        "player_rebounds": (2.5, 15.0),
        "player_assists": (1.5, 12.0),
        "player_threes": (0.5, 5.5),
        "player_shots_on_goal": (1.5, 7.0),
    }
    lo, hi = ranges.get(market, (0.5, 10.0))
    return max(0.0, min(1.0, (line - lo) / max(hi - lo, 1.0)))


def build_features(
    odds: float,
    opening_odds: float,
    line: float,
    market: str,
    sport: str,
    edge: float = 0.0,
    edge_open: float = 0.0,
    line_movement: float = 0.0,
    days_rest: float = 3.0,
    home_game: float = 0.0,
) -> list[float]:
    imp      = _imp(odds)
    open_imp = _imp(opening_odds) if opening_odds else imp
    movement = imp - open_imp

    return [
        imp,                                       # implied_prob
        open_imp,                                  # opening_implied
        movement,                                  # odds_movement
        edge_open,                                 # edge at opening
        edge,                                      # edge current
        _norm_line(line, market),                  # line_norm
        MARKET_BUCKET.get(market, 6) / 7.0,        # market_bucket (norm)
        SPORT_CODE.get(sport.upper(), 0) / 4.0,    # sport_code (norm)
        1.0 if odds > 0 else 0.0,                  # is_underdog
        min(abs(odds) / 300.0, 1.0),               # juice_norm
        float(line_movement),                      # line_movement (open - current line)
        min(float(days_rest) / 14.0, 1.0),         # days_rest (normalised, cap 14)
        float(home_game),                          # home_game (0 or 1)
    ]


def _extract_bet_features(bet: dict, snap_index: dict) -> Optional[tuple[list, int]]:
    """
    Build feature vector and label from a graded bet dict.
    snap_index: {player|market|line → {odds, edge, opening}} for opening-line lookup.
    Returns (features, label) or None.
    """
    result = bet.get("result")
    if result not in ("win", "loss"):
        return None

    try:
        odds   = float(bet["odds"])
        line   = float(bet.get("line", 0.5))
        sport  = str(bet.get("sport", "MLB"))
        prop   = str(bet.get("prop", ""))
        market = prop.split()[0] if prop else ""
        label  = 1 if result == "win" else 0

        # Look up opening odds from snapshot index
        snap_key    = f"{bet.get('player','').lower()}|{market}|{line}"
        snap_entry  = snap_index.get(snap_key, {})
        open_odds   = float(snap_entry.get("opening", odds))
        edge_open   = float(snap_entry.get("edge", 0.0))

        # New contextual features — safe defaults when columns absent
        try:
            line_movement = float(bet.get("open_line", line)) - line
        except Exception:
            line_movement = 0.0

        try:
            import datetime
            last_date_str = bet.get("last_game_date")
            bet_date_str  = bet.get("date", "")
            if last_date_str and bet_date_str:
                days_rest = (
                    datetime.date.fromisoformat(bet_date_str[:10]) -
                    datetime.date.fromisoformat(last_date_str[:10])
                ).days
                days_rest = max(0.0, float(days_rest))
            else:
                days_rest = 3.0
        except Exception:
            days_rest = 3.0

        try:
            venue    = str(bet.get("home_away", bet.get("venue", ""))).lower()
            home_game = 1.0 if venue in ("home", "h") else 0.0
        except Exception:
            home_game = 0.0

        feats = build_features(
            odds=odds, opening_odds=open_odds,
            line=line, market=market, sport=sport,
            edge=0.0, edge_open=edge_open,
            line_movement=line_movement,
            days_rest=days_rest,
            home_game=home_game,
        )
        return feats, label

    except Exception:
        return None


def _build_snap_index(snaps: dict) -> dict:
    """Flatten snapshots into player|market|line → record for fast lookup."""
    idx = {}
    for day_data in snaps.values():
        for key, rec in day_data.items():
            if key not in idx:
                idx[key] = rec
            else:
                # Keep entry with actual opening odds (non-null)
                if rec.get("opening") and not idx[key].get("opening"):
                    idx[key] = rec
    return idx


# ── Model class ───────────────────────────────────────────────────────────────

class PropModel:
    """
    LightGBM-based prop scoring model.
    Score 0-100 replaces raw edge confidence when enough data is available.
    Can be initialised for a specific sport (per-sport model) or for all sports
    combined (unified fallback model).
    """

    MIN_SAMPLES = 20   # minimum graded bets before training (per sport)

    def __init__(self, sport: Optional[str] = None):
        """
        Parameters
        ----------
        sport : str or None
            If given (e.g. "MLB"), this model trains/loads only on that sport's
            bets and persists to ``data/prop_lgbm_{sport.lower()}.pkl``.
            If None, behaves as the unified model using ``data/prop_lgbm_model.pkl``.
        """
        self._sport   = sport.upper() if sport else None
        self._model   = None
        self._stats   = {}
        self._trained = False

        # Resolve file paths
        if self._sport:
            self._model_file = DATA_DIR / f"prop_lgbm_{self._sport.lower()}.pkl"
            self._stats_file = DATA_DIR / f"prop_lgbm_{self._sport.lower()}_stats.json"
        else:
            self._model_file = MODEL_FILE
            self._stats_file = STATS_FILE

        self._load()

    # ── Persistence ──────────────────────────────────────────────────────────

    def _load(self):
        if self._model_file.exists():
            try:
                bundle = pickle.loads(self._model_file.read_bytes())
                self._model   = bundle["model"]
                self._stats   = bundle.get("stats", {})
                self._trained = True
            except Exception:
                pass
        elif self._stats_file.exists():
            try:
                self._stats = json.loads(self._stats_file.read_text(encoding="utf-8"))
            except Exception:
                pass

    def _save(self):
        if self._model is not None:
            bundle = {"model": self._model, "stats": self._stats}
            self._model_file.write_bytes(pickle.dumps(bundle))
        self._stats_file.write_text(json.dumps(self._stats, indent=2), encoding="utf-8")

    # ── Training ─────────────────────────────────────────────────────────────

    def train(self, bets: Optional[list] = None, snaps: Optional[dict] = None) -> dict:
        """
        Train LightGBM on graded bets + odds snapshots.
        Returns stats dict with accuracy, AUC, feature importance.
        """
        try:
            import lightgbm as lgb
            from sklearn.calibration import CalibratedClassifierCV
            from sklearn.model_selection import StratifiedKFold, cross_val_score, TimeSeriesSplit
            from sklearn.metrics import roc_auc_score, brier_score_loss
        except ImportError as e:
            return {"status": "error", "msg": str(e)}

        if bets is None:
            bets = json.loads(BETS_FILE.read_text(encoding="utf-8")) if BETS_FILE.exists() else []
        if snaps is None:
            snaps = json.loads(SNAP_FILE.read_text(encoding="utf-8")) if SNAP_FILE.exists() else {}

        # Filter to this sport if we're a per-sport model
        if self._sport:
            bets = [b for b in bets if str(b.get("sport", "")).upper() == self._sport]

        snap_idx = _build_snap_index(snaps)

        # Sort chronologically so that temporal CV respects time ordering
        bets = sorted(bets, key=lambda b: str(b.get("date", "")))

        X_raw, y_raw = [], []
        for bet in bets:
            result = _extract_bet_features(bet, snap_idx)
            if result is not None:
                feats, label = result
                X_raw.append(feats)
                y_raw.append(label)

        n = len(X_raw)
        sport_label = f" ({self._sport})" if self._sport else ""
        if n < self.MIN_SAMPLES:
            self._stats = {
                "status": "insufficient_data",
                "n_samples": n,
                "sport": self._sport,
                "msg": f"Need ≥{self.MIN_SAMPLES} graded bets{sport_label}, have {n}.",
            }
            return self._stats

        X = np.array(X_raw, dtype=np.float32)
        y = np.array(y_raw, dtype=np.int32)

        # Conservative params to prevent overfitting on small dataset
        params = {
            "objective":       "binary",
            "metric":          "binary_logloss",
            "n_estimators":    min(200, n * 3),
            "learning_rate":   0.05,
            "num_leaves":      min(15, n // 8),
            "max_depth":       4,
            "min_child_samples": max(5, n // 15),
            "subsample":       0.8,
            "colsample_bytree": 0.8,
            "reg_alpha":       0.5,
            "reg_lambda":      1.0,
            "random_state":    42,
            "verbose":         -1,
            "n_jobs":          -1,
        }

        base_model = lgb.LGBMClassifier(**params)
        # Wrap with isotonic calibration (beta calibration) for reliable probabilities
        model = CalibratedClassifierCV(base_model, method="isotonic", cv=min(5, max(2, n // 20)))
        model.fit(X, y)
        train_preds = model.predict_proba(X)[:, 1]

        # Metrics
        brier  = float(brier_score_loss(y, train_preds))
        acc    = float(np.mean((train_preds >= 0.5) == y))
        try:
            auc = float(roc_auc_score(y, train_preds))
        except Exception:
            auc = 0.5

        # Temporal out-of-sample CV using TimeSeriesSplit (preserves time ordering)
        cv_auc = None
        oos_brier = None
        oos_auc = None
        if n >= 50:
            try:
                tscv = TimeSeriesSplit(n_splits=3)
                oos_preds, oos_labels = [], []
                for train_idx, test_idx in tscv.split(X):
                    m = lgb.LGBMClassifier(**params)
                    m.fit(X[train_idx], y[train_idx])
                    oos_preds.extend(m.predict_proba(X[test_idx])[:, 1])
                    oos_labels.extend(y[test_idx])
                if oos_labels:
                    oos_brier = round(float(brier_score_loss(oos_labels, oos_preds)), 4)
                    oos_auc = round(
                        float(roc_auc_score(oos_labels, oos_preds))
                        if len(set(oos_labels)) > 1 else 0.5, 4
                    )
                    cv_auc = oos_auc  # keep cv_auc populated for quality() below
            except Exception:
                pass

        # Feature importance
        importances = {}
        try:
            imp_vals = model.feature_importances_
            for name, val in zip(FEATURE_NAMES, imp_vals):
                importances[name] = int(val)
        except Exception:
            pass

        self._model   = model
        self._trained = True
        self._stats   = {
            "status":       "ok",
            "sport":        self._sport,
            "n_samples":    n,
            "n_wins":       int(y.sum()),
            "win_rate":     round(float(y.mean()), 4),
            "brier_score":  round(brier, 4),
            "train_auc":    round(auc, 4),
            "cv_auc":       cv_auc,
            "oos_auc":      oos_auc,
            "oos_brier":    oos_brier,
            "accuracy":     round(acc, 4),
            "importances":  importances,
            "params":       {k: v for k, v in params.items() if k not in ("verbose", "n_jobs", "random_state")},
            "quality":      _auc_quality(cv_auc or auc),
            "msg":          f"LightGBM{sport_label} trained on {n} bets | AUC={auc:.3f} | Brier={brier:.3f}",
        }
        self._save()
        return self._stats

    # ── Prediction ────────────────────────────────────────────────────────────

    def predict_prob(
        self,
        odds: float,
        line: float,
        market: str,
        sport: str,
        opening_odds: Optional[float] = None,
        edge: float = 0.0,
        edge_open: float = 0.0,
        fair_est: float = 0.5,
        line_movement: float = 0.0,
        days_rest: float = 3.0,
        home_game: float = 0.0,
    ) -> float:
        """
        Return ML-predicted win probability (0-1).
        Falls back to fair_est if model not trained or error occurs.
        """
        if not self._trained or self._model is None:
            return fair_est

        try:
            feats = build_features(
                odds=odds,
                opening_odds=opening_odds or odds,
                line=line,
                market=market,
                sport=sport,
                edge=edge,
                edge_open=edge_open,
                line_movement=line_movement,
                days_rest=days_rest,
                home_game=home_game,
            )
            X = np.array([feats], dtype=np.float32)
            p = float(self._model.predict_proba(X)[0, 1])

            # Blend: weight model more as n_samples grows
            n = self._stats.get("n_samples", 0)
            w = min(0.7, 0.3 + (n / 300) * 0.4)
            blended = w * p + (1.0 - w) * fair_est
            return round(min(max(blended, 0.001), 0.999), 4)
        except Exception:
            return fair_est

    def predict_score(
        self,
        odds: float,
        line: float,
        market: str,
        sport: str,
        opening_odds: Optional[float] = None,
        edge: float = 0.0,
        edge_open: float = 0.0,
        fair_est: float = 0.5,
    ) -> int:
        """Return ML score as int 0-100 (maps calibrated prob → score)."""
        p = self.predict_prob(
            odds=odds, line=line, market=market, sport=sport,
            opening_odds=opening_odds, edge=edge,
            edge_open=edge_open, fair_est=fair_est,
        )
        # Map probability to 0-100 score (50% prob → 50 score baseline)
        score = int(round(p * 100))
        return max(0, min(100, score))

    def score_props(self, props: Union[list, "pd.DataFrame"]) -> list[dict]:
        """
        Score a list of prop dicts or a DataFrame.
        Adds 'ml_score' (0-100) and 'ml_prob' (float) fields to each row.
        Returns enriched list.
        """
        try:
            import pandas as pd
            if isinstance(props, pd.DataFrame):
                rows = props.to_dict("records")
            else:
                rows = list(props)
        except ImportError:
            rows = list(props)

        out = []
        for row in rows:
            odds    = float(row.get("over_odds", row.get("odds", -110)))
            open_o  = float(row.get("opening_odds", odds))
            line    = float(row.get("line", 0.5))
            market  = str(row.get("market", row.get("prop", "").split()[0]))
            sport   = str(row.get("sport", "MLB"))
            edge    = float(row.get("edge", 0.0))
            fair    = float(row.get("fair_est", 0.5))

            # New contextual features — safe defaults when columns absent
            try:
                line_movement = float(row["open_line"]) - line if "open_line" in row else 0.0
            except Exception:
                line_movement = 0.0

            try:
                import datetime
                last_date_str = row.get("last_game_date")
                row_date_str  = row.get("date", "")
                if last_date_str and row_date_str:
                    days_rest = max(0.0, float((
                        datetime.date.fromisoformat(str(row_date_str)[:10]) -
                        datetime.date.fromisoformat(str(last_date_str)[:10])
                    ).days))
                else:
                    days_rest = 3.0
            except Exception:
                days_rest = 3.0

            try:
                venue     = str(row.get("home_away", row.get("venue", ""))).lower()
                home_game = 1.0 if venue in ("home", "h") else 0.0
            except Exception:
                home_game = 0.0

            prob  = self.predict_prob(
                odds=odds, opening_odds=open_o, line=line,
                market=market, sport=sport, edge=edge, fair_est=fair,
                line_movement=line_movement, days_rest=days_rest, home_game=home_game,
            )
            score = int(round(prob * 100))
            out.append({**row, "ml_prob": prob, "ml_score": max(0, min(100, score))})

        return out

    # ── Info ──────────────────────────────────────────────────────────────────

    @property
    def is_trained(self) -> bool:
        return self._trained and self._model is not None

    @property
    def stats(self) -> dict:
        return self._stats

    def summary(self) -> str:
        if not self.is_trained:
            return f"Not trained (need ≥{self.MIN_SAMPLES} graded bets)."
        s = self._stats
        return (
            f"LightGBM | n={s.get('n_samples','?')} | "
            f"AUC={s.get('cv_auc') or s.get('train_auc','?')} | "
            f"Brier={s.get('brier_score','?')} | "
            f"{s.get('quality','?')}"
        )

    def feature_importance_str(self) -> str:
        imp = self._stats.get("importances", {})
        if not imp:
            return ""
        ranked = sorted(imp.items(), key=lambda x: x[1], reverse=True)
        return " | ".join(f"{k}={v}" for k, v in ranked[:5])


def _auc_quality(auc: float) -> str:
    if auc >= 0.65:
        return "Strong"
    elif auc >= 0.58:
        return "Good"
    elif auc >= 0.53:
        return "Fair"
    else:
        return "Needs more data"


# ── Module-level singleton and per-sport registry ─────────────────────────────

_prop_model: Optional[PropModel] = None
_model_registry: dict[str, PropModel] = {}


def get_model() -> PropModel:
    """Return the unified (all-sports) model singleton."""
    global _prop_model
    if _prop_model is None:
        _prop_model = PropModel()
    return _prop_model


def get_prop_model(sport: str) -> PropModel:
    """
    Return cached per-sport model, initialising from disk if not yet loaded.
    Falls back to unified model if no sport-specific file exists yet.
    """
    key = sport.upper()
    if key not in _model_registry:
        m = PropModel(sport=key)
        # If sport-specific model isn't trained, fall back to unified
        if not m.is_trained and MODEL_FILE.exists():
            m = get_model()
        _model_registry[key] = m
    return _model_registry[key]


def train_prop_model(sport: Optional[str] = None, bets=None, snaps=None) -> dict:
    """
    Train (or retrain) the prop model.

    Parameters
    ----------
    sport : str or None
        If given, train only that sport's model.
        If None, train all sports (MLB, NBA, WNBA, NHL) in sequence and also
        retrain the unified model.  Returns a dict keyed by sport (plus
        ``"unified"``).
    """
    import logging
    log = logging.getLogger(__name__)

    if sport is not None:
        # Single-sport training
        key = sport.upper()
        m = PropModel(sport=key)
        result = m.train(bets=bets, snaps=snaps)
        _model_registry[key] = m
        return result

    # Train all sports then the unified model
    results: dict = {}
    for s in ALL_SPORTS:
        log.info("Training per-sport model: %s", s)
        m = PropModel(sport=s)
        r = m.train(bets=bets, snaps=snaps)
        _model_registry[s] = m
        results[s] = r
        if r.get("status") == "insufficient_data":
            log.warning("Skipping %s model — insufficient data: %s", s, r.get("msg"))
        else:
            log.info("%s model: %s", s, r.get("msg", r.get("status")))

    # Also retrain the unified model for backwards compatibility
    log.info("Training unified (all-sports) model…")
    global _prop_model
    _prop_model = PropModel()
    r_unified = _prop_model.train(bets=bets, snaps=snaps)
    results["unified"] = r_unified
    return results


def score_prop(
    odds: float = -110,
    line: float = 0.5,
    market: str = "",
    sport: str = "MLB",
    opening_odds: Optional[float] = None,
    edge: float = 0.0,
    fair_est: float = 0.5,
) -> int:
    """
    Convenience wrapper — returns ML score 0-100 for a single prop.
    Uses the sport-specific model when available, falls back to unified.
    """
    model = get_prop_model(sport) if sport else get_model()
    return model.predict_score(
        odds=odds, line=line, market=market, sport=sport,
        opening_odds=opening_odds, edge=edge, fair_est=fair_est,
    )


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys as _sys
    _sport_arg = _sys.argv[1].upper() if len(_sys.argv) > 1 else None
    if _sport_arg:
        print(f"Training LightGBM prop model for {_sport_arg}…")
        stats = train_prop_model(sport=_sport_arg)
        print(json.dumps({k: v for k, v in stats.items() if k != "params"}, indent=2))
        m = get_prop_model(_sport_arg)
    else:
        print("Training LightGBM prop models (all sports + unified)…")
        all_stats = train_prop_model()
        for s, st in all_stats.items():
            filtered = {k: v for k, v in st.items() if k != "params"}
            print(f"\n--- {s} ---")
            print(json.dumps(filtered, indent=2))
        m = get_model()
    print("\nSummary:", m.summary())
    print("Top features:", m.feature_importance_str())
    print()

    # Demo predictions
    demos = [
        {"odds": -130, "opening_odds": -115, "line": 6.5, "market": "pitcher_strikeouts",
         "sport": "MLB", "edge": 0.04, "fair_est": 0.60},
        {"odds": +110, "opening_odds": +120, "line": 7.5, "market": "player_rebounds",
         "sport": "NBA", "edge": 0.02, "fair_est": 0.53},
        {"odds": -105, "opening_odds": -110, "line": 1.5, "market": "player_threes",
         "sport": "WNBA", "edge": 0.03, "fair_est": 0.55},
    ]
    print("Sample ML scores:")
    for d in demos:
        s = score_prop(**{k: v for k, v in d.items()})
        print(f"  {d['market']:38s}  fair={d['fair_est']:.0%}  ML score={s}/100")
