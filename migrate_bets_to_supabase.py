"""
One-time migration: import data/bets.json into Supabase bets table.

Usage:
    python migrate_bets_to_supabase.py --user-id <supabase-user-uuid>
    python migrate_bets_to_supabase.py --user-id <uuid> --dry-run

Requires SUPABASE_URL and SUPABASE_SERVICE_KEY in .env or environment.
The service key is used so the migration can run outside a Streamlit session.
"""

import os
import sys
import json
import argparse
from pathlib import Path

# Load .env
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

BETS_FILE = Path(__file__).parent / "data" / "bets.json"

SUPABASE_URL        = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")


def _bet_to_row(bet: dict, user_id: str) -> dict:
    return {
        "id":           bet["id"],
        "user_id":      user_id,
        "date":         bet.get("date") or "2024-01-01",
        "time":         bet.get("time", ""),
        "sport":        bet.get("sport", ""),
        "player":       bet.get("player", ""),
        "prop":         bet.get("prop", ""),
        "line":         bet.get("line"),
        "odds":         bet.get("odds", 0),
        "stake":        bet.get("stake", 0.0),
        "book":         bet.get("book", ""),
        "result":       bet.get("result", "pending"),
        "profit":       bet.get("profit"),
        "sharp_odds":   bet.get("sharp_odds"),
        "fair_est":     bet.get("fair_est"),
        "edge":         bet.get("edge"),
        "opening_clv":  bet.get("opening_clv"),
        "closing_odds": bet.get("closing_odds"),
        "clv":          bet.get("clv"),
        "notes":        bet.get("notes", ""),
        "is_parlay":    bet.get("is_parlay", False),
        "parlay_legs":  bet.get("parlay_legs") or [],
    }


def migrate(user_id: str, dry_run: bool = False, batch_size: int = 50):
    if not BETS_FILE.exists():
        print(f"No bets file found at {BETS_FILE} — nothing to migrate.")
        return 0

    bets = json.loads(BETS_FILE.read_text())
    if not bets:
        print("bets.json is empty — nothing to migrate.")
        return 0

    print(f"Found {len(bets)} bets in {BETS_FILE}")

    if dry_run:
        print(f"[DRY RUN] Would upsert {len(bets)} bets for user {user_id}")
        for b in bets[:3]:
            print(f"  Sample: {b.get('date')} {b.get('sport')} {b.get('player')} — {b.get('result')}")
        if len(bets) > 3:
            print(f"  ... and {len(bets) - 3} more")
        return len(bets)

    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        print("ERROR: SUPABASE_URL and SUPABASE_SERVICE_KEY must be set.")
        sys.exit(1)

    from supabase import create_client
    client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

    rows = [_bet_to_row(b, user_id) for b in bets]

    inserted = 0
    skipped  = 0
    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        try:
            client.table("bets").upsert(batch, on_conflict="id").execute()
            inserted += len(batch)
            print(f"  Upserted batch {i//batch_size + 1}: {len(batch)} bets ({inserted}/{len(rows)} total)")
        except Exception as e:
            print(f"  ERROR on batch {i//batch_size + 1}: {e}")
            skipped += len(batch)

    print(f"\n✅ Migration complete: {inserted} inserted/updated, {skipped} skipped.")
    if inserted > 0:
        backup = BETS_FILE.with_suffix(".json.migrated")
        BETS_FILE.rename(backup)
        print(f"   Original file renamed to {backup.name} (kept as backup).")
    return inserted


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Migrate bets.json → Supabase")
    p.add_argument("--user-id",   required=True, help="Supabase user UUID to assign all bets to")
    p.add_argument("--dry-run",   action="store_true", help="Preview without writing")
    p.add_argument("--batch-size", type=int, default=50, help="Rows per upsert batch (default 50)")
    args = p.parse_args()

    n = migrate(args.user_id, dry_run=args.dry_run, batch_size=args.batch_size)
    print(f"Done. {n} bets processed.")
