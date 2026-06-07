"""
Sports Betting Plus — Scheduled Discord Daily Slip
===================================================
Run via Windows Task Scheduler each morning (e.g. 9:00 AM) to automatically
post today's top props and parlays to Discord.

One-time setup (run setup_scheduler.bat as Administrator, or manually):
    schtasks /Create /TN "SBP_DiscordSlip" /TR "C:\\Users\\kenan\\sports-betting-plus\\run_discord_slip.bat" /SC DAILY /ST 09:00 /RL HIGHEST /F

Manual run:
    python run_discord_slip.py
"""

import sys
import os
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent / "src"))

# Load .env
_env = Path(__file__).parent / ".env"
try:
    from dotenv import load_dotenv
    load_dotenv(_env)
except ImportError:
    if _env.exists():
        for _line in _env.read_text(encoding="utf-8").splitlines():
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                k, _, v = _line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


def main():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] Discord daily slip starting…")

    from discord_bot import is_configured, send_daily_slip, send

    if not is_configured():
        print("❌ DISCORD_WEBHOOK_URL not set in .env — aborting.")
        sys.exit(1)

    from scraper import scrape_props
    from parlay_builder import get_top_candidates, build_parlay_report
    from bet_tracker import get_stats

    SPORTS = ["MLB", "NBA", "WNBA", "NHL"]
    record = get_stats()

    all_sent = 0
    for sport in SPORTS:
        print(f"  Scraping {sport}…")
        try:
            df = scrape_props(sport)
            if df.empty:
                print(f"    No props found for {sport} today — skipping.")
                continue

            # Filter to positive-edge plays
            if "edge" in df.columns:
                df_edge = df[df["edge"] > 0].copy()
            else:
                df_edge = df.copy()

            if df_edge.empty:
                print(f"    No positive-edge props for {sport} — skipping.")
                continue

            picks = df_edge.sort_values("edge", ascending=False).to_dict("records")
            print(f"    {len(picks)} positive-edge props — building report…")

            # Build parlay report for top parlays
            report = build_parlay_report(df_edge, stake=10.0)
            parlays = report.get("parlays", {})

            ok = send_daily_slip(picks, parlays=parlays, record=record, sport=sport)
            if ok:
                print(f"    ✅ {sport} slip sent to Discord.")
                all_sent += 1
            else:
                print(f"    ⚠️ Discord send failed for {sport}.")

        except Exception as e:
            print(f"    ❌ {sport} error: {e}")

    if all_sent == 0:
        # Send a "no plays today" fallback message
        send(content=f"📅 **{datetime.now().strftime('%B %d, %Y')}** — No positive-edge plays found across MLB/NBA/WNBA/NHL today. Check back tomorrow!")
        print("Sent 'no plays' fallback message.")
    else:
        print(f"\n✅ Done — {all_sent} sport slip(s) sent to Discord.")


if __name__ == "__main__":
    main()
