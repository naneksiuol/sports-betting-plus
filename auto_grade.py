"""
Standalone script for Windows Task Scheduler.
Runs at 2 AM Central to grade yesterday's pending bets.
"""
import sys
import os
import json
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass


def send_grade_report(summary: dict, stats: dict):
    """Email the grading summary to the owner."""
    EMAIL = os.environ.get("EMAIL_FROM", "naneksiuol@gmail.com")
    APP_PASSWORD = os.environ.get("EMAIL_APP_PASSWORD", "")
    TO_EMAIL = os.environ.get("EMAIL_TO", "naneksiuol@gmail.com")

    wins = stats.get("wins", 0)
    losses = stats.get("losses", 0)
    roi = stats.get("roi", 0)
    profit = stats.get("total_profit", 0)
    win_rate = stats.get("win_rate", 0)

    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: auto;">
    <h2 style="color:#1a1a2e;">📊 Sports Betting Plus — Nightly Grade Report</h2>
    <p><strong>Date graded:</strong> {summary.get('date')}</p>
    <p><strong>Bets graded:</strong> {summary.get('graded')} &nbsp;|&nbsp;
       <strong>Skipped:</strong> {summary.get('skipped')}</p>

    <h3 style="color:#1a1a2e;">📈 Overall Tracker Stats</h3>
    <table border="1" cellpadding="8" cellspacing="0" style="border-collapse:collapse;width:100%;">
        <tr style="background-color:#1a1a2e;color:white;">
            <th>Wins</th><th>Losses</th><th>Win Rate</th><th>Profit</th><th>ROI</th>
        </tr>
        <tr style="text-align:center;">
            <td style="color:#4CAF50;font-weight:bold;">{wins}</td>
            <td style="color:#f44336;font-weight:bold;">{losses}</td>
            <td>{win_rate:.1f}%</td>
            <td style="color:{'#4CAF50' if profit >= 0 else '#f44336'};font-weight:bold;">${profit:+.2f}</td>
            <td style="color:{'#4CAF50' if roi >= 0 else '#f44336'};font-weight:bold;">{roi:+.1f}%</td>
        </tr>
    </table>
    """

    if summary.get("skipped_details"):
        html += "<h4>⚠️ Could not grade:</h4><ul>"
        for s in summary["skipped_details"]:
            html += f"<li>{s}</li>"
        html += "</ul>"

    html += """
    <hr style="border:1px solid #ddd;">
    <p style="color:#999;font-size:0.8rem;">Sports Betting Plus · Auto-graded at 2 AM Central</p>
    </div>
    """

    try:
        msg = MIMEMultipart()
        msg["From"] = EMAIL
        msg["To"] = TO_EMAIL
        msg["Subject"] = f"📊 Nightly Grade Report — {summary.get('date')} ({summary.get('graded')} bets graded)"
        msg.attach(MIMEText(html, "html"))
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(EMAIL, APP_PASSWORD)
        server.send_message(msg)
        server.quit()
        print("✅ Grade report emailed.")
    except Exception as e:
        print(f"⚠️ Could not send email: {e}")


if __name__ == "__main__":
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Auto-grader started (2 AM Central run)")

    from result_grader import grade_pending_bets
    from bet_tracker import get_stats

    summary = grade_pending_bets()
    stats = get_stats()

    print(f"\n[Stats] {stats['wins']}W / {stats['losses']}L | ROI: {stats['roi']:+.1f}%")

    # Email report
    send_grade_report(summary, stats)

    # Push nightly report to Discord + Telegram
    try:
        from bet_tracker import load_bets
        from datetime import date, timedelta
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        last_bets = [b for b in load_bets()
                     if b.get("date") == yesterday and b["result"] in ("win","loss","push")]
        wins_n = sum(1 for b in last_bets if b["result"] == "win")
        losses_n = sum(1 for b in last_bets if b["result"] == "loss")
        pushes_n = sum(1 for b in last_bets if b["result"] == "push")
        graded = summary.get("graded", 0)

        from discord_bot import is_configured as dc_ok, send_grade_report as dc_grade
        if dc_ok():
            dc_grade(graded, wins_n, losses_n, pushes_n, stats["roi"], stats["total_profit"])
            print("Discord nightly report sent.")

        from telegram_bot import is_configured as tg_ok, broadcast, fmt_grade_report
        if tg_ok():
            msg = fmt_grade_report(graded, wins_n, losses_n, pushes_n,
                                   stats["roi"], stats["total_profit"])
            broadcast(msg)
            print("Telegram nightly report sent.")
    except Exception as e:
        print(f"Push report error: {e}")

    print("Auto-grade complete.")
