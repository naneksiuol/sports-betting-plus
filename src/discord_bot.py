"""
Discord webhook notifications for Sports Betting Plus.
No bot account needed — just a webhook URL from any Discord channel.

Setup (60 seconds):
  1. Open Discord → your server → any channel
  2. Click the gear (Edit Channel) → Integrations → Webhooks → New Webhook
  3. Copy the webhook URL
  4. Add to .env:  DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
"""

import os
import requests
from datetime import datetime, timezone
from pathlib import Path

_ENV_FILE = Path(__file__).parent.parent / ".env"


def _load_env():
    """Load .env file — tries python-dotenv first, falls back to manual parse."""
    try:
        from dotenv import load_dotenv
        load_dotenv(_ENV_FILE, override=True)
        return
    except ImportError:
        pass
    # Manual fallback: parse KEY=VALUE lines directly into os.environ
    if _ENV_FILE.exists():
        for line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                os.environ.setdefault(key.strip(), val.strip())


_load_env()


def get_webhook_url() -> str:
    return os.environ.get("DISCORD_WEBHOOK_URL", "")


def is_configured() -> bool:
    return bool(get_webhook_url())


def send(content: str = "", embeds: list = None) -> bool:
    url = get_webhook_url()
    if not url:
        return False
    try:
        payload = {}
        if content:
            payload["content"] = content
        if embeds:
            payload["embeds"] = embeds
        resp = requests.post(url, json=payload, timeout=10)
        return resp.status_code in (200, 204)
    except Exception:
        return False


# ── Message formatters ────────────────────────────────────────────────────────

