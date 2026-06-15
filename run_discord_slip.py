"""
Sports Betting Plus — Scheduled Discord Daily Slip
===================================================
Run via Windows Task Scheduler each morning (e.g. 9:00 AM) to automatically
post today's top props and parlays to Discord.

Also saves props_cache_{sport}.json for each sport so Streamlit Cloud
can display live data even when Action Network blocks cloud IPs.

One-time setup (run setup_scheduler.bat as Administrator, or manually):
    schtasks /Create /TN "SBP_DiscordSlip" /TR "C:\\Users\\kenan\\sports-betting-plus\\run_discord_slip.bat" /SC DAILY /ST 09:00 /RL HIGHEST /F

Manual run:
    python run_discord_slip.py
"""

import sys
import os
import json
import subprocess
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

DATA_DIR = Path(__file__).parent / "data"


def save_props_cache(sport: str, df) -> bool:
    """Save scraped props to data/props_cache_{sport}.json for Streamlit Cloud fallback."""
    try:
        cache_path = DATA_DIR / f"props_cache_{sport.lower()}.json"
        records = df.to_dict(orient="records")
        payload = {
            "scraped_at": datetime.now().isoformat(),
            "sport": sport,
            "rows": len(records),
            "data": records,
        }
        cache_path.write_text(json.dumps(payload, default=str), encoding="utf-8")
        print(f"    [SAVED] {len(records)} rows to {cache_path.name}")
        return True
    except Exception as e:
        print(f"    [WARN] Cache save failed: {e}")
        return False


def _git(args: list, cwd) -> subprocess.CompletedProcess:
    return subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True)


def save_game_lines_cache(sport: str) -> bool:
    """Save game lines to data/game_lines_{sport}.json for the deployed app."""
    try:
        from odds_client import get_game_lines
        gl = get_game_lines(sport)
        if gl.empty:
            print(f"    [INFO] No game lines for {sport}.")
            return False
        cache_path = DATA_DIR / f"game_lines_{sport.lower()}.json"
        payload = {
            "scraped_at": datetime.now().isoformat(),
            "sport": sport,
            "rows": len(gl),
            "data": gl.to_dict(orient="records"),
        }
        cache_path.write_text(json.dumps(payload, default=str), encoding="utf-8")
        print(f"    [SAVED] {len(gl)} game lines to {cache_path.name}")
        return True
    except Exception as e:
        print(f"    [WARN] Game lines cache save failed: {e}")
        return False


def push_cache_to_github():
    """Git add/commit/push the props and game-lines cache files.

    Rebases onto origin/main before pushing (the push silently failed for days
    when local main fell behind the remote) and retries with backoff, printing
    the real git error on failure instead of swallowing it.
    """
    import time
    try:
        repo = Path(__file__).parent
        cache_files = (list(DATA_DIR.glob("props_cache_*.json"))
                       + list(DATA_DIR.glob("game_lines_*.json")))
        if not cache_files:
            return
        paths = [str(f) for f in cache_files]

        r = _git(["add"] + paths, repo)
        if r.returncode != 0:
            print(f"    [WARN] git add failed: {r.stderr.strip()}")
            return
        if _git(["diff", "--cached", "--quiet"], repo).returncode == 0:
            print("    [INFO] No cache changes to push.")
            return

        msg = f"chore: refresh props cache {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        r = _git(["commit", "-m", msg], repo)
        if r.returncode != 0:
            print(f"    [WARN] git commit failed: {r.stderr.strip() or r.stdout.strip()}")
            return

        for attempt, delay in ((1, 2), (2, 4), (3, 8), (4, 16)):
            # Stash any unstaged changes so rebase doesn't fail, then restore them
            _git(["stash", "--include-untracked", "-m", "pre-push-stash"], repo)
            pull = _git(["pull", "--rebase", "origin", "main"], repo)
            _git(["stash", "pop"], repo)
            if pull.returncode != 0:
                _git(["rebase", "--abort"], repo)
                print(f"    [WARN] git pull --rebase failed: {pull.stderr.strip()}")
            r = _git(["push", "origin", "main"], repo)
            if r.returncode == 0:
                print(f"    [OK] Props cache pushed to GitHub ({len(cache_files)} files)")
                return
            print(f"    [WARN] git push attempt {attempt} failed: {r.stderr.strip()}")
            time.sleep(delay)
        print("    [ERROR] Could not push props cache after 4 attempts — "
              "the deployed app will keep serving stale data until this is fixed.")
    except Exception as e:
        print(f"    [WARN] GitHub push failed: {e}")


def main():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] Discord daily slip starting…")

    from discord_bot import is_configured, send_daily_slip, send
    from scraper import scrape_props
    from parlay_builder import build_parlay_report
    from bet_tracker import get_stats, get_clv_avg

    if not is_configured():
        print("ERROR: DISCORD_WEBHOOK_URL is not set. Set it in your .env file or environment and retry.")
        sys.exit(1)

    discord_ok = True

    SPORTS = ["MLB", "NBA", "WNBA", "NHL"]
    record = get_stats()
    clv_avg = get_clv_avg(n_recent=30)
    all_sent = 0

    for sport in SPORTS:
        print(f"  Scraping {sport}…")
        try:
            save_game_lines_cache(sport)
            df = scrape_props(sport)
            if df.empty:
                print(f"    No props found for {sport} today — skipping.")
                continue

            # Always save cache
            save_props_cache(sport, df)

            # Filter to positive-edge plays for Discord
            df_edge = df[df["edge"] > 0].copy() if "edge" in df.columns else df.copy()
            if df_edge.empty:
                print(f"    No positive-edge props for {sport} — skipping Discord.")
                continue

            picks = df_edge.sort_values("edge", ascending=False).to_dict("records")
            print(f"    {len(picks)} positive-edge props — building report…")

            report = build_parlay_report(df_edge, stake=10.0, sport=sport)
            parlays = report.get("parlays", {})

            ok = send_daily_slip(picks, parlays=parlays, record=record, sport=sport,
                                 clv_avg=clv_avg)
            if ok:
                print(f"    [OK] {sport} slip sent to Discord.")
                all_sent += 1
            else:
                print(f"    [WARN] Discord send failed for {sport}.")

        except Exception as e:
            print(f"    [ERR] {sport} error: {e}")

    # ── Watchlist injury alerts ───────────────────────────────────────────────
    print("\n  Checking watchlist injury alerts…")
    try:
        from watchlist import run_injury_alerts
        n_alerts = run_injury_alerts()
        if n_alerts:
            print(f"    [OK] Sent {n_alerts} watchlist injury alert(s).")
        else:
            print("    [INFO] No new injury alerts for watched players.")
    except Exception as e:
        print(f"    [WARN] Watchlist alert check failed: {e}")

    # Push all cache files to GitHub so Streamlit Cloud sees them
    print("\n  Pushing cache to GitHub…")
    push_cache_to_github()

    if all_sent == 0:
        send(content=f"📅 **{datetime.now().strftime('%B %d, %Y')}** — No positive-edge plays found across MLB/NBA/WNBA/NHL today. Check back tomorrow!")
        print("Sent 'no plays' fallback message.")
    else:
        print(f"\n[DONE] {all_sent} sport slip(s) sent to Discord.")

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] Finished.")


if __name__ == "__main__":
    main()
