"""
Auto-Retrain Pipeline
=====================
Retrains the LightGBM prop model and Platt/isotonic calibrator, then
logs metrics and optionally sends a Discord summary.

Usage:
    python train_models.py

Scheduled via run_grader.bat (daily at 02:00).
"""

import json
import logging
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

# Suppress LightGBM / sklearn verbosity
warnings.filterwarnings("ignore")

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

DATA_DIR      = Path(__file__).parent / "data"
RETRAIN_LOG   = DATA_DIR / "retrain_log.json"
MAX_LOG_ENTRIES = 30

# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_log() -> list:
    if RETRAIN_LOG.exists():
        try:
            return json.loads(RETRAIN_LOG.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def _save_log(entries: list) -> None:
    RETRAIN_LOG.write_text(
        json.dumps(entries[-MAX_LOG_ENTRIES:], indent=2),
        encoding="utf-8",
    )


# ── Model training helpers ────────────────────────────────────────────────────

def _before_stats_model() -> dict:
    """Read current model stats without retraining (unified model)."""
    try:
        from src.prop_model import get_model
        m = get_model()
        s = m.stats
        return {
            "accuracy":  s.get("accuracy"),
            "cv_auc":    s.get("cv_auc"),
            "n_samples": s.get("n_samples", 0),
            "status":    s.get("status", "unknown"),
        }
    except Exception as exc:
        log.warning("Could not read pre-train model stats: %s", exc)
        return {"status": "error", "accuracy": None, "cv_auc": None, "n_samples": 0}


def _before_stats_per_sport() -> dict:
    """Read current per-sport model stats without retraining."""
    from src.prop_model import ALL_SPORTS, PropModel
    per_sport = {}
    for sport in ALL_SPORTS:
        try:
            m = PropModel(sport=sport)
            s = m.stats
            per_sport[sport] = {
                "accuracy":  s.get("accuracy"),
                "cv_auc":    s.get("cv_auc"),
                "n_samples": s.get("n_samples", 0),
                "status":    s.get("status", "unknown"),
            }
        except Exception as exc:
            per_sport[sport] = {"status": "error", "msg": str(exc)}
    return per_sport


def _before_stats_calibrator() -> dict:
    """Read current calibrator stats without retraining."""
    try:
        from src.calibration import calibration_status
        cs = calibration_status()
        return {
            "brier_score": cs.get("brier_score"),
            "method":      cs.get("method"),
            "n_trained":   cs.get("n_graded", 0),
            "status":      cs.get("status", "unknown"),
        }
    except Exception as exc:
        log.warning("Could not read pre-train calibrator stats: %s", exc)
        return {"status": "error", "brier_score": None}


# ── Main pipeline ─────────────────────────────────────────────────────────────

def run_retrain() -> dict:
    """
    Run full retrain pipeline.

    Returns a summary dict:
        {
            "timestamp": "...",
            "model": {
                "before_accuracy": float|None,
                "after_accuracy":  float|None,
                "before_cv_auc":   float|None,
                "after_cv_auc":    float|None,
                "n_samples":       int,
                "status":          str,
            },
            "calibrator": {
                "before_brier": float|None,
                "after_brier":  float|None,
                "method":       str|None,
                "n_trained":    int,
                "status":       str,
            },
        }
    """
    log.info("=== Sports Betting Plus — Retrain Pipeline ===")

    summary: dict = {"timestamp": datetime.now(timezone.utc).isoformat()}

    # ── 1. Prop model (per-sport + unified) ───────────────────────────────────
    log.info("Step 1/2: Training LightGBM prop models (per-sport + unified)…")
    before_model   = _before_stats_model()
    before_by_sport = _before_stats_per_sport()
    log.info(
        "  Before (unified) — accuracy=%.4f  cv_auc=%s  n=%d",
        before_model.get("accuracy") or 0.0,
        before_model.get("cv_auc"),
        before_model.get("n_samples", 0),
    )

    after_by_sport: dict = {}
    after_unified:  dict = {}
    try:
        from src.prop_model import train_prop_model, ALL_SPORTS
        all_results = train_prop_model()   # trains all sports + unified
        after_unified = all_results.get("unified", {})

        for sport in ALL_SPORTS:
            result = all_results.get(sport, {})
            status = result.get("status", "unknown")
            if status == "ok":
                after_by_sport[sport] = {
                    "accuracy":  result.get("accuracy"),
                    "cv_auc":    result.get("cv_auc"),
                    "n_samples": result.get("n_samples", 0),
                    "status":    "ok",
                }
                log.info(
                    "  %s — accuracy=%.4f  cv_auc=%s  n=%d  msg=%s",
                    sport,
                    result.get("accuracy") or 0.0,
                    result.get("cv_auc"),
                    result.get("n_samples", 0),
                    result.get("msg", ""),
                )
            elif status == "insufficient_data":
                after_by_sport[sport] = {
                    "n_samples": result.get("n_samples", 0),
                    "status":    "insufficient_data",
                    "msg":       result.get("msg", ""),
                }
                log.warning("  %s skipped — %s", sport, result.get("msg", "insufficient data"))
            else:
                after_by_sport[sport] = {"status": status, "msg": result.get("msg", "")}
                log.error("  %s error: %s", sport, result.get("msg", status))

        u_status = after_unified.get("status", "unknown")
        if u_status == "ok":
            log.info(
                "  unified — accuracy=%.4f  cv_auc=%s  n=%d",
                after_unified.get("accuracy") or 0.0,
                after_unified.get("cv_auc"),
                after_unified.get("n_samples", 0),
            )
        else:
            log.warning("  unified — %s: %s", u_status, after_unified.get("msg", ""))

    except Exception as exc:
        after_unified  = {"status": "error", "msg": str(exc)}
        log.error("  Exception during model training: %s", exc)

    summary["model"] = {
        # Unified model stats (backwards-compatible keys)
        "before_accuracy": before_model.get("accuracy"),
        "after_accuracy":  after_unified.get("accuracy"),
        "before_cv_auc":   before_model.get("cv_auc"),
        "after_cv_auc":    after_unified.get("cv_auc"),
        "n_samples":       after_unified.get("n_samples", before_model.get("n_samples", 0)),
        "status":          after_unified.get("status", "unknown"),
        # Per-sport breakdown
        "per_sport": {
            sport: {
                "before": before_by_sport.get(sport, {}),
                "after":  after_by_sport.get(sport, {}),
            }
            for sport in (after_by_sport or before_by_sport)
        },
    }

    # ── 2. Calibrator ──────────────────────────────────────────────────────────
    log.info("Step 2/2: Training calibrator…")
    before_cal = _before_stats_calibrator()
    log.info(
        "  Before — brier=%s  method=%s  n=%d",
        before_cal.get("brier_score"),
        before_cal.get("method"),
        before_cal.get("n_trained", 0),
    )

    after_cal: dict = {}
    try:
        from src.calibration import train_calibrator
        result = train_calibrator(force=True)
        status = result.get("status", "unknown")
        if status == "ok":
            after_cal = {
                "brier_score": result.get("brier_score"),
                "method":      result.get("method"),
                "n_trained":   result.get("n_trained", 0),
                "status":      "ok",
            }
            log.info(
                "  After  — brier=%.4f  method=%s  n=%d",
                result.get("brier_score") or 0.0,
                result.get("method"),
                result.get("n_trained", 0),
            )
        elif status == "insufficient_data":
            after_cal = {
                "brier_score": None,
                "n_trained":   result.get("n_graded", 0),
                "status":      "insufficient_data",
                "msg":         result.get("msg", ""),
            }
            log.warning("  Skipped — insufficient data: %s", result.get("msg", ""))
        else:
            after_cal = {"status": status, "msg": result.get("msg", "")}
            log.error("  Error training calibrator: %s", result.get("msg", status))
    except Exception as exc:
        after_cal = {"status": "error", "msg": str(exc)}
        log.error("  Exception during calibrator training: %s", exc)

    summary["calibrator"] = {
        "before_brier": before_cal.get("brier_score"),
        "after_brier":  after_cal.get("brier_score"),
        "method":       after_cal.get("method") or before_cal.get("method"),
        "n_trained":    after_cal.get("n_trained", before_cal.get("n_trained", 0)),
        "status":       after_cal.get("status", "unknown"),
    }

    # ── 3. Persist log ────────────────────────────────────────────────────────
    try:
        entries = _load_log()
        entries.append(summary)
        _save_log(entries)
        log.info("Retrain log updated (%s entries kept).", min(len(entries), MAX_LOG_ENTRIES))
    except Exception as exc:
        log.error("Failed to write retrain log: %s", exc)

    return summary


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    summary = run_retrain()

    # Send Discord notification (silently skip if not configured)
    try:
        from src.discord_bot import send_retrain_summary, is_configured
        if is_configured():
            ok = send_retrain_summary(summary)
            log.info("Discord notification %s.", "sent" if ok else "failed")
        else:
            log.info("Discord webhook not configured — skipping notification.")
    except Exception as exc:
        log.warning("Discord notification error: %s", exc)

    # Print final summary to stdout so it lands in grader.log
    model   = summary.get("model", {})
    cal     = summary.get("calibrator", {})
    print("\n=== Retrain Summary ===")
    print(f"  Unified model: {model.get('status')} | "
          f"accuracy {model.get('before_accuracy')} → {model.get('after_accuracy')} | "
          f"n={model.get('n_samples')}")
    for sport, sp in model.get("per_sport", {}).items():
        after = sp.get("after", {})
        print(f"    {sport:6s}: {after.get('status','?'):20s} | "
              f"n={after.get('n_samples','?')} | "
              f"cv_auc={after.get('cv_auc','?')}")
    print(f"  Calibrator: {cal.get('status')} | "
          f"brier {cal.get('before_brier')} → {cal.get('after_brier')} | "
          f"method={cal.get('method')}")


if __name__ == "__main__":
    main()
