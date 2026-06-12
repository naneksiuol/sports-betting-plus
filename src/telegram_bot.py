"""
Telegram bot for Sports Betting Plus.
Uses raw Telegram Bot API — no extra packages needed.

Setup:
  1. Message @BotFather on Telegram → /newbot → copy token
  2. Add TELEGRAM_BOT_TOKEN=xxx to .env
  3. Run: python setup_telegram.py  → prints your TELEGRAM_CHAT_ID
  4. Add TELEGRAM_CHAT_ID=xxx to .env

Subscribers: stored in data/telegram_subscribers.json
"""

import os
import json
import requests
from pathlib import Path
from datetime import datetime

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

API_BASE = "https://api.telegram.org/bot"
SUBS_FILE = Path(__file__).parent.parent / "data" / "telegram_subscribers.json"


# ── Config ────────────────────────────────────────────────────────────────────

def get_token() -> str:
    return os.environ.get("TELEGRAM_BOT_TOKEN", "")


def get_owner_chat_id() -> str:
    return os.environ.get("TELEGRAM_CHAT_ID", "")


def is_configured() -> bool:
    return bool(get_token() and get_owner_chat_id())


# ── Subscriber management ─────────────────────────────────────────────────────

def load_tg_subscribers() -> list[str]:
    if not SUBS_FILE.exists():
        return []
    try:
        return json.loads(SUBS_FILE.read_text())
    except Exception:
        return []


def save_tg_subscribers(chat_ids: list[str]):
    SUBS_FILE.write_text(json.dumps(list(set(chat_ids)), indent=2))


def add_tg_subscriber(chat_id: str) -> tuple[bool, str]:
    subs = load_tg_subscribers()
    if chat_id in subs:
        return False, f"{chat_id} already subscribed."
    subs.append(chat_id)
    save_tg_subscribers(subs)
    return True, f"Added {chat_id}"


def remove_tg_subscriber(chat_id: str) -> tuple[bool, str]:
    subs = load_tg_subscribers()
    if chat_id not in subs:
        return False, f"{chat_id} not found."
    subs.remove(chat_id)
    save_tg_subscribers(subs)
    return True, f"Removed {chat_id}"


def all_recipients() -> list[str]:
    """Owner chat_id + all subscribers, deduplicated."""
    recipients = set(load_tg_subscribers())
    owner = get_owner_chat_id()
    if owner:
        recipients.add(owner)
    return list(recipients)


# ── Core sending ──────────────────────────────────────────────────────────────

def send_message(chat_id: str, text: str, parse_mode: str = "HTML") -> bool:
    token = get_token()
    if not token:
        return False
    try:
        resp = requests.post(
            f"{API_BASE}{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": parse_mode,
                  "disable_web_page_preview": True},
            timeout=10,
        )
        return resp.status_code == 200
    except Exception:
        return False


def broadcast(text: str, parse_mode: str = "HTML") -> dict:
    """Send to owner + all subscribers. Returns {sent, failed}."""
    results = {"sent": [], "failed": []}
    for cid in all_recipients():
        if send_message(cid, text, parse_mode):
            results["sent"].append(cid)
        else:
            results["failed"].append(cid)
    return results


def get_updates() -> list[dict]:
    """Fetch latest messages (used to discover chat_id)."""
    token = get_token()
    if not token:
        return []
    try:
        resp = requests.get(f"{API_BASE}{token}/getUpdates", timeout=10)
        return resp.json().get("result", [])
    except Exception:
        return []


# ── Message formatters ────────────────────────────────────────────────────────

