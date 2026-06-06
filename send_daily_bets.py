import sys
import os
import pandas as pd
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
import glob

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

# ================== CENTRAL CONFIG ==================
MIN_EDGE_THRESHOLD = -0.04
EMAIL = "naneksiuol@gmail.com"
APP_PASSWORD = "peri zrba vdnl hyht"
TO_EMAIL = "naneksiuol@gmail.com"
SPORTS = ["MLB", "NBA", "WNBA", "NHL"]
# ===================================================


def get_latest_data_file():
    export_files = glob.glob("attachments/*export*.csv")
    if export_files:
        return max(export_files, key=os.path.getctime)
    return "data/hits_board-1.csv"


def load_data():
    return pd.read_csv(get_latest_data_file())


# ── Design tokens ─────────────────────────────────────────────────────────────

SPORT_META = {
    "MLB": {"icon": "⚾", "gradient": "linear-gradient(135deg,#1a472a 0%,#2d6a4f 100%)", "accent": "#52b788"},
    "NBA": {"icon": "🏀", "gradient": "linear-gradient(135deg,#0a3161 0%,#1d4e8f 100%)", "accent": "#4dabf7"},
    "WNBA":{"icon": "🏀", "gradient": "linear-gradient(135deg,#7b1a1a 0%,#c8102e 100%)", "accent": "#ff8fa3"},
    "NHL": {"icon": "🏒", "gradient": "linear-gradient(135deg,#003087 0%,#0057b8 100%)", "accent": "#74c0fc"},
}

BASE_CSS = """
  body{margin:0;padding:0;background:#0f0f13;font-family:'Segoe UI',Arial,sans-serif;}
  a{color:inherit;text-decoration:none;}
"""


def _edge_badge(edge: float) -> str:
    """Colored pill badge for edge value."""
    pct = f"{edge:+.1%}"
    if edge >= 0.05:
        bg, color = "#1a3a1a", "#52c41a"
        label = f"🔥 {pct}"
    elif edge >= 0.03:
        bg, color = "#1a2e1a", "#73d13d"
        label = f"✅ {pct}"
    elif edge >= 0.01:
        bg, color = "#2e2a10", "#ffc53d"
        label = f"🟡 {pct}"
    elif edge >= 0.0:
        bg, color = "#1e1e1e", "#8c8c8c"
        label = f"⚪ {pct}"
    else:
        bg, color = "#2e1a1a", "#ff4d4f"
        label = f"❌ {pct}"
    return (f'<span style="display:inline-block;padding:2px 10px;border-radius:20px;'
            f'background:{bg};color:{color};font-size:12px;font-weight:700;'
            f'border:1px solid {color}33;white-space:nowrap;">{label}</span>')


def _odds_fmt(odds) -> str:
    try:
        o = int(odds)
        return f"+{o}" if o > 0 else str(o)
    except Exception:
        return str(odds)


def _card(content: str, padding: str = "20px") -> str:
    return (f'<div style="background:#1a1a24;border:1px solid #2a2a3a;border-radius:16px;'
            f'padding:{padding};margin-bottom:16px;">{content}</div>')


def _section_header(title: str, subtitle: str = "") -> str:
    sub = f'<p style="margin:4px 0 0;color:#888;font-size:13px;">{subtitle}</p>' if subtitle else ""
    return (f'<p style="margin:0 0 16px;font-size:18px;font-weight:700;color:#e8e8f0;">'
            f'{title}</p>{sub}')


def _play_row(rank: int, row: dict, prop_label: str = "") -> str:
    edge = row.get("edge", 0) or 0
    player = row.get("player", "")
    team = row.get("team", "")
    line = row.get("line", "")
    odds = _odds_fmt(row.get("over_odds", 0))
    prop = prop_label or row.get("market", "")
    badge = _edge_badge(edge)

    return f"""
    <div style="display:flex;align-items:center;padding:10px 0;
                border-bottom:1px solid #2a2a3a;gap:12px;flex-wrap:wrap;">
      <span style="width:24px;height:24px;background:#2a2a3a;border-radius:50%;
                   display:inline-flex;align-items:center;justify-content:center;
                   color:#aaa;font-size:11px;font-weight:700;flex-shrink:0;">{rank}</span>
      <div style="flex:1;min-width:160px;">
        <span style="color:#e8e8f0;font-weight:700;font-size:14px;">{player}</span>
        <span style="color:#888;font-size:12px;margin-left:8px;">{team}</span>
      </div>
      <span style="color:#aaa;font-size:12px;background:#222232;padding:2px 8px;
                   border-radius:6px;">{prop} O{line}</span>
      <span style="color:#c8c8d8;font-size:13px;font-weight:600;">{odds}</span>
      {badge}
    </div>"""


