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
# ===================================================


def get_latest_data_file():
    export_files = glob.glob("attachments/*export*.csv")
    if export_files:
        return max(export_files, key=os.path.getctime)
    return "data/hits_board-1.csv"


def load_data():
    return pd.read_csv(get_latest_data_file())


def generate_betting_slip(df: pd.DataFrame, parlay_report: dict = None) -> str:
    # Use parlay builder's top 10 sweet-spot candidates if available, else fall back to df
    if parlay_report and parlay_report.get("top10"):
        top_plays = parlay_report["top10"]  # list of dicts
        use_parlay_top = True
    else:
        top_plays = df.head(10).to_dict("records")
        use_parlay_top = False

    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 700px; margin: auto;">
    <h2 style="color:#1a1a2e;">🎯 Sports Betting Plus — Daily Slip</h2>
    <p><strong>Date:</strong> {datetime.now().strftime('%B %d, %Y')}</p>

    <h3 style="color:#1a1a2e;">🏆 Top 10 Best-Odds Candidates
        <span style="font-size:0.85rem;color:#666;">(-100 to -200 sweet spot)</span>
    </h3>
    <p style="color:#555;font-size:0.9rem;">Best odds first. Avoid stacking -250+ legs — they kill parlay value.</p>
    <table border="1" cellpadding="8" cellspacing="0" style="border-collapse:collapse;width:100%;">
        <tr style="background-color:#1a1a2e;color:white;">
            <th>#</th><th>Player</th><th>Prop</th><th>Line</th><th>Game</th><th>Odds</th><th>Edge</th>
        </tr>
    """

    for i, row in enumerate(top_plays, 1):
        edge = row.get('edge', 0) or 0
        edge_color = "#4CAF50" if edge > 0 else "#f44336"
        prop_label = row.get('market', row.get('prop', ''))
        html += f"""
        <tr style="background-color:{'#f9f9f9' if i % 2 == 0 else 'white'};">
            <td style="text-align:center;"><strong>{i}</strong></td>
            <td><strong>{row.get('player','')}</strong></td>
            <td style="font-size:0.85rem;color:#555;">{prop_label}</td>
            <td style="text-align:center;">O{row.get('line','')}</td>
            <td style="font-size:0.85rem;">{row.get('team', '')}</td>
            <td style="text-align:center;"><strong>{int(row.get('over_odds', 0))}</strong></td>
            <td style="text-align:center;color:{edge_color};font-weight:bold;">{edge:.1%}</td>
        </tr>
        """

    html += "</table><br>"

    # ── Parlay section ──
    if parlay_report:
        html += """<hr style="border:1px solid #ddd;">
        <h3 style="color:#1a1a2e;">🎰 Today's Parlay Picks</h3>
        <p style="color:#555;font-size:0.9rem;">All legs from different games to avoid correlated losses.</p>
        """

        for n in [3, 4, 5]:
            key = f"{n}_leg"
            if key in parlay_report.get("parlays", {}):
                p = parlay_report["parlays"][key]
                pout = p["payout"]
                html += f"""
                <h4 style="color:#16213e;margin-bottom:4px;">📋 {n}-Leg Parlay &nbsp;
                    <span style="color:#4CAF50;font-size:1rem;">{pout['american_odds']} odds
                    &nbsp;→&nbsp; ${pout['payout']:.2f} on ${pout['stake']:.0f}</span>
                </h4>
                <table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;width:100%;margin-bottom:12px;">
                    <tr style="background-color:#e8f5e9;">
                        <th>#</th><th>Player</th><th>Prop</th><th>Line</th><th>Game</th><th>Odds</th>
                    </tr>
                """
                for j, leg in enumerate(p["legs"], 1):
                    html += f"""
                    <tr>
                        <td style="text-align:center;">{j}</td>
                        <td><strong>{leg['player']}</strong></td>
                        <td style="font-size:0.85rem;color:#555;">{leg.get('market', '')}</td>
                        <td style="text-align:center;">O{leg.get('line', '')}</td>
                        <td style="font-size:0.85rem;">{leg['team']}</td>
                        <td style="text-align:center;">{int(leg['over_odds'])}</td>
                    </tr>
                    """
                html += "</table>"

        # SGPs
        if parlay_report.get("sgps"):
            html += """<hr style="border:1px solid #ddd;">
            <h3 style="color:#1a1a2e;">🔗 Same-Game Parlays (SGPs)</h3>
            <p style="color:#555;font-size:0.9rem;">Books often boost SGP payouts. 2-3 players from the same game.</p>
            """
            for i, sgp in enumerate(parlay_report["sgps"], 1):
                pout = sgp["payout"]
                html += f"""
                <h4 style="color:#16213e;margin-bottom:4px;">SGP {i}: {sgp['game']} &nbsp;
                    <span style="color:#4CAF50;">{pout['american_odds']} odds
                    &nbsp;→&nbsp; ${pout['payout']:.2f} on ${pout['stake']:.0f}</span>
                </h4>
                <table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;width:100%;margin-bottom:12px;">
                    <tr style="background-color:#e3f2fd;">
                        <th>#</th><th>Player</th><th>Prop</th><th>Line</th><th>Odds</th>
                    </tr>
                """
                for j, leg in enumerate(sgp["legs"], 1):
                    html += f"""
                    <tr>
                        <td style="text-align:center;">{j}</td>
                        <td><strong>{leg['player']}</strong></td>
                        <td style="font-size:0.85rem;color:#555;">{leg.get('market', '')}</td>
                        <td style="text-align:center;">O{leg.get('line', '')}</td>
                        <td style="text-align:center;">{int(leg['over_odds'])}</td>
                    </tr>
                    """
                html += "</table>"

    html += """
    <hr style="border:1px solid #ddd;">
    <p style="color:#999;font-size:0.8rem;">
        Sports Betting Plus · Always bet responsibly · Past performance does not guarantee future results.
    </p>
    </div>
    """
    return html


def send_email(df: pd.DataFrame = None, parlay_report: dict = None, extra_recipients: list[str] = None):
    if df is None:
        raw = load_data()
        raw['edge'] = raw['fair_est'] - raw['book_implied']
        df = raw[raw['edge'] >= MIN_EDGE_THRESHOLD].sort_values('over_odds', ascending=False)

    if parlay_report is None:
        from parlay_builder import build_parlay_report
        parlay_report = build_parlay_report(df)

    # Build recipient list: owner + subscribers
    from subscribers import load_subscribers
    all_recipients = list({TO_EMAIL} | set(load_subscribers()) | set(extra_recipients or []))

    html_content = generate_betting_slip(df, parlay_report)
    subject = f"🎯 Sports Betting Plus — Daily Slip {datetime.now().strftime('%B %d, %Y')}"

    results = {"sent": [], "failed": []}
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(EMAIL, APP_PASSWORD)

        for recipient in all_recipients:
            try:
                msg = MIMEMultipart()
                msg['From'] = EMAIL
                msg['To'] = recipient
                msg['Subject'] = subject
                msg.attach(MIMEText(html_content, 'html'))
                server.send_message(msg)
                results["sent"].append(recipient)
            except Exception as e:
                results["failed"].append((recipient, str(e)))

        server.quit()
    except Exception as e:
        raise RuntimeError(f"SMTP connection failed: {e}")

    return results


if __name__ == "__main__":
    send_email()