def fmt_pick(player: str, prop: str, line: float, over_odds: int,
             edge: float, kelly_stake: float, clv: float = None,
             sport: str = "MLB", is_steam: bool = False) -> str:
    steam = "🔥 <b>STEAM MOVE</b>\n" if is_steam else ""
    odds_str = f"+{over_odds}" if over_odds > 0 else str(over_odds)
    clv_str = f"\nOpening CLV: <b>{clv:+.1f}%</b>" if clv is not None else ""
    edge_emoji = "🔥" if edge >= 0.05 else ("✅" if edge >= 0.03 else "🟡")

    return (
        f"{steam}"
        f"{edge_emoji} <b>{player}</b>\n"
        f"📋 {sport} | {prop} O{line}\n"
        f"💰 Odds: <b>{odds_str}</b>\n"
        f"📊 Edge: <b>{edge:+.1%}</b>{clv_str}\n"
        f"🏦 Kelly Stake: <b>${kelly_stake:.2f}</b>\n"
        f"⏰ {datetime.now().strftime('%I:%M %p CT')}"
    )


def fmt_daily_slip(picks: list[dict], parlays: dict = None,
                   record: dict = None) -> str:
    today = datetime.now().strftime("%B %d, %Y")
    lines = [
        f"🎯 <b>PropLens</b>",
        f"📅 Daily Slip — {today}",
        "",
    ]

    if record:
        w = record.get("wins", 0)
        l = record.get("losses", 0)
        roi = record.get("roi", 0)
        lines += [
            f"📈 Record: <b>{w}W-{l}L</b> | ROI: <b>{roi:+.1f}%</b>",
            "",
        ]

    lines += [f"🏆 <b>Top {len(picks)} Plays (Best Odds First)</b>", ""]

    for i, p in enumerate(picks, 1):
        odds = p.get("over_odds", 0)
        odds_str = f"+{int(odds)}" if odds > 0 else str(int(odds))
        edge = p.get("edge", 0)
        lines.append(
            f"{i}. <b>{p['player']}</b> — {p.get('prop_label', p.get('market',''))} "
            f"O{p.get('line',0.5)} | {odds_str} | Edge: {edge:+.1%}"
        )

    if parlays:
        lines += ["", "🎰 <b>Parlay Picks</b>"]
        for n, parlay in parlays.items():
            pout = parlay.get("payout", {})
            lines.append(
                f"\n{n.replace('_',' ').title()} → "
                f"<b>{pout.get('american_odds','?')}</b> "
                f"(${pout.get('payout',0):.2f} on ${pout.get('stake',10):.0f})"
            )
            for j, leg in enumerate(parlay.get("legs", []), 1):
                odds_l = int(leg.get("over_odds", 0))
                odds_str_l = f"+{odds_l}" if odds_l > 0 else str(odds_l)
                lines.append(
                    f"  {j}. {leg['player']} — "
                    f"{leg.get('prop_label', leg.get('market',''))} "
                    f"O{leg.get('line','')} ({odds_str_l})"
                )

    lines += [
        "",
        "⚠️ 21+ only. Not betting advice. Past performance ≠ future results.",
        "Gambling problem? Call or text 1-800-GAMBLER.",
        "📱 PropLens",
    ]
    return "\n".join(lines)


def fmt_steam_alert(player: str, market: str, prev_odds: int,
                    curr_odds: int, diff: int) -> str:
    direction = "improved" if diff > 0 else "moved shorter"
    return (
        f"🔥 <b>STEAM ALERT</b>\n\n"
        f"<b>{player}</b> — {market}\n"
        f"Line {direction}: <b>{prev_odds:+d} → {curr_odds:+d}</b> ({diff:+d})\n"
        f"⚡ Sharp money detected\n"
        f"⏰ {datetime.now().strftime('%I:%M %p CT')}"
    )


def fmt_grade_report(graded: int, wins: int, losses: int,
                     pushes: int, roi: float, profit: float) -> str:
    emoji = "📈" if profit >= 0 else "📉"
    return (
        f"{emoji} <b>Nightly Grade Report</b>\n\n"
        f"Graded: <b>{graded}</b> bets\n"
        f"Results: <b>{wins}W / {losses}L / {pushes}P</b>\n"
        f"Profit: <b>${profit:+.2f}</b>\n"
        f"All-Time ROI: <b>{roi:+.1f}%</b>\n"
        f"📅 {datetime.now().strftime('%B %d, %Y')}"
    )