def _parlay_leg_row(rank: int, leg: dict) -> str:
    edge = leg.get("edge", 0) or 0
    player = leg.get("player", "")
    team = leg.get("team", "")
    line = leg.get("line", "")
    market = leg.get("market", "")
    odds = _odds_fmt(leg.get("over_odds", 0))
    badge = _edge_badge(edge)
    return f"""
    <div style="display:flex;align-items:center;padding:8px 0;
                border-bottom:1px solid #222232;gap:10px;flex-wrap:wrap;">
      <span style="color:#666;font-size:12px;width:16px;text-align:right;">{rank}.</span>
      <div style="flex:1;min-width:140px;">
        <span style="color:#d8d8e8;font-weight:600;font-size:13px;">{player}</span>
        <span style="color:#666;font-size:11px;margin-left:6px;">{team}</span>
      </div>
      <span style="color:#888;font-size:11px;">{market} O{line}</span>
      <span style="color:#b0b0c8;font-size:13px;font-weight:600;">{odds}</span>
      {badge}
    </div>"""


def _payout_hero(american_odds: str, payout: float, stake: float, label: str = "") -> str:
    return f"""
    <div style="background:linear-gradient(135deg,#141420 0%,#1e1e2e 100%);
                border:1px solid #3a3a5a;border-radius:12px;padding:16px 20px;
                margin-bottom:14px;display:flex;align-items:center;gap:20px;flex-wrap:wrap;">
      <div>
        <p style="margin:0;color:#888;font-size:11px;text-transform:uppercase;
                  letter-spacing:1px;">Combined Odds</p>
        <p style="margin:2px 0 0;color:#a78bfa;font-size:28px;font-weight:800;
                  font-variant-numeric:tabular-nums;">{american_odds}</p>
      </div>
      <div style="flex:1;">
        <p style="margin:0;color:#888;font-size:11px;text-transform:uppercase;
                  letter-spacing:1px;">Payout on ${stake:.0f}</p>
        <p style="margin:2px 0 0;color:#34d399;font-size:24px;font-weight:800;">${payout:.2f}</p>
      </div>
      {f'<span style="color:#666;font-size:12px;">{label}</span>' if label else ""}
    </div>"""


# ── Sport section ──────────────────────────────────────────────────────────────

