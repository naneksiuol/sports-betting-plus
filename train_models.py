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
    """Read current model stats without retraining."""
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

    # ── 1. Prop model ──────────────────────────────────────────────────────────
    log.info("Step 1/2: Training LightGBM prop model…")
    before_model = _before_stats_model()
    log.info(
        "  Before — accuracy=%.4f  cv_auc=%s  n=%d",
        before_model.get("accuracy") or 0.0,
        before_model.get("cv_auc"),
        before_model.get("n_samples", 0),
    )

    after_model: dict = {}
    try:
        from src.prop_model import train_prop_model
        result = train_prop_model()
        status = result.get("status", "unknown")
        if status == "ok":
            after_model = {
                "accuracy":  result.get("accuracy"),
                "cv_auc":    result.get("cv_auc"),
                "n_samples": result.get("n_samples", 0),
                "status":    "ok",
            }
            log.info(
                "  After  — accuracy=%.4f  cv_auc=%s  n=%d  msg=%s",
                result.get("accuracy") or 0.0,
                result.get("cv_auc"),
                result.get("n_samples", 0),
                result.get("msg", ""),
            )
        elif status == "insufficient_data":
            after_model = {
                "accuracy":  None,
                "cv_auc":    None,
                "n_samples": result.get("n_samples", 0),
                "status":    "insufficient_data",
                "msg":       result.get("msg", ""),
            }
            log.warning("  Skipped — insufficient data: %s", result.get("msg", ""))
        else:
            after_model = {"status": status, "msg": result.get("msg", "")}
            log.error("  Error training model: %s", result.get("msg", status))
    except Exception as exc:
        after_model = {"status": "error", "msg": str(exc)}
        log.error("  Exception during model training: %s", exc)

    summary["model"] = {
        "before_accuracy": before_model.get("accuracy"),
        "after_accuracy":  after_model.get("accuracy"),
        "before_cv_auc":   before_model.get("cv_auc"),
        "after_cv_auc":    after_model.get("cv_auc"),
        "n_samples":       after_model.get("n_samples", before_model.get("n_samples", 0)),
        "status":          after_model.get("status", "unknown"),
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
    print(f"  Model:      {model.get('status')} | "
          f"accuracy {model.get('before_accuracy')} → {model.get('after_accuracy')} | "
          f"n={model.get('n_samples')}")
    print(f"  Calibrator: {cal.get('status')} | "
          f"brier {cal.get('before_brier')} → {cal.get('after_brier')} | "
          f"method={cal.get('method')}")


if __name__ == "__main__":
    main()
