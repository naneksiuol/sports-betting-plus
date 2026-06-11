"""
Auto-grade pending bets and update CLV for settled bets.

Usage:
    python run_result_grader.py
    python run_result_grader.py --user-id <uuid>
    python run_result_grader.py --dry-run

Designed to run as a cron job (e.g. every hour).
Requires ODDS_API_KEY in .env or environment.
"""
from __future__ import annotations

import os, sys, argparse
from pathlib import Path

_env = Path(__file__).parent / ".env"
try:
    from dotenv import load_dotenv
    load_dotenv(_env, override=True)
except ImportError:
    if _env.exists():
        for line in _env.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

sys.path.insert(0, str(Path(__file__).parent / "src"))


def main(user_id: str | None, dry_run: bool):
    if dry_run:
        from bet_tracker import load_bets
        bets = load_bets(user_id=user_id)
        pending = [b for b in bets if b.get("result") == "pending"]
        no_clv = [b for b in bets if b.get("result") not in ("pending", "") and not b.get("closing_odds")]
        print(f"[DRY RUN] Would attempt to grade {len(pending)} pending bets.")
        print(f"[DRY RUN] Would attempt CLV close for {len(no_clv)} settled bets with no closing odds.")
        return

    print("── Auto-grading pending bets ──")
    try:
        from result_grader import auto_grade_pending_bets
        result = auto_grade_pending_bets(user_id=user_id)
        print(f"  Graded: {result['graded']}  Skipped: {result['skipped']}  Errors: {result['errors']}")
        for d in result.get("details", [])[:10]:
            print(f"  {d}")
    except Exception as e:
        print(f"  ERROR: {e}")

    print("── Auto-closing CLV ──")
    try:
        from closing_line_scraper import auto_close_pending_clv
        result = auto_close_pending_clv(user_id=user_id)
        print(f"  Updated: {result['updated']}  Skipped: {result['skipped']}  Errors: {result['errors']}")
    except Exception as e:
        print(f"  ERROR: {e}")

    print("Done.")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Auto-grade bets and close CLV")
    p.add_argument("--user-id", default=None, help="Supabase user UUID (omit for JSON file mode)")
    p.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = p.parse_args()
    main(args.user_id, args.dry_run)