def _sport_section_html(sport: str, df: pd.DataFrame, parlay_report: dict) -> str:
    meta = SPORT_META.get(sport, {"icon": "🎯", "gradient": "linear-gradient(135deg,#1a1a2e,#2a2a4e)", "accent": "#a78bfa"})
    top_plays = parlay_report.get("top10") or df.head(10).to_dict("records")
    parlays   = parlay_report.get("parlays", {})
    sgps      = parlay_report.get("sgps", [])
    pos_games = parlay_report.get("pos_edge_games", 0)

    # ── Sport header ──
    html = f"""
    <div style="margin:32px 0 0;">
      <div style="background:{meta['gradient']};border-radius:20px 20px 0 0;
                  padding:24px 28px 20px;">
        <h2 style="margin:0;color:#fff;font-size:24px;font-weight:800;
                   letter-spacing:-0.5px;">{meta['icon']} {sport}</h2>
        <p style="margin:6px 0 0;color:rgba(255,255,255,0.7);font-size:13px;">
          {len(df)} props &nbsp;·&nbsp; {pos_games} positive-edge game(s) today
        </p>
      </div>
      <div style="background:#13131f;border:1px solid #2a2a3a;border-top:none;
                  border-radius:0 0 20px 20px;padding:24px 28px;">
    """

    # ── Top plays ──
    if top_plays:
        html += _section_header("🏆 Top 10 Edge Candidates",
                                "Best value plays sorted by edge — sweet spot for parlay legs")
        for i, row in enumerate(top_plays[:10], 1):
            html += _play_row(i, row)

    # ── Multi-game parlays ──
    if parlays:
        html += f'<div style="margin-top:28px;">'
        html += _section_header("🎰 Multi-Game Parlays",
                                "Legs from different games — independence maximised")
        for n in [2, 3, 4, 5]:
            key = f"{n}_leg"
            if key not in parlays:
                continue
            p    = parlays[key]
            pout = p["payout"]
            html += f'<p style="margin:18px 0 8px;color:{meta["accent"]};font-size:15px;font-weight:700;">{n}-Leg Parlay</p>'
            html += _payout_hero(pout["american_odds"], pout["payout"], pout["stake"])
            for j, leg in enumerate(p["legs"], 1):
                html += _parlay_leg_row(j, leg)
        html += '</div>'

    # ── SGPs ──
    if sgps:
        html += f'<div style="margin-top:28px;">'
        html += _section_header("🔗 Same-Game Parlays",
                                "Correlation-adjusted SGPs — copula penalty applied")
        for i, sgp in enumerate(sgps, 1):
            pout    = sgp["payout"]
            ev      = sgp.get("combined_ev", 0) or 0
            pen     = sgp.get("independence_penalty", 1.0) or 1.0
            quality = "🔥 Strong" if ev > 0.04 else ("✅ Good" if ev > 0.02 else "🟡 Marginal")
            html += f"""
            <div style="background:#0f0f1a;border:1px solid #2a2a3a;border-radius:14px;
                        padding:16px 20px;margin-bottom:16px;">
              <div style="display:flex;align-items:center;justify-content:space-between;
                          flex-wrap:wrap;gap:8px;margin-bottom:12px;">
                <div>
                  <span style="color:#c8c8d8;font-weight:700;font-size:14px;">{sgp['game']}</span>
                  <span style="margin-left:10px;color:#888;font-size:12px;">{quality}</span>
                </div>
                <span style="color:#888;font-size:12px;">
                  EV {ev*100:+.2f}% &nbsp;·&nbsp; Corr {pen:.0%}
                </span>
              </div>
            """
            html += _payout_hero(pout["american_odds"], pout["payout"], pout["stake"])
            for j, leg in enumerate(sgp["legs"], 1):
                html += _parlay_leg_row(j, leg)
            html += '</div>'
        html += '</div>'

    html += '</div></div>'  # close inner + outer
    return html


# ── Full multi-sport email ────────────────────────────────────────────────────

def generate_all_sports_slip(sports_data: dict = None) -> str:
    if sports_data is None:
        sports_data = _scrape_all_sports()

    date_str = datetime.now().strftime("%B %d, %Y")
    day_str  = datetime.now().strftime("%A")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Sports Betting Plus — {date_str}</title>
  <style>{BASE_CSS}</style>
</head>
<body style="background:#0f0f13;margin:0;padding:0;">
<div style="max-width:680px;margin:0 auto;padding:24px 16px 48px;">

  <!-- Header -->
  <div style="text-align:center;padding:40px 24px 32px;">
    <div style="display:inline-block;background:linear-gradient(135deg,#7c3aed,#4f46e5);
                border-radius:16px;padding:12px 20px;margin-bottom:20px;">
      <span style="color:#fff;font-size:22px;font-weight:900;letter-spacing:-0.5px;">
        Sports Betting+
      </span>
    </div>
    <h1 style="margin:0;color:#e8e8f0;font-size:28px;font-weight:800;letter-spacing:-1px;">
      Daily Slip
    </h1>
    <p style="margin:8px 0 0;color:#666;font-size:14px;">
      {day_str}, {date_str}
    </p>
  </div>

  <!-- Summary bar -->
"""

    # Count total parlays and SGPs across all sports
    total_parlays = sum(len(d.get("report", {}).get("parlays", {})) for d in sports_data.values())
    total_sgps    = sum(len(d.get("report", {}).get("sgps", [])) for d in sports_data.values())
    active_sports = sum(1 for d in sports_data.values() if d.get("df") is not None and not d["df"].empty)

    html += f"""
  <div style="display:flex;gap:12px;margin-bottom:28px;flex-wrap:wrap;">
    {"".join([_stat_chip(str(active_sports), "Sports Active"),
              _stat_chip(str(total_parlays), "Parlays Built"),
              _stat_chip(str(total_sgps),    "SGPs Built")])}
  </div>