def send_daily_slip(picks: list[dict], parlays: dict = None,
                    record: dict = None, sport: str = "MLB",
                    clv_avg: float = None) -> bool:
    today = datetime.now().strftime("%B %d, %Y")
    embeds = []

    # ── Quality filter ──
    # Primary: edge >= 0.03 OR confidence >= 65
    filtered = [
        p for p in picks
        if p.get("edge", 0) >= 0.03 or p.get("confidence", 0) >= 65
    ]
    filter_threshold = 0.03
    # Fallback: if fewer than 3 pass, lower threshold to edge >= 0.01
    if len(filtered) < 3:
        filtered = [p for p in picks if p.get("edge", 0) >= 0.01]
        filter_threshold = 0.01
    # Last resort: use all picks so Discord slip is never silently empty
    if not filtered:
        filtered = picks

    # ── Embed 1: Top picks ──
    record_str = ""
    if record:
        record_str = f"**Record:** {record.get('wins',0)}W-{record.get('losses',0)}L | **ROI:** {record.get('roi',0):+.1f}%\n\n"

    # Select top 5 per unique prop/market, up to 20 total, sorted by edge descending
    from collections import defaultdict
    _by_market = defaultdict(list)
    for p in sorted(filtered, key=lambda x: x.get("edge", 0), reverse=True):
        _market = p.get("prop_label", p.get("market", "other"))
        if len(_by_market[_market]) < 5:
            _by_market[_market].append(p)
    # Flatten and re-sort by edge, cap at 20
    _top20 = sorted(
        [p for group in _by_market.values() for p in group],
        key=lambda x: x.get("edge", 0), reverse=True
    )[:20]

    picks_lines = []
    for i, p in enumerate(_top20, 1):
        odds = int(p.get("over_odds", 0))
        odds_str = f"+{odds}" if odds > 0 else str(odds)
        edge = p.get("edge", 0)
        label = p.get("prop_label", p.get("market", ""))
        picks_lines.append(
            f"`{i:02d}.` **{p['player']}** — {label} O{p.get('line',0.5)} | {odds_str} | Edge: {edge:+.1%}"
        )

    embeds.append({
        "title": f"🎯 Sports Betting Plus — {sport} Daily Slip",
        "description": f"📅 {today}\n\n{record_str}**🏆 Top 20 Best Edge Candidates (Top 5 per Prop)**\n\n" + "\n".join(picks_lines),
        "color": 0x00FF88,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    # ── Embeds 2+: One per parlay ──
    if parlays:
        for key, parlay in parlays.items():
            pout = parlay.get("payout", {})
            n_label = key.replace("_leg", "-Leg").replace("_", " ").title()
            leg_lines = []
            for j, leg in enumerate(parlay.get("legs", []), 1):
                lo = int(leg.get("over_odds", 0))
                lo_str = f"+{lo}" if lo > 0 else str(lo)
                lbl = leg.get("prop_label", leg.get("market", ""))
                leg_lines.append(f"`{j}.` **{leg['player']}** — {lbl} O{leg.get('line','')} ({lo_str})\n    {leg.get('team','')}")

            embeds.append({
                "title": f"🎰 {n_label} Parlay — {pout.get('american_odds','?')} odds",
                "description": (
                    f"**Payout:** ${pout.get('payout',0):.2f} on ${pout.get('stake',10):.0f}\n\n"
                    + "\n".join(leg_lines)
                ),
                "color": 0xFFD700,
            })

    # Discord allows max 10 embeds per message
    embeds = embeds[:10]
    # Build footer with filter note and optional CLV credibility signal
    threshold_pct = int(filter_threshold * 100)
    footer_parts = [f"Filtered to edge ≥ {threshold_pct}% | {len(_top20)} plays"]
    if clv_avg is not None:
        footer_parts.append(f"System CLV avg: {clv_avg:+.1%}")
    footer_parts.append("Sports Betting Plus • Bet responsibly")
    embeds[-1]["footer"] = {"text" : " • ".join(footer_parts)}
    return send(embeds=embeds)


def send_steam_alert(player: str, market: str, prev_odds: int,
                     curr_odds: int, diff: int) -> bool:
    direction = "improved" if diff > 0 else "moved shorter"
    embed = {
        "title": "🔥 STEAM ALERT — Sharp Money Detected",
        "description": (
            f"**{player}** — {market}\n\n"
            f"Line {direction}: **{prev_odds:+d} → {curr_odds:+d}** ({diff:+d})\n"
            f"⚡ Multiple books moving — sharp action likely"
        ),
        "color": 0xFF4500,
        "footer": {"text": f"Sports Betting Plus • {datetime.now().strftime('%I:%M %p CT')}"},
    }
    return send(embeds=[embed])


def send_grade_report(graded: int, wins: int, losses: int,
                      pushes: int, roi: float, profit: float) -> bool:
    color = 0x00FF88 if profit >= 0 else 0xFF4444
    emoji = "📈" if profit >= 0 else "📉"
    embed = {
        "title": f"{emoji} Nightly Grade Report",
        "description": (
            f"**Graded:** {graded} bets\n"
            f"**Tonight:** {wins}W / {losses}L / {pushes}P\n"
            f"**Profit:** ${profit:+.2f}\n"
            f"**All-Time ROI:** {roi:+.1f}%"
        ),
        "color": color,
        "footer": {"text": f"Sports Betting Plus • {datetime.now().strftime('%B %d, %Y')}"},
    }
    return send(embeds=[embed])


def send_retrain_summary(summary: dict) -> bool:
    """
    Send a Discord embed summarising a completed retrain run.

    summary shape (from train_models.py):
        {
            "timestamp": str,
            "model":      {before_accuracy, after_accuracy, before_cv_auc,
                           after_cv_auc, n_samples, status},
            "calibrator": {before_brier, after_brier, method, n_trained, status},
        }
    """
    if not is_configured():
        return False

    model = summary.get("model", {})
    cal   = summary.get("calibrator", {})
    ts    = summary.get("timestamp", datetime.now(timezone.utc).isoformat())

    def _fmt(val, fmt=".4f"):
        return f"{val:{fmt}}" if val is not None else "n/a"

    def _arrow(before, after, fmt=".4f", higher_is_better=True):
        if before is None and after is None:
            return "n/a"
        b = f"{before:{fmt}}" if before is not None else "n/a"
        a = f"{after:{fmt}}"  if after  is not None else "n/a"
        if before is not None and after is not None:
            delta = after - before
            if higher_is_better:
                emoji = "📈" if delta > 0.001 else ("📉" if delta < -0.001 else "➡️")
            else:
                emoji = "📈" if delta < -0.001 else ("📉" if delta > 0.001 else "➡️")
            return f"{b} → {a} {emoji}"
        return f"{b} → {a}"

    model_status = model.get("status", "unknown")
    cal_status   = cal.get("status", "unknown")

    # Overall color: green if both ok, yellow if one insufficient, red if error
    statuses = {model_status, cal_status}
    if "error" in statuses:
        color = 0xFF4444
    elif statuses <= {"ok", "insufficient_data"}:
        color = 0x00FF88 if "ok" in statuses else 0xFFD700
    else:
        color = 0xFFD700

    model_lines = [
        f"**Status:** {model_status}",
        f"**Accuracy:** {_arrow(model.get('before_accuracy'), model.get('after_accuracy'))}",
        f"**CV AUC:**   {_arrow(model.get('before_cv_auc'),   model.get('after_cv_auc'))}",
        f"**Samples:**  {model.get('n_samples', 0)}",
    ]
    cal_lines = [
        f"**Status:** {cal_status}",
        f"**Brier:** {_arrow(cal.get('before_brier'), cal.get('after_brier'), higher_is_better=False)}",
        f"**Method:** {cal.get('method') or 'n/a'}",
        f"**Samples:** {cal.get('n_trained', 0)}",
    ]

    embed = {
        "title": "🤖 Model Retrain Complete",
        "color": color,
        "timestamp": ts,
        "fields": [
            {
                "name": "📊 Prop Model (LightGBM)",
                "value": "\n".join(model_lines),
                "inline": True,
            },
            {
                "name": "🎯 Calibrator",
                "value": "\n".join(cal_lines),
                "inline": True,
            },
        ],
        "footer": {"text": "Sports Betting Plus • Auto-Retrain Pipeline"},
    }
    return send(embeds=[embed])


def send_pick_alert(player: str, prop: str, line: float, over_odds: int,
                    edge: float, kelly_stake: float, sport: str = "MLB",
                    is_steam: bool = False) -> bool:
    odds_str = f"+{over_odds}" if over_odds > 0 else str(over_odds)
    edge_emoji = "🔥" if edge >= 0.05 else ("✅" if edge >= 0.03 else "🟡")
    steam_prefix = "🔥 **STEAM + " if is_steam else ""

    embed = {
        "title": f"{steam_prefix}{edge_emoji} Value Alert — {sport}",
        "description": (
            f"**{player}**\n"
            f"📋 {prop} O{line}\n"
            f"💰 Odds: **{odds_str}**\n"
            f"📊 Edge: **{edge:+.1%}**\n"
            f"🏦 Kelly Stake: **${kelly_stake:.2f}**"
        ),
        "color": 0x00FF88 if edge >= 0.03 else 0xFFD700,
        "footer": {"text": f"Sports Betting Plus • {datetime.now().strftime('%I:%M %p CT')}"},
    }
    return send(embeds=[embed])
