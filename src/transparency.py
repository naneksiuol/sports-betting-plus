"""
Public transparency page — PropLens's core trust signal.

Shows the complete graded record (W-L, ROI, profit), CLV record, and
calibration quality (Brier score + reliability plot). Accessible without
login via ?page=transparency.
"""

import streamlit as st


def render_transparency():
    st.markdown("""
    <div style="text-align:center;padding:1.5rem 1rem 0.5rem;">
      <h1 style="font-weight:900;letter-spacing:-0.02em;margin-bottom:0.3rem;">📊 Transparency</h1>
      <p style="color:#94a3b8;max-width:640px;margin:0 auto;line-height:1.6;">
        Every pick we publish is graded, every closing line is recorded, and the
        complete record lives on this page — wins, losses, and all. We don't sell
        picks; we show you a calibrated view of the props market and let the
        numbers speak.
      </p>
    </div>
    """, unsafe_allow_html=True)
    st.divider()

    # ── Record & ROI ──────────────────────────────────────────────────────────
    try:
        from bet_tracker import get_stats
        stats = get_stats()
    except Exception:
        stats = {}

    wins   = stats.get("wins", 0)
    losses = stats.get("losses", 0)
    roi    = stats.get("roi", 0.0)
    profit = stats.get("total_profit", 0.0)
    avg_clv = stats.get("avg_clv")

    st.markdown("### 🧾 The Complete Record")
    st.caption("All system picks since inception — graded nightly, never trimmed.")
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Record", f"{wins}W – {losses}L")
    k2.metric("ROI (flat stakes)", f"{roi:+.1f}%")
    k3.metric("Net Profit", f"${profit:+,.2f}")
    k4.metric("Avg CLV", f"{avg_clv:+.2f}%" if avg_clv is not None else "—",
              help="Closing Line Value: how much better our published price was than "
                   "the market's closing price. Positive CLV over time is the strongest "
                   "evidence a model beats the market, independent of short-term variance.")

    by_sport = stats.get("by_sport") or {}
    if by_sport:
        import pandas as pd
        rows = [{"Sport": s,
                 "Record": f"{v.get('wins',0)}W–{v.get('losses',0)}L",
                 "Profit": f"${v.get('profit',0):+,.2f}",
                 "ROI": f"{v.get('roi',0):+.1f}%"}
                for s, v in sorted(by_sport.items())]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    st.divider()

    # ── Calibration ───────────────────────────────────────────────────────────
    st.markdown("### 🎯 Model Calibration")
    st.caption("When we say 60%, does it hit 60% of the time? This section answers that.")

    try:
        from calibration import calibration_status
        cal = calibration_status()
    except Exception:
        cal = {}

    c1, c2, c3, c4 = st.columns(4)
    brier = cal.get("brier_score")
    c1.metric("Brier Score", f"{brier:.4f}" if brier else "—",
              help="Mean squared error of our probabilities vs. outcomes. "
                   "Lower is better; 0.25 = coin-flip guessing, below 0.20 is skillful.")
    c2.metric("Method", (cal.get("method") or "—").title())
    c3.metric("Graded Samples", f"{cal.get('n_graded', 0):,}")
    _trained = (cal.get("trained_at") or "")[:10]
    c4.metric("Last Retrained", _trained or "—")

    reliability = cal.get("reliability") or {}
    mean_pred = reliability.get("mean_pred") or []
    frac_pos  = reliability.get("frac_pos") or []
    if mean_pred and frac_pos:
        import plotly.graph_objects as go
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=[0, 1], y=[0, 1], mode="lines",
                                 name="Perfect calibration",
                                 line=dict(color="#475569", dash="dash")))
        fig.add_trace(go.Scatter(x=mean_pred, y=frac_pos, mode="lines+markers",
                                 name="Our model",
                                 line=dict(color="#2DD4BF", width=3),
                                 marker=dict(size=9)))
        fig.update_layout(
            title="Reliability Diagram — predicted probability vs. actual hit rate",
            xaxis_title="Predicted probability",
            yaxis_title="Actual hit rate",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="#13131f",
            font_color="#94a3b8",
            legend=dict(orientation="h", y=1.12),
            height=420,
            xaxis=dict(range=[0, 1], gridcolor="#2a2a3a"),
            yaxis=dict(range=[0, 1], gridcolor="#2a2a3a"),
        )
        st.plotly_chart(fig, use_container_width=True)
        st.caption("Points on the dashed line mean our stated probabilities match reality. "
                   "Points below it mean we were overconfident in that range; above it, underconfident.")
    else:
        st.info("Calibration plot will appear once the calibrator has enough graded bets.")

    st.divider()

    # ── Methodology ───────────────────────────────────────────────────────────
    st.markdown("### 🔬 How the Numbers Are Made")
    st.markdown("""
- **Fair probabilities** come from de-vigging consensus and sharp opening lines
  (power method, with Shin as a cross-check) across 8+ sportsbooks — not from our opinion.
- **Edges** are the gap between our fair probability and the best available
  FanDuel/DraftKings price at publication time, timestamped in our daily slips.
- **Calibration** is retrained nightly on every graded bet using Platt scaling or
  isotonic regression (chosen by sample size). The Brier score and reliability plot
  above are computed on that full history.
- **CLV** is recorded against the closing line for every published play. We treat
  long-run CLV — not short-term win rate — as the primary health metric.
- **Grading** runs automatically every night. Results are never edited or removed.
    """)

    st.divider()
    st.markdown("""
    <div style="text-align:center;color:#475569;font-size:0.78rem;padding-bottom:1.5rem;">
      For informational and entertainment purposes only. Not betting advice —
      past performance does not guarantee future results. 21+ only.
      Sports betting is not legal in all states; void where prohibited.<br>
      Gambling problem? Call or text <b>1-800-GAMBLER</b>.
    </div>
    """, unsafe_allow_html=True)