"""

    # Sport sections
    for sport, data in sports_data.items():
        df     = data.get("df")
        report = data.get("report", {})
        if df is None or df.empty:
            html += f"""
  <div style="background:#1a1a24;border:1px solid #2a2a3a;border-radius:20px;
              padding:24px 28px;margin:24px 0;text-align:center;">
    <p style="color:#555;margin:0;font-size:14px;">
      {SPORT_META.get(sport,{}).get('icon','🎯')} {sport} — No data available today
    </p>
  </div>"""
            continue
        html += _sport_section_html(sport, df, report)

    # Footer
    html += f"""
  <!-- Footer -->
  <div style="text-align:center;padding:32px 0 0;border-top:1px solid #1a1a24;margin-top:32px;">
    <p style="color:#333;font-size:12px;margin:0 0 6px;">
      Sports Betting Plus &nbsp;·&nbsp; {date_str}
    </p>
    <p style="color:#262630;font-size:11px;margin:0;">
      Always bet responsibly. Past performance does not guarantee future results.
    </p>
  </div>

</div>
</body>
</html>"""
    return html


def _stat_chip(value: str, label: str) -> str:
    return f"""
    <div style="flex:1;min-width:120px;background:#1a1a24;border:1px solid #2a2a3a;
                border-radius:14px;padding:14px 16px;text-align:center;">
      <p style="margin:0;color:#a78bfa;font-size:24px;font-weight:800;">{value}</p>
      <p style="margin:4px 0 0;color:#666;font-size:11px;text-transform:uppercase;
                letter-spacing:1px;">{label}</p>
    </div>"""


# ── Single-sport legacy slip ──────────────────────────────────────────────────

def generate_betting_slip(df: pd.DataFrame = None, parlay_report: dict = None) -> str:
    """Legacy single-sport slip. Wraps generate_all_sports_slip with one sport."""
    if df is None:
        return generate_all_sports_slip()
    sport = "MLB"
    pr = parlay_report or {}
    sports_data = {"": {"df": df, "report": pr}}
    return generate_all_sports_slip(sports_data)


# ── Data fetching ─────────────────────────────────────────────────────────────

def _scrape_all_sports() -> dict:
    from scraper import scrape_props
    from parlay_builder import build_parlay_report

    sports_data = {}
    for sport in SPORTS:
        try:
            df = scrape_props(sport)
            if df.empty:
                sports_data[sport] = {"df": df, "report": {}}
                continue
            filtered = df[df["edge"] >= MIN_EDGE_THRESHOLD].copy()
            report   = build_parlay_report(filtered, full_df=df)
            sports_data[sport] = {"df": filtered, "report": report}
        except Exception as e:
            print(f"Warning: could not load {sport}: {e}")
            sports_data[sport] = {"df": pd.DataFrame(), "report": {}}
    return sports_data


# ── Sending ───────────────────────────────────────────────────────────────────

def send_email(
    df: pd.DataFrame = None,
    parlay_report: dict = None,
    extra_recipients: list = None,
    all_sports: bool = False,
    sports_data: dict = None,
):
    if all_sports or sports_data is not None:
        if sports_data is None:
            sports_data = _scrape_all_sports()
        html_content = generate_all_sports_slip(sports_data)
    else:
        if df is None:
            raw = load_data()
            raw["edge"] = raw["fair_est"] - raw["book_implied"]
            df = raw[raw["edge"] >= MIN_EDGE_THRESHOLD].sort_values("over_odds", ascending=False)
        if parlay_report is None:
            from parlay_builder import build_parlay_report
            parlay_report = build_parlay_report(df)
        html_content = generate_betting_slip(df, parlay_report)

    from subscribers import load_subscribers
    all_recipients = list({TO_EMAIL} | set(load_subscribers()) | set(extra_recipients or []))
    subject = f"🎯 Sports Betting Plus — Daily Slip {datetime.now().strftime('%B %d, %Y')}"

    results = {"sent": [], "failed": []}
    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(EMAIL, APP_PASSWORD)
        for recipient in all_recipients:
            try:
                msg = MIMEMultipart("alternative")
                msg["From"]    = EMAIL
                msg["To"]      = recipient
                msg["Subject"] = subject
                msg.attach(MIMEText(html_content, "html"))
                server.send_message(msg)
                results["sent"].append(recipient)
            except Exception as e:
                results["failed"].append((recipient, str(e)))
        server.quit()
    except Exception as e:
        raise RuntimeError(f"SMTP connection failed: {e}")

    return results


if __name__ == "__main__":
    print("Scraping all sports and sending email...")
    results = send_email(all_sports=True)
    print(f"Sent to: {results['sent']}")
    if results["failed"]:
        print(f"Failed: {results['failed']}")
