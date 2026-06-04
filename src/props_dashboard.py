import os
import sys
from pathlib import Path

# Load .env if present (local dev)
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

# Inject Streamlit secrets into env so modules can use os.environ
try:
    import streamlit as _st_tmp
    for k, v in _st_tmp.secrets.items():
        os.environ.setdefault(k, str(v))
except Exception:
    pass

# Ensure src/ is on path when running from project root
sys.path.insert(0, str(Path(__file__).parent))

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path

# Load API keys from env (set via Streamlit secrets or shell env)
ODDS_API_KEY = os.environ.get("ODDS_API_KEY", "")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

st.set_page_config(
    page_title="Sports Betting Plus | MLB Props",
    page_icon="⚾",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .main-header {font-size: 2.5rem; font-weight: 700; color: #1a1a2e;}
    .metric-card {background-color: #f8f9fa; padding: 1rem; border-radius: 10px;}
    .value-positive {color: #28a745; font-weight: bold;}
    .value-negative {color: #dc3545;}
    .ai-box {background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
             color: #e0e0e0; padding: 1.2rem; border-radius: 12px;
             border-left: 4px solid #4ecca3; font-size: 0.95rem; line-height: 1.6;}
</style>
""", unsafe_allow_html=True)


# ── Data loading ──────────────────────────────────────────────────────────────

@st.cache_data(ttl=300, show_spinner="Fetching live odds...")
def load_live_data() -> pd.DataFrame:
    from odds_client import get_mlb_hits_props
    return get_mlb_hits_props()


@st.cache_data(ttl=3600)
def load_static_data() -> pd.DataFrame:
    data_path = Path("data/hits_board-1.csv")
    if not data_path.exists():
        return pd.DataFrame()
    df = pd.read_csv(data_path)
    df["last5"] = pd.to_numeric(df["last5"], errors="coerce").fillna(0.0)
    df["edge"] = df["fair_est"] - df["book_implied"]
    df["line"] = 0.5
    df["over_odds"] = df["odds_1plus"]
    df["team"] = df["team"]
    return df[["player", "team", "line", "over_odds", "book_implied", "fair_est", "edge"]]


def load_data(use_live: bool) -> pd.DataFrame:
    if use_live and ODDS_API_KEY:
        try:
            df = load_live_data()
            if not df.empty:
                return df, "live"
        except Exception as e:
            st.warning(f"Live odds unavailable ({e}). Falling back to static board.")
    df = load_static_data()
    return df, "static"


# ── Groq helpers ──────────────────────────────────────────────────────────────

def run_ai_analysis(picks: list[dict], question: str = "") -> str:
    from groq_analyst import analyze_picks
    return analyze_picks(picks, user_question=question)


def run_ai_summary(stats: dict) -> str:
    from groq_analyst import quick_summary
    return quick_summary(stats)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    st.title("⚾ Sports Betting Plus")
    st.subheader("MLB Hits Props — Live Value Dashboard")

    # ── Sidebar ──
    with st.sidebar:
        st.header("⚙️ Settings")

        use_live = st.toggle(
            "Live Odds (The Odds API)",
            value=bool(ODDS_API_KEY),
            disabled=not bool(ODDS_API_KEY),
            help="Pull real-time lines. Requires ODDS_API_KEY.",
        )

        st.divider()
        st.header("🔍 Filters")

    df, data_source = load_data(use_live)

    if df.empty:
        st.error("No data available. Check your API key or ensure data/hits_board-1.csv exists.")
        st.stop()

    source_badge = "🟢 Live" if data_source == "live" else "🟡 Static Board"
    st.caption(f"Data source: {source_badge} · {len(df)} players loaded")

    # ── Sidebar filters (need df) ──
    with st.sidebar.form("filter_form"):
        edge_threshold = st.slider(
            "Min Edge",
            min_value=0.0, max_value=0.12,
            value=0.03, step=0.005, format="%.3f",
        )
        all_teams = sorted(df["team"].dropna().unique())
        selected_teams = st.multiselect("Teams", options=all_teams, default=all_teams)
        player_search = st.text_input("Search Player", placeholder="e.g. Ohtani")
        submitted = st.form_submit_button("Apply Filters", use_container_width=True)

    if submitted or "filtered_df" not in st.session_state:
        filtered = df[
            (df["edge"] >= edge_threshold)
            & (df["team"].isin(selected_teams))
            & (df["player"].str.contains(player_search, case=False, na=False))
        ].sort_values("edge", ascending=False).copy()
        st.session_state.filtered_df = filtered
        st.session_state.edge_threshold = edge_threshold
    else:
        filtered = st.session_state.filtered_df
        edge_threshold = st.session_state.get("edge_threshold", 0.03)

    # ── KPIs ──
    st.markdown("### 📊 Board Overview")
    k1, k2, k3, k4 = st.columns(4)
    avg_edge = filtered["edge"].mean() if len(filtered) > 0 else 0.0
    best = filtered.iloc[0] if len(filtered) > 0 else None

    k1.metric("Total Players", len(df))
    k2.metric("Value Bets", len(filtered), delta=f"{len(filtered)/len(df):.1%} of board" if len(df) else None)
    k3.metric("Avg Edge", f"{avg_edge:.2%}")
    if best is not None:
        k4.metric("Best Play", f"{best['player']}", delta=f"+{best['edge']:.2%} edge")
    else:
        k4.metric("Best Play", "—")

    st.divider()

    # ── AI Summary bar ──
    if GROQ_API_KEY and len(filtered) > 0:
        with st.expander("🤖 AI Board Summary", expanded=True):
            if st.button("Generate AI Summary", key="summary_btn"):
                stats = {
                    "total_value_bets": len(filtered),
                    "avg_edge": round(avg_edge, 4),
                    "top_edge": round(filtered["edge"].max(), 4),
                    "top_player": filtered.iloc[0]["player"],
                    "teams_represented": filtered["team"].nunique(),
                }
                with st.spinner("Asking Groq..."):
                    try:
                        summary = run_ai_summary(stats)
                        st.markdown(f'<div class="ai-box">{summary}</div>', unsafe_allow_html=True)
                    except Exception as e:
                        st.error(f"AI error: {e}")

    # ── Main table ──
    st.markdown(f"### 🎯 Value Bets ({len(filtered)} plays)")

    if len(filtered) == 0:
        st.warning("No value bets match your filters. Try lowering the edge threshold.")
    else:
        display_cols = ["player", "team", "line", "over_odds", "book_implied", "fair_est", "edge"]
        display_df = filtered[display_cols].copy()
        display_df.columns = ["Player", "Team/Game", "Line", "Odds", "Book Implied", "Fair Est.", "Edge"]

        for col in ["Book Implied", "Fair Est.", "Edge"]:
            display_df[col] = display_df[col].apply(lambda x: f"{x:.1%}" if pd.notna(x) else "N/A")
        display_df["Odds"] = display_df["Odds"].apply(
            lambda x: f"+{int(x)}" if pd.notna(x) and x > 0 else (f"{int(x)}" if pd.notna(x) else "N/A")
        )

        def highlight_edge(val):
            try:
                num = float(val.strip("%")) / 100
                if num >= 0.05:
                    return "background-color: #d4edda; color: #155724; font-weight: bold"
                elif num >= 0.03:
                    return "background-color: #c3e6cb; color: #155724"
                elif num > 0:
                    return "background-color: #fff3cd; color: #856404"
                return "background-color: #f8d7da; color: #721c24"
            except Exception:
                return ""

        st.dataframe(
            display_df.style.applymap(highlight_edge, subset=["Edge"]),
            use_container_width=True,
            hide_index=True,
            height=420,
        )

        csv = filtered.to_csv(index=False).encode("utf-8")
        st.download_button(
            "📥 Download CSV",
            data=csv,
            file_name="value_bets.csv",
            mime="text/csv",
            use_container_width=True,
        )

    st.divider()

    # ── Charts ──
    st.markdown("### 📈 Visual Analysis")
    tab1, tab2, tab3 = st.tabs(["🔍 Fair vs Book", "📊 Top Plays", "📉 Edge Distribution"])

    with tab1:
        if len(filtered) > 0:
            fig = px.scatter(
                filtered, x="book_implied", y="fair_est", color="edge",
                color_continuous_scale="RdYlGn", range_color=[-0.05, 0.12],
                hover_data={"player": True, "team": True, "edge": ":.2%"},
                title="Fair Probability vs Book Implied",
                labels={"book_implied": "Book Implied %", "fair_est": "Fair Est. %", "edge": "Edge"},
                height=520,
            )
            fig.add_trace(go.Scatter(
                x=[0.45, 0.85], y=[0.45, 0.85], mode="lines",
                name="No Edge", line=dict(color="gray", dash="dash"),
            ))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No data to plot.")

    with tab2:
        if len(filtered) > 0:
            top_df = filtered.head(15).sort_values("edge", ascending=True)
            fig = px.bar(
                top_df, x="edge", y="player", color="edge",
                color_continuous_scale="RdYlGn", orientation="h",
                hover_data=["team", "fair_est", "book_implied"],
                title="Top 15 Value Plays by Edge",
                labels={"edge": "Edge", "player": "Player"},
                height=520,
            )
            fig.update_layout(showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No value bets to display.")

    with tab3:
        if len(filtered) > 1:
            fig = px.histogram(
                filtered, x="edge", nbins=25,
                color_discrete_sequence=["#636EFA"],
                title="Edge Distribution",
                labels={"edge": "Edge"},
                height=420,
            )
            fig.add_vline(x=edge_threshold, line_dash="dash", line_color="red", annotation_text="Threshold")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Need at least 2 data points.")

    st.divider()

    # ── AI Analyst chat ──
    if GROQ_API_KEY:
        st.markdown("### 🤖 Ask the AI Analyst")
        st.caption("Ask questions about today's value plays, matchups, or strategy.")

        if "chat_history" not in st.session_state:
            st.session_state.chat_history = []

        for msg in st.session_state.chat_history:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        if prompt := st.chat_input("Ask about today's picks..."):
            st.session_state.chat_history.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)

            top_picks = filtered.head(10)[["player", "team", "line", "over_odds", "book_implied", "fair_est", "edge"]].to_dict("records")
            with st.chat_message("assistant"):
                with st.spinner("Thinking..."):
                    try:
                        response = run_ai_analysis(top_picks, question=prompt)
                        st.markdown(response)
                        st.session_state.chat_history.append({"role": "assistant", "content": response})
                    except Exception as e:
                        st.error(f"AI error: {e}")
    else:
        st.info("Set GROQ_API_KEY to enable the AI Analyst feature.")

    st.divider()
    st.caption("Sports Betting Plus · Live odds via The Odds API · AI analysis by Groq · Always bet responsibly.")


if __name__ == "__main__":
    main()
