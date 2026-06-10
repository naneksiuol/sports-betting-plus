import os
import sys
from pathlib import Path

_env_file = Path(__file__).parent.parent / ".env"
try:
    from dotenv import load_dotenv
    load_dotenv(_env_file, override=True)
except ImportError:
    if _env_file.exists():
        for _line in _env_file.read_text(encoding="utf-8").splitlines():
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                os.environ.setdefault(_k.strip(), _v.strip())

try:
    import streamlit as _st_tmp
    for k, v in _st_tmp.secrets.items():
        os.environ.setdefault(k, str(v))
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).parent))

import json
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

from edge_model import (
    edge_confidence_score,
    confidence_label,
    recommended_stake,
    edge_rating,
    clv_summary,
    clv_rating,
    kelly_portfolio,
    get_market_pair_rho,
)
from bet_tracker import get_clv_avg
from settings_manager import load_settings, save_settings

ODDS_API_KEY = os.environ.get("ODDS_API_KEY", "")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")


def _share_btn(text: str, uid: str, width: str = "auto") -> None:
    """
    Share slip — expander with st.code so Streamlit's native copy button works.
    No JS, no rerun, works inside columns and expanders.
    """
    with st.expander("📤 Share", expanded=False):
        st.code(text, language=None)

st.set_page_config(
    page_title="Sports Betting Plus Bot",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Auth gate ─────────────────────────────────────────────────────────────────
_SUPABASE_CONFIGURED = bool(os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_ANON_KEY"))

if _SUPABASE_CONFIGURED:
    import auth, auth_ui, tiers as _tiers

    auth.handle_oauth_callback()

    if not auth.is_authenticated():
        auth_mode = st.session_state.get("auth_mode")
        if auth_mode in ("login", "signup"):
            auth_ui.show_auth_page()
        else:
            from landing import show_landing
            show_landing(
                on_login=lambda: st.session_state.update({"auth_mode": "login"}),
                on_signup=lambda: st.session_state.update({"auth_mode": "signup"}),
            )
        st.stop()

    # Clear auth UI state so login form doesn't ghost behind the dashboard
    st.session_state.pop("auth_mode", None)

    # User is logged in — show user menu in sidebar
    auth_ui.show_user_menu()

    # Admin panel (full-page overlay for admin users)
    if auth.is_admin() and st.session_state.get("show_admin", False):
        from admin_panel import show_admin_panel
        show_admin_panel()
        st.stop()

    _current_tier = auth.get_tier()
else:
    # Supabase not configured yet — run in open mode (local dev)
    _current_tier = "premium"
    _tiers = None
    try:
        import tiers as _tiers
    except ImportError:
        pass

# ── Design System — matches email (send_daily_bets.py) exactly ────────────────
# Palette:  bg #0f0f13  card #1a1a24  border #2a2a3a
#           purple #a78bfa  green #34d399  text #e8e8f0  muted #888
# Sport gradients: MLB green · NBA blue · WNBA red · NHL blue
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=Space+Grotesk:wght@400;500;600;700&display=swap');

/* ── Base ── */
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

.stApp {
    background: #0f0f13;
}

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background: #0d0d18 !important;
    border-right: 1px solid #2a2a3a !important;
}
[data-testid="stSidebar"] .stMarkdown h1,
[data-testid="stSidebar"] .stMarkdown h2,
[data-testid="stSidebar"] .stMarkdown h3 {
    color: #a78bfa !important;
    font-family: 'Space Grotesk', sans-serif !important;
}

/* ── Main title ── */
h1 {
    font-family: 'Space Grotesk', sans-serif !important;
    font-weight: 800 !important;
    background: linear-gradient(90deg, #a78bfa 0%, #7c3aed 50%, #4f46e5 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    font-size: 2.4rem !important;
    letter-spacing: -0.5px !important;
}
h2, h3 {
    font-family: 'Space Grotesk', sans-serif !important;
    color: #e8e8f0 !important;
}

/* ── Metric cards — matches email stat-chip style ── */
[data-testid="metric-container"] {
    background: #1a1a24 !important;
    border: 1px solid #2a2a3a !important;
    border-radius: 16px !important;
    padding: 1.2rem !important;
    transition: border-color 0.25s ease, box-shadow 0.25s ease;
}
[data-testid="metric-container"]:hover {
    border-color: #3a3a5a !important;
    box-shadow: 0 4px 24px rgba(167,139,250,0.1) !important;
}
[data-testid="metric-container"] [data-testid="stMetricValue"] {
    font-family: 'Space Grotesk', sans-serif !important;
    font-size: 1.8rem !important;
    font-weight: 800 !important;
    color: #a78bfa !important;
}
[data-testid="metric-container"] [data-testid="stMetricLabel"] {
    color: #666 !important;
    font-size: 0.75rem !important;
    text-transform: uppercase;
    letter-spacing: 0.1em;
}
[data-testid="metric-container"] [data-testid="stMetricDelta"] {
    font-size: 0.82rem !important;
}

/* ── Tabs — pill style matching email nav ── */
[data-testid="stTabs"] [data-baseweb="tab-list"] {
    background: #13131f !important;
    border-radius: 14px !important;
    padding: 5px !important;
    border: 1px solid #2a2a3a !important;
    gap: 3px !important;
}
[data-testid="stTabs"] [data-baseweb="tab"] {
    border-radius: 10px !important;
    font-family: 'Space Grotesk', sans-serif !important;
    font-weight: 500 !important;
    color: #666 !important;
    transition: all 0.2s ease !important;
    padding: 0.45rem 1rem !important;
}
[data-testid="stTabs"] [aria-selected="true"] {
    background: linear-gradient(135deg, #7c3aed, #4f46e5) !important;
    color: #fff !important;
    border: none !important;
    box-shadow: 0 2px 12px rgba(124,58,237,0.4) !important;
}

/* ── Dataframe — card border style ── */
[data-testid="stDataFrame"] {
    border: 1px solid #2a2a3a !important;
    border-radius: 14px !important;
    overflow: hidden !important;
    background: #1a1a24 !important;
}

/* ── Buttons — matches email CTA style ── */
.stButton > button {
    background: #1a1a24 !important;
    border: 1px solid #3a3a5a !important;
    border-radius: 10px !important;
    color: #a78bfa !important;
    font-family: 'Space Grotesk', sans-serif !important;
    font-weight: 600 !important;
    transition: all 0.2s ease !important;
}
.stButton > button:hover {
    background: linear-gradient(135deg, #7c3aed22, #4f46e522) !important;
    border-color: #7c3aed !important;
    box-shadow: 0 4px 20px rgba(124,58,237,0.25) !important;
    transform: translateY(-1px) !important;
    color: #c4b5fd !important;
}
/* Primary (type="primary") buttons — email's gradient CTA */
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #7c3aed, #4f46e5) !important;
    border-color: transparent !important;
    color: #fff !important;
    box-shadow: 0 2px 12px rgba(124,58,237,0.4) !important;
}
.stButton > button[kind="primary"]:hover {
    background: linear-gradient(135deg, #6d28d9, #4338ca) !important;
    box-shadow: 0 4px 20px rgba(124,58,237,0.55) !important;
    color: #fff !important;
}

/* ── Download button ── */
[data-testid="stDownloadButton"] > button {
    background: #1a1a24 !important;
    border: 1px solid #2a2a3a !important;
    color: #888 !important;
}

/* ── Selectbox / multiselect / input ── */
[data-baseweb="select"], [data-baseweb="input"], [data-baseweb="textarea"] {
    background: #1a1a24 !important;
    border-color: #2a2a3a !important;
    border-radius: 8px !important;
    color: #e8e8f0 !important;
}

/* ── Slider ── */
[data-testid="stSlider"] [data-baseweb="slider"] div[role="slider"] {
    background: #a78bfa !important;
}

/* ── Expander — card style ── */
[data-testid="stExpander"] {
    background: #1a1a24 !important;
    border: 1px solid #2a2a3a !important;
    border-radius: 14px !important;
}
[data-testid="stExpander"] summary {
    color: #e8e8f0 !important;
}

/* ── Divider — subtle, matching email footer line ── */
hr { border-color: #2a2a3a !important; }

/* ── Sidebar toggle buttons (market filter pills) ── */
[data-testid="stSidebar"] .stButton > button {
    font-size: 0.75rem !important;
    padding: 0.3rem 0.6rem !important;
    border-radius: 20px !important;
    font-weight: 500 !important;
    background: #13131f !important;
    border-color: #2a2a3a !important;
    color: #888 !important;
}
[data-testid="stSidebar"] .stButton > button:hover {
    border-color: #a78bfa !important;
    color: #a78bfa !important;
    box-shadow: none !important;
}

/* ── Info / Warning / Error boxes ── */
[data-testid="stAlert"] {
    background: #1a1a24 !important;
    border: 1px solid #2a2a3a !important;
    border-radius: 12px !important;
}

/* ── Custom components — all updated to match email tokens ── */
.glass-card {
    background: #1a1a24;
    border: 1px solid #2a2a3a;
    border-radius: 16px;
    padding: 1.5rem;
    margin-bottom: 1rem;
}

/* AI analysis box — email card style with purple left accent */
.ai-box {
    background: #13131f;
    border: 1px solid #2a2a3a;
    border-left: 4px solid #a78bfa;
    color: #e8e8f0;
    padding: 1.2rem;
    border-radius: 12px;
    font-size: 0.95rem;
    line-height: 1.7;
}

/* Badge system — matches email _edge_badge() exactly */
.gold-badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 20px;
    background: #2e2510;
    border: 1px solid #ffc53d33;
    color: #ffc53d;
    font-weight: 700;
    font-size: 0.82rem;
}
.green-badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 20px;
    background: #1a3a1a;
    border: 1px solid #34d39933;
    color: #34d399;
    font-weight: 700;
    font-size: 0.82rem;
}
.purple-badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 20px;
    background: #1e1428;
    border: 1px solid #a78bfa33;
    color: #a78bfa;
    font-weight: 700;
    font-size: 0.82rem;
}

/* Stat row + chips — mirrors email _stat_chip() */
.stat-row {
    display: flex;
    gap: 1rem;
    flex-wrap: wrap;
    margin-bottom: 1rem;
}
.stat-chip {
    background: #1a1a24;
    border: 1px solid #2a2a3a;
    border-radius: 14px;
    padding: 0.3rem 0.8rem;
    font-size: 0.8rem;
    color: #888;
}
.win-chip  { border-color: #34d39944; color: #34d399; background: #0d2018; }
.loss-chip { border-color: #ff6060aa; color: #ff6060; background: #1e0d0d; }
.pending-chip { border-color: #ffc53d44; color: #ffc53d; background: #1e1a0a; }

/* Section header — uppercase label like email section headers */
.section-header {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 0.75rem;
    font-weight: 700;
    color: #666;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    margin-bottom: 0.5rem;
}

/* Sport banner — matches email sport section gradient header */
.sport-banner-mlb  { background: linear-gradient(135deg,#1a472a 0%,#2d6a4f 100%); }
.sport-banner-nba  { background: linear-gradient(135deg,#0a3161 0%,#1d4e8f 100%); }
.sport-banner-wnba { background: linear-gradient(135deg,#7b1a1a 0%,#c8102e 100%); }
.sport-banner-nhl  { background: linear-gradient(135deg,#003087 0%,#0057b8 100%); }
.sport-banner {
    border-radius: 16px 16px 0 0;
    padding: 20px 24px 18px;
    margin-bottom: 0;
}

/* Payout hero card — matches email _payout_hero() */
.payout-hero {
    background: linear-gradient(135deg,#141420 0%,#1e1e2e 100%);
    border: 1px solid #3a3a5a;
    border-radius: 12px;
    padding: 16px 20px;
    margin-bottom: 14px;
    display: flex;
    align-items: center;
    gap: 20px;
    flex-wrap: wrap;
}

/* ── Mobile responsive overrides (max-width: 768px) ── */
@media (max-width: 768px) {
    /* 1. Sidebar: collapsed/hidden by default on mobile */
    [data-testid="stSidebar"] {
        transform: translateX(-100%) !important;
        position: fixed !important;
        z-index: 999 !important;
        width: 80vw !important;
        min-width: 0 !important;
        max-width: 320px !important;
        height: 100vh !important;
        overflow-y: auto !important;
        transition: transform 0.3s ease !important;
    }
    [data-testid="stSidebar"][aria-expanded="true"] {
        transform: translateX(0) !important;
    }

    /* 2. Reduce font sizes for metric labels on small screens */
    [data-testid="stMetric"] [data-testid="stMetricValue"],
    [data-testid="metric-container"] [data-testid="stMetricValue"] {
        font-size: 1.2rem !important;
    }
    [data-testid="stMetric"] [data-testid="stMetricLabel"],
    [data-testid="metric-container"] [data-testid="stMetricLabel"] {
        font-size: 0.65rem !important;
    }
    [data-testid="stMetric"] [data-testid="stMetricDelta"],
    [data-testid="metric-container"] [data-testid="stMetricDelta"] {
        font-size: 0.72rem !important;
    }

    /* 3. Stack st.columns vertically on mobile */
    [data-testid="column"] {
        width: 100% !important;
        flex: 0 0 100% !important;
        max-width: 100% !important;
        min-width: 100% !important;
    }
    [data-testid="stHorizontalBlock"] {
        flex-direction: column !important;
        gap: 0.5rem !important;
    }

    /* 4. Ensure tables scroll horizontally */
    .stDataFrame,
    [data-testid="stDataFrame"] {
        overflow-x: auto !important;
        -webkit-overflow-scrolling: touch !important;
        display: block !important;
        max-width: 100vw !important;
    }
    .stDataFrame > div,
    [data-testid="stDataFrame"] > div {
        overflow-x: auto !important;
        min-width: 0 !important;
    }

    /* 5. Reduce chart padding/margins on mobile */
    .js-plotly-plot {
        margin: 0 !important;
        padding: 0 !important;
    }
    .js-plotly-plot .plotly {
        margin: 0 !important;
    }
    .js-plotly-plot .svg-container {
        margin: 0 auto !important;
    }

    /* General: prevent horizontal overflow on mobile */
    .main .block-container {
        padding-left: 0.75rem !important;
        padding-right: 0.75rem !important;
        max-width: 100vw !important;
        overflow-x: hidden !important;
    }

    /* Reduce main title size on mobile */
    h1 {
        font-size: 1.6rem !important;
    }
}
</style>
""", unsafe_allow_html=True)

# ── Plotly dark theme — matches email bg/card palette ─────────────────────────
PLOT_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="#13131f",
    font_color="#888",
    font_family="Inter",
    xaxis=dict(gridcolor="#2a2a3a", zerolinecolor="#3a3a5a"),
    yaxis=dict(gridcolor="#2a2a3a", zerolinecolor="#3a3a5a"),
)

from odds_client import SPORTS_CONFIG


# ── Data loading ──────────────────────────────────────────────────────────────
@st.cache_data(ttl=300, show_spinner="⚡ Fetching live odds...")
def load_live_data(sport: str) -> tuple:
    from odds_client import get_props, quota_exhausted
    exhausted = quota_exhausted()
    df = get_props(sport)
    source = "scraped" if exhausted else "live"
    return df, source


@st.cache_data(ttl=300, show_spinner="🔵 Scraping Action Network...")
def load_scraped_data(sport: str) -> pd.DataFrame:
    from scraper import scrape_props
    return scrape_props(sport)


def preload_all_sports_parallel(use_live: bool = False):
    """
    Warm the @st.cache_data caches for all live sports.
    Runs sequentially on the main thread to avoid Streamlit cache-thread issues.
    Only runs once per session (tracked in session_state).
    """
    if st.session_state.get("_sports_preloaded"):
        return
    live_sports = [s for s, cfg in SPORTS_CONFIG.items() if cfg.get("status", "live") == "live"]
    for s in live_sports:
        try:
            load_scraped_data(s)
        except Exception:
            pass
    st.session_state["_sports_preloaded"] = True


@st.cache_data(ttl=300)
def _get_game_lines_cached(sport: str) -> "pd.DataFrame":
    from odds_client import get_game_lines
    return get_game_lines(sport)


@st.cache_data(ttl=3600)
def load_static_mlb() -> pd.DataFrame:
    data_path = Path(__file__).parent.parent / "data" / "hits_board-1.csv"
    if not data_path.exists():
        return pd.DataFrame()
    df = pd.read_csv(data_path)
    df["last5"] = pd.to_numeric(df["last5"], errors="coerce").fillna(0.0)
    df["book_implied"] = pd.to_numeric(df["book_implied"], errors="coerce")
    # Static CSV only has over odds — use flat 5% markup as fair estimate
    # (Shin de-vig requires both Over+Under; skipping to avoid all-negative edges)
    df["fair_est"] = (df["book_implied"] * 1.05).clip(upper=0.99)
    df["edge"] = df["fair_est"] - df["book_implied"]
    df["n_books"] = 1
    df["line"] = 0.5
    df["over_odds"] = pd.to_numeric(df["odds_1plus"], errors="coerce")
    df["market"] = "batter_hits"
    return df[["player", "team", "market", "line", "over_odds", "book_implied", "fair_est", "edge", "n_books"]]


def load_data(sport: str, use_live: bool):
    # Try live API first if toggle is on and key is present
    if use_live and ODDS_API_KEY:
        try:
            df, source = load_live_data(sport)
            if not df.empty:
                return df, source
        except Exception as e:
            st.warning(f"Live odds unavailable ({e}). Falling back to scraped data.")

    # Always try scraper as fallback (no API key needed)
    try:
        df = load_scraped_data(sport)
        if not df.empty:
            return df, "scraped"
    except Exception as _scrape_err:
        st.warning(f"{sport} scraper error: {_scrape_err}")

    # Fallback: read locally-scraped cache pushed to repo by scheduled task
    try:
        _cache_path = Path(__file__).parent.parent / "data" / f"props_cache_{sport.lower()}.json"
        if _cache_path.exists():
            import json as _json
            _payload = _json.loads(_cache_path.read_text(encoding="utf-8"))
            _records = _payload.get("data", [])
            if _records:
                _cached_df = pd.DataFrame(_records)
                _scraped_at = _payload.get("scraped_at", "")
                _source_label = f"cached · {_scraped_at[:16]}" if _scraped_at else "cached"
                return _cached_df, _source_label
    except Exception:
        pass

    # Last resort: static CSV for MLB hits only
    if sport == "MLB":
        return load_static_mlb(), "static"
    return pd.DataFrame(), "unavailable"


# ── Groq helpers ──────────────────────────────────────────────────────────────
def run_ai_analysis(picks: list[dict], question: str = "") -> str:
    from groq_analyst import analyze_picks
    return analyze_picks(picks, user_question=question)


def run_ai_summary(stats: dict) -> str:
    from groq_analyst import quick_summary
    return quick_summary(stats)


# ── Bet Tracker Tab ───────────────────────────────────────────────────────────
def render_bet_tracker():
    from bet_tracker import load_bets, add_bet, update_result, delete_bet, get_stats
    import plotly.graph_objects as go

    st.markdown("## 📊 Bet Tracker")
    st.caption("Log your bets, track results, and measure if the system is actually profitable.")

    # Load once per render and pass through — avoids 5+ repeated disk reads
    _uid = st.session_state.get("user_id")
    _all_bets_cache = load_bets(user_id=_uid)
    stats = get_stats(user_id=_uid)

    # ── KPIs ──
    k1, k2, k3, k4, k5 = st.columns(5)
    roi_color = "#00ff88" if stats["roi"] >= 0 else "#ff6060"
    k1.metric("Total Bets", stats["total_bets"])
    k2.metric("Win Rate", f"{stats['win_rate']}%", delta=f"{stats['wins']}W / {stats['losses']}L / {stats.get('voids',0)}V")
    k3.metric("Total Profit", f"${stats['total_profit']:+.2f}")
    k4.metric("ROI", f"{stats['roi']:+.1f}%")
    clv_val = stats.get("avg_clv") or stats.get("avg_opening_clv")
    clv_label = "Avg CLV" if stats.get("avg_clv") else "Avg Opening CLV"
    k5.metric(clv_label,
              f"{clv_val:+.2f}%" if clv_val is not None else "—",
              help="Closing Line Value vs sharp/Pinnacle line. Positive = you beat the market. Opening CLV shown when no closing line yet.")

    st.divider()

    col_log, col_list = st.columns([1, 2])

    # ── Log a bet ──
    with col_log:
        st.markdown('<div class="section-header">➕ Log a Bet</div>', unsafe_allow_html=True)
        with st.form("log_bet_form", clear_on_submit=True):
            sport = st.selectbox("Sport", [s for s in SPORTS_CONFIG if SPORTS_CONFIG[s]["status"] == "live"])
            player = st.text_input("Player", placeholder="e.g. Daniel Susac")
            prop = st.text_input("Prop", placeholder="e.g. 1+ Hits, Points O22.5")
            line = st.number_input("Line", value=0.5, step=0.5)
            odds = st.number_input("Odds (American)", value=-150, step=5)
            win_prob = st.number_input("Est. Win Prob (%)", value=55.0, min_value=1.0,
                                       max_value=99.0, step=0.5,
                                       help="Your fair probability estimate. Use Fair Est. from the table.")
            _bankroll = st.session_state.get("bankroll_input", 1000.0)
            _kmult = st.session_state.get("kelly_mult", 0.25)
            # Wire real CLV history into dynamic Kelly — stake scales with proven track record
            _uid = st.session_state.get("user_id")
            _clv_avg = get_clv_avg(n_recent=30, user_id=_uid)
            _rec = recommended_stake(win_prob / 100, float(odds), _bankroll, _kmult, clv_avg=_clv_avg)
            _clv_note = f" | CLV avg: {_clv_avg:+.1f}% (last 30)" if _clv_avg is not None else " | CLV: no history yet"
            st.caption(f"💡 Kelly suggestion: **${_rec['stake']:.2f}** ({_rec['recommended_pct']:.1f}% · {_rec['kelly_multiplier']:.0%} Kelly) | EV: ${_rec['ev_on_stake']:+.2f}{_clv_note}")
            stake = st.number_input("Stake ($)", value=float(_rec["stake"]) if _rec["stake"] > 0 else 10.0,
                                    step=1.0, min_value=0.5)
            book = st.text_input("Sportsbook", placeholder="DraftKings, FanDuel...")
            is_parlay_bet = st.checkbox("🎰 Is Parlay?", value=False, help="Mark if this is a parlay ticket")
            notes = st.text_input("Notes", placeholder="Optional")
            if st.form_submit_button("🎯 Log Bet", use_container_width=True):
                if player and prop:
                    # Auto-fetch sharp line at bet time for CLV
                    sharp_odds_val = None
                    try:
                        from sharp_line import get_sharp_lines
                        from scraper import PROP_TYPE_MAP
                        mkt_key = next((k for k, v in PROP_TYPE_MAP.items()
                                       if prop.lower() in v or v in prop.lower()), None)
                        if mkt_key:
                            slines = get_sharp_lines(sport)
                            match = slines.get((player.lower(), mkt_key, float(line)))
                            if match:
                                sharp_odds_val = match["consensus_odds"]
                    except Exception:
                        pass
                    _edge_val = (win_prob / 100 - (100 / (100 + abs(odds)) if odds < 0 else odds / (100 + odds))) if win_prob else None
                    add_bet(sport, player, prop, line, int(odds), stake, book, notes,
                            sharp_odds=sharp_odds_val, fair_est=win_prob/100,
                            is_parlay=is_parlay_bet, edge=_edge_val)
                    def _american_to_dec(o):
                        return (o/100+1) if o > 0 else (100/abs(o)+1)
                    clv_msg = f" | Opening CLV: {((1/_american_to_dec(sharp_odds_val))-(1/_american_to_dec(int(odds))))*100:+.1f}% vs sharp" if sharp_odds_val else ""
                    st.success(f"✅ Bet logged!{clv_msg}")
                    st.rerun()
                else:
                    st.error("Player and prop are required.")

    # ── Bet list ──
    with col_list:
        st.markdown('<div class="section-header">📋 All Bets</div>', unsafe_allow_html=True)

        bets = _all_bets_cache
        if not bets:
            st.info("No bets logged yet. Use the form to log your first bet.")
        else:
            # Result filter
            filter_result = st.selectbox("Filter", ["All", "Pending", "Win", "Loss", "Push", "Void"],
                                          key="bet_filter", label_visibility="collapsed")
            filtered_bets = bets if filter_result == "All" else [
                b for b in bets if b["result"].lower() == filter_result.lower()
            ]

            if filtered_bets:
                import csv, io as _io
                _buf = _io.StringIO()
                _fields = ["date", "sport", "player", "prop", "line", "odds", "stake",
                           "book", "result", "profit", "fair_est", "edge", "opening_clv", "clv", "notes"]
                _w = csv.DictWriter(_buf, fieldnames=_fields, extrasaction="ignore")
                _w.writeheader()
                _w.writerows(filtered_bets)
                st.download_button("📥 Export CSV", _buf.getvalue(), "bets.csv", "text/csv", use_container_width=False)

            for bet in reversed(filtered_bets):
                result = bet["result"]
                badge = {
                    "win": "🟢 WIN",
                    "loss": "🔴 LOSS",
                    "push": "⚪ PUSH",
                    "void": "↩️ VOID",
                    "pending": "🟡 PENDING"
                }.get(result, "🟡 PENDING")

                profit_str = f"${bet['profit']:+.2f}" if bet["profit"] is not None else "—"
                # Show best available CLV info — explicit None check avoids dropping 0.0 CLV
                clv_display = bet.get("clv") if bet.get("clv") is not None else bet.get("opening_clv")
                clv_label = "CLV" if bet.get("clv") else "Opening CLV"
                clv_str = f"{clv_label}: {clv_display:+.2f}%" if clv_display is not None else ""

                with st.expander(f"{badge} | {bet['player']} — {bet['prop']} | {bet['sport']} | {bet['date']}"):
                    c1, c2, c3 = st.columns(3)
                    c1.markdown(f"**Odds:** {bet['odds']}")
                    c1.markdown(f"**Line:** O{bet['line']}")
                    c2.markdown(f"**Stake:** ${bet['stake']:.2f}")
                    c2.markdown(f"**Book:** {bet.get('book') or '—'}")
                    c3.markdown(f"**Profit:** {profit_str}")
                    if clv_str:
                        color = "green" if clv_display > 0 else "red"
                        c3.markdown(f"**:{color}[{clv_str}]**")
                    if bet.get("sharp_odds"):
                        c1.markdown(f"**Sharp Line:** {bet['sharp_odds']:+d}")
                    if bet.get("notes"):
                        st.caption(f"📝 {bet['notes']}")

                    if result == "pending":
                        r_col1, r_col2, r_col3 = st.columns(3)
                        if r_col1.button("✅ Win", key=f"win_{bet['id']}"):
                            closing = st.session_state.get(f"close_{bet['id']}", None)
                            update_result(bet["id"], "win", closing)
                            st.rerun()
                        if r_col2.button("❌ Loss", key=f"loss_{bet['id']}"):
                            update_result(bet["id"], "loss")
                            st.rerun()
                        if r_col3.button("↩️ Push", key=f"push_{bet['id']}"):
                            update_result(bet["id"], "push")
                            st.rerun()
                        closing_odds = st.number_input("Closing Odds (optional for CLV)",
                                                       value=0, step=5, key=f"close_{bet['id']}")
                    if st.button("🗑️ Delete", key=f"del_{bet['id']}"):
                        delete_bet(bet["id"])
                        st.rerun()

                    # Share button — copies a text slip to clipboard
                    odds_fmt = f"+{bet['odds']}" if bet['odds'] > 0 else str(bet['odds'])
                    share_text = (
                        f"🎯 {bet['sport']} | {bet['player']}\n"
                        f"📊 {bet['prop']} @ {odds_fmt}\n"
                        f"💰 Stake: ${bet['stake']:.2f}  |  {badge}\n"
                        f"📅 {bet['date']}\n"
                        f"— via Sports Betting Plus"
                    )
                    _share_btn(share_text, f"bet_{bet['id']}")

    st.divider()

    # ── CLV Analytics ────────────────────────────────────────────────────────
    st.markdown("### 📈 Closing Line Value (CLV) Analysis")
    st.caption(
        "CLV is the gold-standard model validator. Consistently positive CLV = real edge. "
        "Negative CLV = short-term variance, not skill. Based on the research framework: "
        "CLV = (1/bet_decimal) − (1/closing_decimal)"
    )

    all_bets_for_clv = _all_bets_cache
    clv_data = clv_summary(all_bets_for_clv)

    if clv_data["n_with_clv"] == 0:
        st.info("No CLV data yet. CLV is calculated automatically when you enter a closing line while grading a bet.")
    else:
        cv1, cv2, cv3, cv4 = st.columns(4)
        avg_clv = clv_data["avg_clv"]
        clv_color = "normal" if avg_clv >= 0 else "inverse"
        cv1.metric("Avg CLV", f"{avg_clv:+.2f}%",
                   delta=clv_rating(avg_clv),
                   delta_color=clv_color)
        cv2.metric("CLV+ Rate", f"{clv_data['clv_positive_rate']:.0f}%",
                   help="% of bets where you beat the closing line")
        cv3.metric("Bets with CLV", clv_data["n_with_clv"])
        cv4.metric("Verdict",
                   "✅ Edge confirmed" if avg_clv > 1.5 else
                   ("🟡 Marginal" if avg_clv > 0 else "❌ No edge detected"))

        # CLV distribution chart
        clv_dist = clv_data.get("clv_distribution", [])
        if len(clv_dist) >= 3:
            import plotly.graph_objects as _go_clv
            fig_clv = _go_clv.Figure()
            fig_clv.add_trace(_go_clv.Bar(
                x=list(range(len(clv_dist))),
                y=clv_dist,
                marker_color=["#00ff88" if c > 0 else "#ff6060" for c in clv_dist],
                name="CLV per bet",
            ))
            fig_clv.add_hline(y=0, line_dash="dash", line_color="white", opacity=0.5)
            fig_clv.add_hline(y=avg_clv, line_dash="dot", line_color="#00d4ff",
                               annotation_text=f"Avg {avg_clv:+.2f}%",
                               annotation_position="top right")
            fig_clv.update_layout(
                title="CLV Per Bet (positive = beat the market)",
                xaxis_title="Bet #", yaxis_title="CLV (%)",
                height=260, margin=dict(l=0, r=0, t=40, b=0),
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                font=dict(color="white"),
            )
            st.plotly_chart(fig_clv, use_container_width=True, config={"responsive": True})

    st.divider()

    # ── Auto-Grader ──────────────────────────────────────────────────────────
    st.markdown("### 🤖 Auto-Grade Pending Bets")
    st.caption("Grades MLB, NBA, WNBA, and NHL bets automatically using free public stat APIs. Runs nightly via Task Scheduler (run setup_scheduler.bat to schedule).")

    pending_bets = [b for b in _all_bets_cache if b["result"] == "pending"]
    past_pending_dates = sorted(set(
        b["date"] for b in pending_bets
        if b["date"] < datetime.now().strftime("%Y-%m-%d")
    ))
    all_gradeable = [b for b in pending_bets
                     if b["date"] < datetime.now().strftime("%Y-%m-%d")]

    ag_col1, ag_col2 = st.columns([2, 1])
    with ag_col1:
        if not past_pending_dates:
            st.info("✅ No past pending bets to grade." if pending_bets
                    else "No pending bets found.")
        else:
            sports_in = ", ".join(sorted({b["sport"] for b in all_gradeable}))
            st.markdown(
                f"**{len(all_gradeable)} bet(s)** eligible ({sports_in}) "
                f"across **{len(past_pending_dates)} date(s)**: "
                f"{', '.join(past_pending_dates)}"
            )

    with ag_col2:
        grade_btn = st.button("⚡ Grade All Past Dates",
                              disabled=len(all_gradeable) == 0,
                              use_container_width=True,
                              type="primary")

    if grade_btn and past_pending_dates:
        from result_grader import grade_pending_bets
        total_graded = 0
        total_skipped = 0
        all_skipped_details = []
        progress = st.progress(0, text="Starting…")
        results_log = []

        for i, date_str in enumerate(past_pending_dates):
            progress.progress((i) / len(past_pending_dates),
                              text=f"Grading {date_str}…")
            try:
                summary = grade_pending_bets(target_date=date_str)
                total_graded += summary.get("graded", 0)
                total_skipped += summary.get("skipped", 0)
                all_skipped_details += summary.get("skipped_details", [])
                results_log.append(
                    f"**{date_str}** — ✅ {summary.get('graded', 0)} graded, "
                    f"⏭️ {summary.get('skipped', 0)} skipped"
                )
            except Exception as exc:
                results_log.append(f"**{date_str}** — ❌ Error: {exc}")

        progress.progress(1.0, text="Done!")

        if total_graded > 0:
            st.success(f"🎉 Graded **{total_graded}** bet(s) across {len(past_pending_dates)} date(s)! ({total_skipped} skipped)")
        else:
            st.warning(f"No bets could be auto-graded ({total_skipped} skipped). Check prop names match the grader's format.")

        with st.expander("📋 Grading Details", expanded=total_graded > 0):
            for line in results_log:
                st.markdown(line)
            if all_skipped_details:
                st.markdown("**Skipped (need manual grading):**")
                for s in all_skipped_details:
                    st.caption(f"• {s}")

        if total_graded > 0:
            st.rerun()

    st.divider()

    # ── Discord Scheduling ────────────────────────────────────────────────────
    st.divider()
    st.markdown("### 📡 Discord Automation")
    _dc_col1, _dc_col2 = st.columns([2, 1])
    with _dc_col1:
        from discord_bot import is_configured as _dc_ok
        if _dc_ok():
            st.success("✅ Discord webhook connected — daily slips enabled.")
            st.caption("Run **setup_scheduler.bat** as Administrator to schedule automatic 9 AM daily slips. Or send one manually:")
        else:
            st.warning("⚠️ Discord not connected. Add `DISCORD_WEBHOOK_URL` to your `.env` file.")
    with _dc_col2:
        if st.button("📨 Send Slip Now", use_container_width=True,
                     help="Scrapes live data and posts today's top plays to Discord immediately."):
            from discord_bot import is_configured as _dc_ok2
            if not _dc_ok2():
                st.error("Discord webhook not configured.")
            else:
                with st.spinner("Scraping all sports and sending…"):
                    try:
                        import subprocess
                        result = subprocess.run(
                            [sys.executable, str(Path(__file__).parent.parent / "run_discord_slip.py")],
                            capture_output=True, text=True, timeout=120
                        )
                        if result.returncode == 0:
                            st.success("✅ Daily slip sent! Check your Discord channel.")
                        else:
                            st.error(f"Script error: {result.stderr[-500:] if result.stderr else 'unknown'}")
                    except Exception as _e:
                        st.error(f"Failed: {_e}")

    # ── Charts ──
    if stats["settled"] > 0:
        st.markdown("### 📈 Performance Analytics")
        ch1, ch2 = st.columns(2)

        settled = stats["settled_bets"]

        with ch1:
            # Cumulative P&L
            running = []
            total = 0
            for b in settled:
                total += b["profit"] or 0
                running.append({"date": b["date"], "profit": round(total, 2)})
            pnl_df = pd.DataFrame(running)
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=pnl_df["date"], y=pnl_df["profit"],
                mode="lines+markers",
                line=dict(color="#00ff88", width=2),
                marker=dict(color="#00ff88", size=6),
                fill="tozeroy",
                fillcolor="rgba(0,255,136,0.08)",
                name="Cumulative P&L"
            ))
            fig.add_hline(y=0, line_dash="dash", line_color="rgba(255,255,255,0.2)")
            fig.update_layout(title="Cumulative P&L ($)", height=260, **PLOT_LAYOUT)
            st.plotly_chart(fig, use_container_width=True, config={"responsive": True})

        with ch2:
            # Win/Loss by sport
            if stats["by_sport"]:
                sport_data = [{"sport": k, **v} for k, v in stats["by_sport"].items()]
                sp_df = pd.DataFrame(sport_data)
                fig2 = go.Figure()
                fig2.add_trace(go.Bar(
                    x=sp_df["sport"], y=sp_df["wins"],
                    name="Wins", marker_color="rgba(0,255,136,0.7)"
                ))
                fig2.add_trace(go.Bar(
                    x=sp_df["sport"], y=sp_df["losses"],
                    name="Losses", marker_color="rgba(255,96,96,0.7)"
                ))
                fig2.update_layout(
                    title="Wins vs Losses by Sport", barmode="group",
                    height=260, **PLOT_LAYOUT
                )
                st.plotly_chart(fig2, use_container_width=True, config={"responsive": True})

        # ROI by sport table
        if stats["by_sport"]:
            st.markdown("#### 💰 ROI by Sport")
            rows = []
            for sport_name, d in stats["by_sport"].items():
                total_w = d["wins"] + d["losses"]
                wr = round(d["wins"] / total_w * 100, 1) if total_w > 0 else 0
                rows.append({
                    "Sport": sport_name,
                    "W": d["wins"], "L": d["losses"],
                    "Win %": f"{wr}%",
                    "Profit": f"${d['profit']:+.2f}"
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        # ── Parlay ROI History Chart ──
        parlay_bets = [b for b in settled if b.get("is_parlay") or b.get("parlay_legs")]
        if parlay_bets:
            st.markdown("#### 🎰 Parlay ROI History")
            parlay_rows = []
            for b in parlay_bets:
                legs = b.get("parlay_legs", 1)
                if isinstance(legs, list):
                    legs = len(legs)
                expected_ev_pct = b.get("parlay_ev_pct") or b.get("ev_pct") or 0.0
                actual_profit   = b.get("profit") or 0.0
                stake           = b.get("stake") or 0.0
                actual_roi_pct  = (actual_profit / stake * 100) if stake else 0.0
                parlay_rows.append({
                    "date":     b.get("date", ""),
                    "legs":     int(legs),
                    "expected": round(float(expected_ev_pct), 2),
                    "actual":   round(actual_roi_pct, 2),
                    "result":   b.get("result", "pending"),
                    "label":    f"{b.get('date','?')} ({legs}-leg)",
                })
            if parlay_rows:
                pr_df = pd.DataFrame(parlay_rows).sort_values("date")
                fig_p = go.Figure()
                fig_p.add_trace(go.Bar(
                    x=pr_df["label"], y=pr_df["expected"],
                    name="Expected EV%", marker_color="rgba(167,139,250,0.6)",
                ))
                fig_p.add_trace(go.Bar(
                    x=pr_df["label"], y=pr_df["actual"],
                    name="Actual ROI%",
                    marker_color=[
                        "rgba(52,211,153,0.8)" if r == "win" else
                        "rgba(255,96,96,0.8)"  if r == "loss" else
                        "rgba(120,120,140,0.5)"
                        for r in pr_df["result"]
                    ],
                ))
                fig_p.add_hline(y=0, line_dash="dash", line_color="rgba(255,255,255,0.2)")
                fig_p.update_layout(
                    title="Parlay: Expected EV% vs Actual ROI%",
                    barmode="group",
                    height=280,
                    **PLOT_LAYOUT,
                )
                st.plotly_chart(fig_p, use_container_width=True, config={"responsive": True})
                total_parlay_profit = sum(b.get("profit") or 0 for b in parlay_bets)
                parlay_wins = sum(1 for b in parlay_bets if b.get("result") == "win")
                st.caption(
                    f"📊 {len(parlay_bets)} parlays logged · "
                    f"{parlay_wins} wins · "
                    f"Total P&L: **${total_parlay_profit:+.2f}**"
                )
        else:
            st.caption("💡 Parlay ROI chart appears once you log parlays (tick 'Is Parlay' when logging).")

        # ── Streak Tracker ────────────────────────────────────────────────────
        st.divider()
        st.markdown("### 🔥 Streak Tracker")
        _streak_col1, _streak_col2, _streak_col3 = st.columns(3)

        # Compute current streak
        _streak_val = 0
        _streak_type = "—"
        for _b in reversed(settled):
            _r = _b.get("result")
            if _r == "push":
                continue
            if _streak_val == 0:
                _streak_type = "W" if _r == "win" else "L"
                _streak_val = 1
            elif (_r == "win" and _streak_type == "W") or (_r == "loss" and _streak_type == "L"):
                _streak_val += 1
            else:
                break

        # Longest win streak
        _best_streak, _cur, _cur_type = 0, 0, None
        for _b in settled:
            _r = _b.get("result")
            if _r == "push":
                continue
            if _r == "win":
                _cur = _cur + 1 if _cur_type == "W" else 1
                _cur_type = "W"
                _best_streak = max(_best_streak, _cur)
            else:
                _cur = _cur + 1 if _cur_type == "L" else 1
                _cur_type = "L"

        _streak_color = "normal" if _streak_type == "W" else "inverse"
        _streak_col1.metric("Current Streak",
                            f"{_streak_val}{_streak_type}" if _streak_val > 0 else "—",
                            delta="🔥" if _streak_type == "W" and _streak_val >= 3 else None)
        _streak_col2.metric("Best Win Streak", f"{_best_streak}W")
        _avg_stake = (sum(b.get("stake", 0) for b in settled) / len(settled)) if settled else 0
        _streak_col3.metric("Avg Stake", f"${_avg_stake:.2f}")

        # ── Daily P&L Breakdown ───────────────────────────────────────────────
        st.divider()
        st.markdown("### 📅 Daily P&L Breakdown")
        _daily: dict = {}
        for _b in settled:
            _d = _b.get("date", "?")
            if _d not in _daily:
                _daily[_d] = {"profit": 0.0, "wins": 0, "losses": 0, "bets": 0}
            _daily[_d]["profit"] += float(_b.get("profit") or 0)
            _daily[_d]["bets"]   += 1
            if _b.get("result") == "win":
                _daily[_d]["wins"] += 1
            elif _b.get("result") == "loss":
                _daily[_d]["losses"] += 1

        if _daily:
            _daily_rows = [
                {
                    "Date":    _d,
                    "Bets":    v["bets"],
                    "W":       v["wins"],
                    "L":       v["losses"],
                    "Win%":    f"{100*v['wins']/max(v['wins']+v['losses'],1):.0f}%",
                    "P&L":     f"${v['profit']:+.2f}",
                }
                for _d, v in sorted(_daily.items(), reverse=True)
            ]
            st.dataframe(pd.DataFrame(_daily_rows), use_container_width=True, hide_index=True)

        # ── CLV Tracking ──────────────────────────────────────────────────────
        st.divider()
        with st.expander("📐 CLV Tracking by Sport / Market / Book", expanded=False):
            _all_bets_clv = _all_bets_cache
            _clv_bets = [
                b for b in _all_bets_clv
                if (b.get("clv") if b.get("clv") is not None else b.get("opening_clv")) is not None
            ]
            if not _clv_bets:
                st.info("No bets with CLV data yet. CLV is captured when you log closing odds.")
            else:
                def _bet_clv(b):
                    return float(b.get("clv") if b.get("clv") is not None else b.get("opening_clv"))

                def _clv_table(group_key, label):
                    groups: dict = {}
                    for b in _clv_bets:
                        key = b.get(group_key) or "Unknown"
                        clv_val = _bet_clv(b)
                        res = b.get("result")
                        if key not in groups:
                            groups[key] = {"clv_sum": 0.0, "count": 0, "wins": 0, "settled": 0}
                        groups[key]["clv_sum"] += clv_val
                        groups[key]["count"] += 1
                        if res in ("win", "loss"):
                            groups[key]["settled"] += 1
                            if res == "win":
                                groups[key]["wins"] += 1
                    rows = []
                    for name, d in sorted(groups.items(), key=lambda x: -x[1]["clv_sum"]/x[1]["count"]):
                        avg_clv = d["clv_sum"] / d["count"]
                        win_pct = (d["wins"] / d["settled"] * 100) if d["settled"] > 0 else None
                        rows.append({
                            label:     name,
                            "Avg CLV": f"{avg_clv:+.2f}%",
                            "Count":   d["count"],
                            "Win%":    f"{win_pct:.0f}%" if win_pct is not None else "—",
                        })
                    return pd.DataFrame(rows)

                _c1, _c2, _c3 = st.columns(3)
                with _c1:
                    st.markdown("**By Sport**")
                    st.dataframe(_clv_table("sport", "Sport"), use_container_width=True, hide_index=True)
                with _c2:
                    st.markdown("**By Market**")
                    st.dataframe(_clv_table("market", "Market"), use_container_width=True, hide_index=True)
                with _c3:
                    st.markdown("**By Book**")
                    st.dataframe(_clv_table("book", "Book"), use_container_width=True, hide_index=True)

        # ── Bankroll Curve ────────────────────────────────────────────────────
        st.divider()
        with st.expander("💰 Bankroll Curve", expanded=False):
            _graded = [b for b in settled if b.get("result") in ("win", "loss", "push")]
            if not _graded:
                st.info("No graded bets yet.")
            else:
                def _odds_to_decimal(odds):
                    try:
                        odds = float(odds)
                    except (TypeError, ValueError):
                        return 1.0
                    if odds >= 100:
                        return (odds / 100) + 1
                    elif odds <= -100:
                        return (100 / abs(odds)) + 1
                    else:
                        return 1.0  # truly unknown odds

                _STARTING_BK = float(
                    st.session_state.get("bankroll_input") or
                    st.session_state.get("settings", {}).get("starting_bankroll") or
                    1000.0
                )
                _bk = _STARTING_BK
                _bk_rows = []
                for _b in _graded:
                    _res = _b.get("result")
                    _stake = float(_b.get("stake") or 0)
                    _odds  = _b.get("odds")
                    if _res == "win":
                        _pnl = _stake * (_odds_to_decimal(_odds) - 1)
                    elif _res == "loss":
                        _pnl = -_stake
                    else:
                        _pnl = 0.0
                    _bk += _pnl
                    _bk_rows.append({"date": _b.get("date", "?"), "bankroll": round(_bk, 2)})

                _bk_df = pd.DataFrame(_bk_rows)
                _peak = _STARTING_BK
                _peak_idx = 0
                _max_dd = 0.0
                _trough_idx = 0
                _dd_peak_idx = 0
                _cur_peak = _STARTING_BK
                _cur_peak_i = 0
                for i, row in _bk_df.iterrows():
                    if row["bankroll"] > _cur_peak:
                        _cur_peak = row["bankroll"]
                        _cur_peak_i = i
                    dd = _cur_peak - row["bankroll"]
                    if dd > _max_dd:
                        _max_dd = dd
                        _trough_idx = i
                        _dd_peak_idx = _cur_peak_i

                _peak_bk = _bk_df["bankroll"].max()
                _current_bk = _bk_df["bankroll"].iloc[-1]
                _max_dd_pct = (_max_dd / _bk_df.at[_dd_peak_idx, "bankroll"] * 100) if _max_dd > 0 else 0

                import plotly.graph_objects as _go_bk
                _fig_bk = _go_bk.Figure()
                _fig_bk.add_trace(_go_bk.Scatter(
                    x=_bk_df["date"], y=_bk_df["bankroll"],
                    mode="lines+markers",
                    line=dict(color="#00ff88", width=2),
                    marker=dict(size=5),
                    name="Bankroll",
                ))
                _fig_bk.add_hline(y=_STARTING_BK, line_dash="dot",
                                   line_color="rgba(255,255,255,0.3)",
                                   annotation_text="Start $1,000")
                if _max_dd > 0:
                    _peak_date   = _bk_df.at[_dd_peak_idx, "date"]
                    _trough_date = _bk_df.at[_trough_idx, "date"]
                    _fig_bk.add_vrect(
                        x0=_peak_date, x1=_trough_date,
                        fillcolor="rgba(255,60,60,0.12)",
                        line_width=0,
                        annotation_text=f"Max DD ${_max_dd:.0f}",
                        annotation_position="top left",
                        annotation_font_color="#ff6060",
                    )
                _fig_bk.update_layout(
                    title="Bankroll Over Time", height=280, **PLOT_LAYOUT
                )
                st.plotly_chart(_fig_bk, use_container_width=True, config={"responsive": True})

                _sm1, _sm2, _sm3, _sm4, _sm5 = st.columns(5)
                _sm1.metric("Starting Bankroll", f"${_STARTING_BK:,.0f}")
                _sm2.metric("Current Bankroll",  f"${_current_bk:,.2f}",
                            delta=f"${_current_bk - _STARTING_BK:+,.2f}")
                _sm3.metric("Peak Bankroll",     f"${_peak_bk:,.2f}")
                _sm4.metric("Max Drawdown $",    f"${_max_dd:,.2f}")
                _sm5.metric("Max Drawdown %",    f"{_max_dd_pct:.1f}%")

    else:
        st.info("📊 Charts will appear once you have settled bets.")


# ── CLV & ROI Tab ─────────────────────────────────────────────────────────────
def render_clv_tab():
    """Full CLV & ROI analysis dashboard — measures if the model is actually working."""
    from bet_tracker import load_bets, get_stats
    import plotly.graph_objects as go
    import plotly.express as px

    st.markdown("## 📈 CLV & ROI Analysis")
    st.caption("Closing Line Value (CLV) is the gold standard for measuring edge quality. Consistent positive CLV = real edge, not luck.")

    _uid = st.session_state.get("user_id")
    bets = load_bets(user_id=_uid)
    if not bets:
        st.info("📭 No bets logged yet. Start logging bets in the Tracker tab to see CLV analysis.")
        return

    stats = get_stats(user_id=_uid)

    # ── CLV Hero Metrics ──────────────────────────────────────────────────────
    clv_bets = [b for b in bets if b.get("clv") is not None]
    clv_vals = [float(b["clv"]) for b in clv_bets]
    settled  = [b for b in bets if b.get("result") in ("win", "loss")]

    avg_clv       = round(sum(clv_vals) / len(clv_vals), 2) if clv_vals else None
    clv_pos_rate  = round(100 * sum(1 for c in clv_vals if c > 0) / len(clv_vals), 1) if clv_vals else None
    model_edge    = stats.get("roi", 0.0)
    expected_roi  = round(avg_clv * 0.85, 2) if avg_clv else None  # CLV → ROI conversion ~85%

    h1, h2, h3, h4, h5 = st.columns(5)
    clv_color = "#00ff88" if (avg_clv or 0) > 0 else "#ff6060"
    h1.metric("Avg CLV", f"{avg_clv:+.2f}%" if avg_clv is not None else "—",
              help="Average Closing Line Value. Positive = you consistently beat the closing market.")
    h2.metric("CLV Positive Rate", f"{clv_pos_rate:.0f}%" if clv_pos_rate is not None else "—",
              help="% of bets where you beat the closing line. >50% = long-term edge.")
    h3.metric("Bets with CLV", len(clv_bets))
    h4.metric("Actual ROI", f"{model_edge:+.1f}%",
              delta="live" if model_edge >= 0 else None)
    h5.metric("CLV-Implied ROI", f"{expected_roi:+.1f}%" if expected_roi is not None else "—",
              help="Estimated ROI from CLV (CLV × 0.85). Matches actual ROI if model is well-calibrated.")

    st.divider()

    # ── CLV Over Time (rolling) ────────────────────────────────────────────────
    if clv_bets:
        st.markdown("### 📉 CLV Trend Over Time")
        clv_df = pd.DataFrame([
            {"date": b["date"], "clv": float(b["clv"]), "sport": b.get("sport","?"), "player": b.get("player","?")}
            for b in clv_bets
        ])
        clv_df = clv_df.sort_values("date")
        clv_df["rolling_clv"] = clv_df["clv"].rolling(window=10, min_periods=1).mean()
        clv_df["cumulative_clv"] = clv_df["clv"].cumsum()
        clv_df["bet_num"] = range(1, len(clv_df) + 1)

        col_l, col_r = st.columns(2)
        with col_l:
            fig_roll = go.Figure()
            fig_roll.add_trace(go.Bar(
                x=clv_df["bet_num"], y=clv_df["clv"],
                name="CLV per bet",
                marker_color=["rgba(0,255,136,0.5)" if c > 0 else "rgba(255,96,96,0.5)" for c in clv_df["clv"]],
            ))
            fig_roll.add_trace(go.Scatter(
                x=clv_df["bet_num"], y=clv_df["rolling_clv"],
                name="10-bet rolling avg", line=dict(color="#00d4ff", width=2),
            ))
            fig_roll.add_hline(y=0, line_dash="dot", line_color="rgba(255,255,255,0.3)")
            fig_roll.update_layout(
                title="CLV per Bet + 10-Bet Rolling Average",
                xaxis_title="Bet #", yaxis_title="CLV (%)",
                height=260, **PLOT_LAYOUT
            )
            st.plotly_chart(fig_roll, use_container_width=True, config={"responsive": True})

        with col_r:
            fig_cum = go.Figure()
            fig_cum.add_trace(go.Scatter(
                x=clv_df["bet_num"], y=clv_df["cumulative_clv"],
                name="Cumulative CLV",
                fill="tozeroy",
                line=dict(color="#a855f7", width=2),
                fillcolor="rgba(168,85,247,0.15)",
            ))
            fig_cum.add_hline(y=0, line_dash="dot", line_color="rgba(255,255,255,0.3)")
            fig_cum.update_layout(
                title="Cumulative CLV (Edge Accumulation)",
                xaxis_title="Bet #", yaxis_title="Cumulative CLV (%)",
                height=260, **PLOT_LAYOUT
            )
            st.plotly_chart(fig_cum, use_container_width=True, config={"responsive": True})

    # ── CLV by Sport ──────────────────────────────────────────────────────────
    if clv_bets:
        st.divider()
        st.markdown("### 🏆 Edge Quality by Sport & Market")
        col_sp, col_mk = st.columns(2)

        # By sport
        with col_sp:
            sp_clv = {}
            for b in clv_bets:
                sp = b.get("sport", "?")
                sp_clv.setdefault(sp, []).append(float(b["clv"]))
            sp_rows = [{"Sport": sp, "Avg CLV": round(sum(v)/len(v), 2), "Bets": len(v),
                        "% Positive": round(100*sum(1 for x in v if x>0)/len(v), 0)}
                       for sp, v in sp_clv.items() if len(v) >= 2]
            sp_rows.sort(key=lambda r: r["Avg CLV"], reverse=True)
            if sp_rows:
                fig_sp = px.bar(
                    pd.DataFrame(sp_rows), x="Sport", y="Avg CLV",
                    color="Avg CLV", color_continuous_scale=["#ff6060","#ffaa00","#00ff88"],
                    title="Avg CLV by Sport", text="Avg CLV",
                )
                fig_sp.update_traces(texttemplate="%{text:+.2f}%", textposition="outside")
                fig_sp.update_layout(height=260, coloraxis_showscale=False, **PLOT_LAYOUT)
                st.plotly_chart(fig_sp, use_container_width=True, config={"responsive": True})

        # By market
        with col_mk:
            mk_clv = {}
            for b in clv_bets:
                # Extract market from prop string (e.g. "pitcher_strikeouts O6.5")
                prop_str = b.get("prop", "")
                mkt = prop_str.split(" ")[0] if prop_str else "unknown"
                # Clean up common suffixes
                for suffix in [" O", " U", " [", "\n"]:
                    mkt = mkt.split(suffix)[0]
                mk_clv.setdefault(mkt, []).append(float(b["clv"]))
            mk_rows = [{"Market": mk.replace("_", " ").title(), "Avg CLV": round(sum(v)/len(v), 2), "Bets": len(v)}
                       for mk, v in mk_clv.items() if len(v) >= 3]
            mk_rows.sort(key=lambda r: r["Avg CLV"], reverse=True)
            if mk_rows:
                fig_mk = px.bar(
                    pd.DataFrame(mk_rows[:12]), x="Market", y="Avg CLV",
                    color="Avg CLV", color_continuous_scale=["#ff6060","#ffaa00","#00ff88"],
                    title="Avg CLV by Market (min 3 bets)", text="Avg CLV",
                )
                fig_mk.update_traces(texttemplate="%{text:+.2f}%", textposition="outside")
                fig_mk.update_layout(height=260, coloraxis_showscale=False, **PLOT_LAYOUT)
                st.plotly_chart(fig_mk, use_container_width=True, config={"responsive": True})

    # ── Win Rate vs Expected ──────────────────────────────────────────────────
    if settled:
        st.divider()
        st.markdown("### 🎯 Actual vs Expected Win Rate")
        st.caption("If the model is well-calibrated, actual win rate should track expected win rate over time.")

        # Per-sport win rate vs expected
        sp_wr = {}
        for b in settled:
            sp = b.get("sport", "?")
            win = b.get("result") == "win"
            sp_wr.setdefault(sp, {"wins": 0, "total": 0, "exp_wins": 0.0})
            sp_wr[sp]["total"] += 1
            if win:
                sp_wr[sp]["wins"] += 1

        wr_rows = []
        for sp, d in sp_wr.items():
            if d["total"] < 3:
                continue
            actual_wr = round(100 * d["wins"] / d["total"], 1)
            wr_rows.append({"Sport": sp, "Actual Win%": actual_wr,
                             "Bets": d["total"], "Wins": d["wins"]})

        if wr_rows:
            wr_df = pd.DataFrame(wr_rows)
            fig_wr = go.Figure()
            fig_wr.add_trace(go.Bar(
                x=wr_df["Sport"], y=wr_df["Actual Win%"],
                name="Actual Win %",
                marker_color="rgba(0,255,136,0.7)",
                text=[f"{v:.1f}%" for v in wr_df["Actual Win%"]],
                textposition="outside",
            ))
            fig_wr.add_hline(y=50, line_dash="dot", line_color="rgba(255,255,255,0.4)",
                             annotation_text="50% baseline")
            fig_wr.update_layout(
                title="Win Rate by Sport (settled bets)",
                yaxis_title="Win %", height=260, **PLOT_LAYOUT
            )
            st.plotly_chart(fig_wr, use_container_width=True, config={"responsive": True})

    # ── Bankroll Growth Chart ──────────────────────────────────────────────────
    if settled:
        st.divider()
        st.markdown("### 💰 Bankroll Growth")

        bk_df = pd.DataFrame([
            {"date": b["date"], "profit": float(b.get("profit") or 0), "sport": b.get("sport","?")}
            for b in sorted(settled, key=lambda x: x["date"])
        ])
        bk_df["cumulative"] = bk_df["profit"].cumsum()
        bk_df["bet_num"] = range(1, len(bk_df) + 1)

        fig_bk = go.Figure()
        fig_bk.add_trace(go.Scatter(
            x=bk_df["bet_num"], y=bk_df["cumulative"],
            mode="lines+markers",
            name="Bankroll P&L",
            line=dict(color="#00ff88", width=2),
            fill="tozeroy",
            fillcolor="rgba(0,255,136,0.08)",
            marker=dict(size=4),
        ))
        fig_bk.add_hline(y=0, line_dash="dot", line_color="rgba(255,255,255,0.3)")
        fig_bk.update_layout(
            title="Cumulative P&L Over All Bets",
            xaxis_title="Bet #", yaxis_title="Profit ($)",
            height=270, **PLOT_LAYOUT
        )
        st.plotly_chart(fig_bk, use_container_width=True, config={"responsive": True})

        # Drawdown chart
        bk_df["peak"] = bk_df["cumulative"].cummax()
        bk_df["drawdown"] = bk_df["cumulative"] - bk_df["peak"]
        max_dd = bk_df["drawdown"].min()
        current_dd = bk_df["drawdown"].iloc[-1]

        d1, d2 = st.columns(2)
        d1.metric("Max Drawdown", f"${max_dd:.2f}", delta=f"Current: ${current_dd:.2f}",
                  delta_color="inverse")
        d2.metric("Peak P&L", f"${bk_df['peak'].iloc[-1]:.2f}")

    # ── Market Edge Calibration (item 5) ──────────────────────────────────────
    if settled:
        st.divider()
        st.markdown("### 🔬 Market Edge Calibration")
        st.caption("Which markets is the model actually finding real edge in? Sorts by CLV to reveal where the signal is real vs noise.")

        mkt_data: dict = {}
        for b in settled:
            prop_str = b.get("prop", "")
            mkt_raw  = prop_str.split(" ")[0].strip() if prop_str else "unknown"
            for suf in [" O", " U", " [", "[", "\n", "(", ")"]:
                mkt_raw = mkt_raw.split(suf)[0]
            mkt_raw = mkt_raw.replace("_", " ").title()

            win   = b.get("result") == "win"
            clv_v = b.get("clv") or b.get("opening_clv")
            if mkt_raw not in mkt_data:
                mkt_data[mkt_raw] = {"wins": 0, "total": 0, "clv_vals": [], "profit": 0.0}
            mkt_data[mkt_raw]["total"] += 1
            if win: mkt_data[mkt_raw]["wins"] += 1
            if clv_v is not None: mkt_data[mkt_raw]["clv_vals"].append(float(clv_v))
            mkt_data[mkt_raw]["profit"] += float(b.get("profit") or 0)

        cal_rows = []
        for mkt, d in mkt_data.items():
            if d["total"] < 3: continue
            wr      = round(100 * d["wins"] / d["total"], 1)
            avg_clv = round(sum(d["clv_vals"]) / len(d["clv_vals"]), 2) if d["clv_vals"] else None
            roi_pct = round(d["profit"] / max(d["total"], 1), 2)
            verdict = ("✅ Trust" if (avg_clv or 0) >= 1.5 and wr >= 50
                       else "🟡 Monitor" if (avg_clv or 0) >= 0
                       else "🔴 Avoid")
            cal_rows.append({
                "Market":   mkt,
                "Bets":     d["total"],
                "Win %":    f"{wr}%",
                "Avg CLV":  f"{avg_clv:+.2f}%" if avg_clv is not None else "—",
                "Avg P&L":  f"${roi_pct:+.2f}",
                "Verdict":  verdict,
            })

        if cal_rows:
            cal_rows.sort(key=lambda r: float(r["Avg CLV"].replace("%","").replace("—","0") or "0"), reverse=True)
            cal_df = pd.DataFrame(cal_rows)
            st.dataframe(cal_df, use_container_width=True, hide_index=True)
            st.caption("Min 3 bets per market. Avg P&L = average profit per bet. CLV data may be partial for recent bets.")
        else:
            st.info("Need 3+ settled bets per market for calibration data.")

    # ── CLV Data Table ────────────────────────────────────────────────────────
    if clv_bets:
        st.divider()
        st.markdown("### 📋 CLV Breakdown (All Bets with CLV Data)")
        clv_table = pd.DataFrame([{
            "Date":   b["date"],
            "Sport":  b.get("sport", "?"),
            "Player": b.get("player", "?"),
            "Prop":   b.get("prop", "?"),
            "Odds":   b.get("odds"),
            "Result": b.get("result", "pending"),
            "CLV":    f"{float(b['clv']):+.2f}%",
            "Profit": f"${float(b.get('profit') or 0):+.2f}",
        } for b in sorted(clv_bets, key=lambda x: x["date"], reverse=True)])
        st.dataframe(clv_table, use_container_width=True, hide_index=True)


# ── Sport Tab ─────────────────────────────────────────────────────────────────
def render_sport_tab(sport: str, use_live: bool):
    cfg = SPORTS_CONFIG[sport]
    market_labels = cfg["market_labels"]

    df, data_source = load_data(sport, use_live)

    if df.empty:
        with st.sidebar:
            st.markdown(f"**{cfg['icon']} {sport} Filters**")
            st.markdown("**Prop Markets**")
            for mkt, label in cfg["market_labels"].items():
                st.checkbox(f"{label} *(no data yet)*", key=f"mkt_chk_{sport}_{mkt}", disabled=True)
            st.divider()
        if data_source == "unavailable":
            st.info(f"No live data for {sport} right now. Props post closer to game time.")
        else:
            st.error("No data available.")
        return

    # ── Hard filter: only keep markets configured for this sport ──
    allowed_markets = set(cfg["market_labels"].keys())
    df = df[df["market"].isin(allowed_markets)].copy()

    # ── Sport gradient banner — matches email sport section header exactly ──
    _SPORT_BANNER_META = {
        "MLB":  {"gradient": "linear-gradient(135deg,#1a472a 0%,#2d6a4f 100%)", "accent": "#52b788", "icon": "⚾"},
        "NBA":  {"gradient": "linear-gradient(135deg,#0a3161 0%,#1d4e8f 100%)", "accent": "#4dabf7", "icon": "🏀"},
        "WNBA": {"gradient": "linear-gradient(135deg,#7b1a1a 0%,#c8102e 100%)", "accent": "#ff8fa3", "icon": "🏀"},
        "NHL":  {"gradient": "linear-gradient(135deg,#003087 0%,#0057b8 100%)", "accent": "#74c0fc", "icon": "🏒"},
    }
    _smeta  = _SPORT_BANNER_META.get(sport, {"gradient":"linear-gradient(135deg,#1e1e2e,#2a2a4e)","accent":"#a78bfa","icon":"🎯"})
    _src_dot = {"live": "🟢", "scraped": "🔵", "static": "🟡"}.get(data_source, "⚪")
    _src_lbl = {"live": "Live · Odds API", "scraped": "Scraped · Action Network", "static": "Static CSV"}.get(data_source, data_source)
    st.markdown(f"""
<div style="background:{_smeta['gradient']};border-radius:16px 16px 0 0;
            padding:20px 24px 16px;margin-bottom:0;">
  <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;">
    <div>
      <span style="font-family:'Space Grotesk',sans-serif;font-size:22px;font-weight:800;
                   color:#fff;letter-spacing:-0.5px;">{_smeta['icon']} {sport}</span>
    </div>
    <div style="text-align:right;">
      <span style="font-size:12px;color:rgba(255,255,255,0.65);">{_src_dot} {_src_lbl}</span><br>
      <span style="font-size:12px;color:rgba(255,255,255,0.5);">{len(df)} props · refreshes every 5 min</span>
    </div>
  </div>
</div>
<div style="height:1px;background:#2a2a3a;margin-bottom:1rem;"></div>
""", unsafe_allow_html=True)

    # ── Line movement snapshot + steam alerts ──
    _alerts_gated = _tiers and not _tiers.can(_current_tier, "alerts")
    try:
        from line_movement import record_snapshot, get_movement_for_df, format_movement, snapshot_key
        # Only track movement on live/scraped data — static CSV has stale odds that cause false alerts
        if data_source == "static" or _alerts_gated:
            steam_alerts = []
            movement_map = {}
        else:
            _snap_data    = record_snapshot(df)
            steam_alerts  = [m for m in _snap_data.values() if m.get("is_steam")]
            # Opening line alerts: any move ≥ 10 pts since first snapshot
            line_alerts   = [m for m in _snap_data.values()
                             if not m.get("is_steam") and abs(m.get("diff", 0)) >= 10]

            if steam_alerts:
                st.warning(f"🔥 **{len(steam_alerts)} Steam Move(s) Detected!** Sharp money moving fast.")
                for alert in steam_alerts[:3]:
                    st.markdown(f"- **{alert['player']}** {alert['market']} | {alert['prev_odds']:+d} → {alert['curr_odds']:+d} ({format_movement(alert['diff'])})")

            if line_alerts:
                _dir_word = lambda d: ("📈 moved up" if d > 0 else "📉 moved down")
                with st.expander(f"📊 {len(line_alerts)} Line Movement(s) Since Opening", expanded=False):
                    for mv in sorted(line_alerts, key=lambda x: abs(x.get("diff",0)), reverse=True)[:10]:
                        diff = mv.get("diff", 0)
                        st.markdown(
                            f"**{mv['player']}** — {mv['market']} O{mv.get('line','')} "
                            f"| Opening: **{mv['prev_odds']:+d}** → Now: **{mv['curr_odds']:+d}** "
                            f"({_dir_word(diff)} {abs(diff)} pts)"
                        )
                # Only auto-push alerts that haven't been sent yet this session
                try:
                    from discord_bot import is_configured as dc_ok, send_steam_alert as dc_steam
                    from telegram_bot import is_configured as tg_ok, broadcast, fmt_steam_alert
                    sent_key = f"steam_sent_{sport}"
                    already_sent = st.session_state.get(sent_key, set())
                    new_alerts = [a for a in steam_alerts
                                  if f"{a['player']}|{a['curr_odds']}" not in already_sent]
                    for alert in new_alerts:
                        if dc_ok():
                            dc_steam(alert["player"], alert["market"],
                                     alert["prev_odds"], alert["curr_odds"], alert["diff"])
                        if tg_ok():
                            msg = fmt_steam_alert(alert["player"], alert["market"],
                                                  alert["prev_odds"], alert["curr_odds"], alert["diff"])
                            broadcast(msg)
                        already_sent.add(f"{alert['player']}|{alert['curr_odds']}")
                    if len(already_sent) > 500:
                        already_sent = set()  # reset to prevent unbounded growth
                    st.session_state[sent_key] = already_sent
                except Exception:
                    pass
            movement_map = get_movement_for_df(df)
    except Exception:
        movement_map = {}

    # ── Injury/lineup status ──
    try:
        from lineup_checker import enrich_df_with_status, get_mlb_pitcher_alert
        df = enrich_df_with_status(df, sport)
        has_status = True
    except Exception:
        has_status = False

    # ── Sharp line benchmark ──
    try:
        from sharp_line import get_sharp_lines
        sharp_map = get_sharp_lines(sport)
    except Exception:
        sharp_map = {}

    # ── Sidebar filters ──
    live_markets = set(df["market"].unique())
    # Always show all configured markets as buttons, gray out ones with no data
    all_configured_markets = list(cfg["market_labels"].keys())
    market_display = cfg["market_labels"]

    with st.sidebar:
        st.markdown(f"**{cfg['icon']} {sport} Filters**")

        st.markdown("**Prop Markets**")
        selected_markets = []
        for mkt in all_configured_markets:
            label = market_display[mkt]
            has_data = mkt in live_markets
            shadow_key = f"mkt_reset_{sport}_{mkt}"
            chk_key = f"mkt_chk_{sport}_{mkt}"
            # Use shadow key to pass reset value before widget is created
            default_val = st.session_state.pop(shadow_key, None)
            kwargs = {"value": default_val} if default_val is not None else {}
            suffix = "" if has_data else " *(no data yet)*"
            checked = st.checkbox(
                f"{label}{suffix}",
                key=chk_key,
                disabled=not has_data,
                **kwargs,
            )
            if checked and has_data:
                selected_markets.append(mkt)

        if not selected_markets:
            selected_markets = list(live_markets)

        st.divider()
        edge_threshold = st.slider("Min Edge", min_value=-0.05, max_value=0.12,
                                   value=0.0, step=0.005, format="%.3f",
                                   key=f"edge_slider_{sport}")
        confirmed_only = st.toggle("✅ Confirmed plays only",
                                   value=False, key=f"confirmed_{sport}",
                                   help="Show only plays where Power de-vig AND NegBin both agree on edge direction. Highest conviction plays.")

        bet_side = st.radio(
            "Bet Side",
            options=["Over", "Under", "Both"],
            index=0,
            key=f"bet_side_{sport}",
            horizontal=True,
            help="Over: show only over-side props. Under: flip to under odds/edge. Both: show all.",
        )
        all_teams = sorted(df["team"].dropna().unique())
        # Guard: if session_state has stale team names from a previous day, clear them
        _tkey_live = f"teams_{sport}"
        if _tkey_live in st.session_state:
            _valid = [t for t in st.session_state[_tkey_live] if t in all_teams]
            if not _valid:
                del st.session_state[_tkey_live]  # reset to default (all teams)
            elif len(_valid) < len(st.session_state[_tkey_live]):
                st.session_state[_tkey_live] = _valid  # drop stale teams
        selected_teams = st.multiselect("Matchups", options=all_teams, default=all_teams,
                                        key=f"teams_{sport}")
        player_search = st.text_input("Search Player", placeholder="e.g. Ohtani",
                                      key=f"search_{sport}")

        st.divider()
        shop_alerts_only = st.toggle(
            "🔔 Line shopping alerts only",
            value=False,
            key=f"shop_alerts_{sport}",
            help="Show only props where a 5+ pt better line is available at another book.",
        )

        hot_streaks_only = st.toggle(
            "🔥 Hot streaks only",
            value=False,
            key=f"hot_streaks_{sport}",
            help="Show only props where the player hit this line in 4+ of their last 5 games.",
        )

        # Reset button
        if st.button("🔄 Reset Filters", use_container_width=True, key=f"reset_{sport}"):
            # Write to shadow keys — read on next run before widgets instantiate
            for mkt in all_configured_markets:
                st.session_state[f"mkt_reset_{sport}_{mkt}"] = True
            for k in [f"teams_{sport}", f"search_{sport}", f"edge_slider_{sport}"]:
                if k in st.session_state:
                    del st.session_state[k]
            st.rerun()

    # ── Line shopping enrichment — add best_book / shop_alert columns to df ──
    try:
        from line_shopper import get_best_lines
        df = get_best_lines(df)
    except Exception:
        pass

    # ── ESPN injury enrichment — flag injured players ─────────────────────────
    try:
        from espn_service import flag_injured_props
        df = flag_injured_props(df, sport)
    except Exception:
        df["injury_status"] = ""

    # ── Streak enrichment — adds "streak" and "hot" columns ──────────────────
    # Only fetch for top-edge rows (max 30) to avoid blocking the page on 1000+
    # API calls. Remaining rows get empty streak so the table still renders fast.
    try:
        from streak_detector import get_streaks_for_df
        _top_idx = df.nlargest(30, "edge").index
        _streak_cache_key = f"_streaks_{sport}_{len(df)}"
        if _streak_cache_key not in st.session_state:
            with st.spinner("Loading player streaks..."):
                st.session_state[_streak_cache_key] = get_streaks_for_df(df.loc[_top_idx], sport)
        _streak_top = st.session_state[_streak_cache_key]
        df["streak"] = ""
        df["hot"] = False
        df.loc[_top_idx, "streak"] = _streak_top["streak"].values
        df.loc[_top_idx, "hot"]    = _streak_top["hot"].values
    except Exception:
        df["streak"] = ""
        df["hot"] = False

    cache_key = f"filtered_{sport}"
    bet_side = st.session_state.get(f"bet_side_{sport}", "Over")

    # For Under view: swap edge/odds columns so the rest of the pipeline sees
    # under_edge as "edge" and under_odds as "over_odds". A copy is used so the
    # raw df is unchanged for charts/SGPs that always show over-side.
    if bet_side == "Under" and "under_edge" in df.columns:
        df_view = df.copy()
        df_view["edge"]        = df_view["under_edge"].fillna(-1)
        df_view["over_odds"]   = df_view["under_odds"]
        df_view["book_implied"]= df_view["under_implied"].fillna(df_view["book_implied"])
        df_view["fair_est"]    = df_view["under_fair"].fillna(df_view["fair_est"])
        df_view["_side"]       = "Under"
    elif bet_side == "Both" and "under_edge" in df.columns:
        # Duplicate rows: original rows (over) + under rows with swapped columns
        df_over  = df.copy(); df_over["_side"]  = "Over"
        df_under = df.copy()
        df_under["edge"]        = df_under["under_edge"].fillna(-1)
        df_under["over_odds"]   = df_under["under_odds"]
        df_under["book_implied"]= df_under["under_implied"].fillna(df_under["book_implied"])
        df_under["fair_est"]    = df_under["under_fair"].fillna(df_under["fair_est"])
        df_under["_side"]       = "Under"
        df_view = pd.concat([df_over, df_under], ignore_index=True)
    else:
        df_view = df.copy()
        df_view["_side"] = "Over"

    _conf_mask = (df_view["edge_confirmed"] == True) if (confirmed_only and "edge_confirmed" in df_view.columns) else pd.Series(True, index=df_view.index)
    _shop_mask = (df_view["shop_alert"] == True) if (shop_alerts_only and "shop_alert" in df_view.columns) else pd.Series(True, index=df_view.index)
    _hot_mask  = (df_view["hot"] == True) if (hot_streaks_only and "hot" in df_view.columns) else pd.Series(True, index=df_view.index)
    filtered = df_view[
        (df_view["market"].isin(selected_markets))
        & (df_view["edge"] >= edge_threshold)
        & (df_view["team"].isin(selected_teams))
        & (df_view["player"].str.contains(player_search, case=False, na=False))
        & _conf_mask
        & _shop_mask
        & _hot_mask
    ].sort_values("edge", ascending=False).copy()
    st.session_state[cache_key] = filtered
    st.session_state[f"edge_{sport}"] = edge_threshold

    # ── Pre-compute confidence scores for all filtered rows ──────────────────
    _uid = st.session_state.get("user_id")
    _clv_avg_global = get_clv_avg(n_recent=30, user_id=_uid)  # shared CLV history for all rows

    def _row_confidence(row) -> int:
        return edge_confidence_score(
            edge=float(row.get("edge", 0)),
            fair_est=float(row.get("fair_est", 0.5)),
            edge_confirmed=bool(row.get("edge_confirmed", False)),
            n_books=int(row.get("n_books", 1)),
            over_odds=float(row.get("over_odds", -110)),
            clv_avg=_clv_avg_global,
        )

    if len(filtered) > 0:
        filtered = filtered.copy()
        filtered["confidence"] = filtered.apply(_row_confidence, axis=1)
        filtered = filtered.sort_values(["confidence", "edge"], ascending=False)

    # ── KPIs ──
    st.markdown("### 📊 Board Overview")
    k1, k2, k3, k4 = st.columns(4)
    avg_edge = filtered["edge"].mean() if len(filtered) > 0 else 0.0
    best = filtered.iloc[0] if len(filtered) > 0 else None
    k1.metric("Total Props", len(df))
    k2.metric("Value Bets", len(filtered),
              delta=f"{len(filtered)/len(df):.1%} of board" if len(df) else None)
    k3.metric("Avg Edge", f"{avg_edge:.2%}")
    if best is not None:
        best_conf = int(best.get("confidence", 0))
        best_label, _ = confidence_label(best_conf)
        k4.metric("Best Play", best["player"], delta=f"{best_label} · {best_conf}/100")
    else:
        k4.metric("Best Play", "—")

    # ── Best Bet of the Day widget ────────────────────────────────────────────
    if best is not None:
        best_conf  = int(best.get("confidence", 0))
        best_label, best_color = confidence_label(best_conf)
        best_prop  = market_labels.get(best.get("market",""), best.get("market",""))
        best_odds  = int(best.get("over_odds", 0))
        best_odds_fmt = f"+{best_odds}" if best_odds > 0 else str(best_odds)
        best_edge  = float(best.get("edge", 0))
        best_fair  = float(best.get("fair_est", 0.5))
        confirmed_badge = " ✅ Both models agree" if best.get("edge_confirmed") else ""
        _best_streak = best.get("streak", "")
        _streak_badge_html = (
            f' <span style="background:#2d1a00;border:1px solid #ff8c00;border-radius:12px;'
            f'padding:1px 8px;font-size:0.78rem;color:#ff8c00;font-weight:700;'
            f'vertical-align:middle;">{_best_streak}</span>'
            if _best_streak else ""
        )
        bar_pct = best_conf  # 0–100

        st.markdown(f"""
<div style="background:linear-gradient(135deg,rgba(0,255,136,0.07) 0%,rgba(0,212,255,0.07) 100%);
            border:1px solid {best_color};border-radius:14px;padding:1.2rem 1.5rem;margin:0.8rem 0;">
  <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:0.5rem;">
    <div>
      <span style="font-size:0.75rem;color:#888;text-transform:uppercase;letter-spacing:1px;">🏆 Best Bet of the Day</span><br>
      <span style="font-size:1.3rem;font-weight:700;color:#fff;">{best['player']}</span>{_streak_badge_html}
      <span style="font-size:0.95rem;color:#aaa;margin-left:0.5rem;">{best_prop} O{best.get('line','')} · {best_odds_fmt}</span>
    </div>
    <div style="text-align:right;">
      <span style="font-size:1.6rem;font-weight:800;color:{best_color};">{best_conf}</span>
      <span style="font-size:0.8rem;color:#888;">/100</span><br>
      <span style="font-size:0.8rem;color:{best_color};font-weight:600;">{best_label}</span>
    </div>
  </div>
  <div style="margin-top:0.7rem;background:rgba(255,255,255,0.08);border-radius:6px;height:6px;overflow:hidden;">
    <div style="width:{bar_pct}%;height:100%;background:linear-gradient(90deg,{best_color},{best_color}99);border-radius:6px;"></div>
  </div>
  <div style="margin-top:0.5rem;font-size:0.8rem;color:#aaa;">
    Edge <b style="color:{best_color};">+{best_edge:.2%}</b> ·
    Fair <b style="color:#fff;">{best_fair:.1%}</b> ·
    Game: <b style="color:#ccc;">{best.get('team','')}</b>{confirmed_badge}
  </div>
</div>
""", unsafe_allow_html=True)

    st.divider()

    # ── Game Lines ──
    with st.expander("📋 Today's Game Lines (Moneyline · Spread · Total)", expanded=False):
        if _tiers and not _tiers.can(_current_tier, "game_lines"):
            import auth_ui as _aui
            _aui.show_upgrade_modal("standard", key=f"game_lines_{sport}")
        else:
            try:
                from odds_client import get_game_lines
                gl = _get_game_lines_cached(sport)
            except Exception:
                gl = pd.DataFrame()

            if gl.empty:
                st.info("Game lines unavailable right now.")
            else:
                def _fmt_ml(v):
                    if v is None: return "—"
                    return f"+{int(v)}" if v > 0 else str(int(v))
                def _fmt_spread(line, odds):
                    if line is None: return "—"
                    sign = "+" if line > 0 else ""
                    odds_str = f" ({_fmt_ml(odds)})" if odds else ""
                    return f"{sign}{line}{odds_str}"
                def _fmt_total(total, over, under):
                    if total is None: return "—"
                    o = _fmt_ml(over) if over else "—"
                    u = _fmt_ml(under) if under else "—"
                    return f"O/U {total}  (O {o} / U {u})"
                def _fmt_pct(v):
                    return f"{int(v)}%" if v is not None and pd.notna(v) else None

                has_team_totals = "away_team_total" in gl.columns and gl["away_team_total"].notna().any()
                has_public = "ml_away_public" in gl.columns and gl["ml_away_public"].notna().any()

                for _, g in gl.iterrows():
                    c1, c2, c3, c4 = st.columns([2, 1, 1, 2])
                    c1.markdown(f"**{g['matchup']}**  \n🕐 {g.get('time','') or '—'} UTC")
                    # Moneyline + optional public %
                    away_pub = _fmt_pct(g.get("ml_away_public")) if has_public else None
                    home_pub = _fmt_pct(g.get("ml_home_public")) if has_public else None
                    away_pub_str = f" _{away_pub} public_" if away_pub else ""
                    home_pub_str = f" _{home_pub} public_" if home_pub else ""
                    c2.markdown(f"**ML**  \n{g['away']}: {_fmt_ml(g['away_ml'])}{away_pub_str}  \n{g['home']}: {_fmt_ml(g['home_ml'])}{home_pub_str}")
                    c3.markdown(f"**Spread**  \n{g['away']}: {_fmt_spread(g['away_spread'], g['away_spread_odds'])}  \n{g['home']}: {_fmt_spread(g['home_spread'], g['home_spread_odds'])}")
                    # Total + optional team totals
                    if has_team_totals and g.get("away_team_total") and g.get("home_team_total"):
                        c4.markdown(
                            f"**Total**  \n{_fmt_total(g['total'], g['over_odds'], g['under_odds'])}  \n"
                            f"**Team Totals:** {g['away']} {g['away_team_total']} · {g['home']} {g['home_team_total']}"
                        )
                    else:
                        c4.markdown(f"**Total**  \n{_fmt_total(g['total'], g['over_odds'], g['under_odds'])}")
                    st.divider()

    # ── AI Summary ──
    if GROQ_API_KEY and len(filtered) > 0:
        with st.expander("🤖 AI Board Summary", expanded=False):
            if _tiers and not _tiers.can(_current_tier, "ai_analysis"):
                import auth_ui as _aui
                _aui.show_upgrade_modal("premium", key=f"ai_{sport}")
            elif st.button("Generate Summary", key=f"summary_{sport}"):
                stats = {
                    "sport": sport,
                    "total_value_bets": len(filtered),
                    "avg_edge": round(avg_edge, 4),
                    "top_edge": round(filtered["edge"].max(), 4),
                    "top_player": filtered.iloc[0]["player"],
                    "markets_covered": filtered["market"].nunique(),
                }
                with st.spinner("Asking Groq..."):
                    try:
                        summary = run_ai_summary(stats)
                        import html as _html
                        st.markdown(f'<div class="ai-box">{_html.escape(summary)}</div>', unsafe_allow_html=True)
                    except Exception as e:
                        st.error(f"AI error: {e}")

    # ── Main table ──
    st.markdown(f"### 🎯 Value Bets ({len(filtered)} plays)")

    if len(filtered) == 0:
        st.warning("No value bets match your filters. Try lowering the edge threshold.")
    else:
        from line_movement import snapshot_key, format_movement
        bankroll = st.session_state.get("bankroll_input", 1000.0)
        kelly_mult = st.session_state.get("kelly_mult", 0.25)
        # Pull persisted settings for unit-size-scaled Kelly display
        _persisted_settings = st.session_state.get("settings", load_settings())
        _unit_size_display = float(_persisted_settings.get("unit_size", 10.0))
        # Use saved kelly_multiplier if set (overrides sidebar slider when saved)
        _saved_kelly_mult = float(_persisted_settings.get("kelly_multiplier", kelly_mult))

        _show_side_col = "_side" in filtered.columns and filtered["_side"].nunique() > 1
        base_cols = ["player", "team", "market", "line", "over_odds", "book_implied", "fair_est", "edge"]
        if _show_side_col:
            base_cols = ["_side"] + base_cols
        display_df = filtered[[c for c in base_cols if c in filtered.columns]].copy()
        if "_side" in display_df.columns:
            display_df = display_df.rename(columns={"_side": "Side"})
        display_df["market"] = display_df["market"].map(lambda k: market_labels.get(k, k))

        # Confidence score (0–100) — already computed above, wire it in
        if "confidence" in filtered.columns:
            display_df["Conf"] = filtered["confidence"].apply(
                lambda s: f"{int(s)}/100")

        # Dynamic Kelly stake — scaled by unit size from settings
        def _kelly_display(r):
            try:
                odds = r['over_odds']
                fair = r['fair_est']
                if odds is None or fair is None:
                    return "—"
                odds = float(odds)
                fair = float(fair)
                if odds == 0 or pd.isna(odds) or pd.isna(fair):
                    return "—"
                raw = recommended_stake(fair, odds, bankroll, _saved_kelly_mult, clv_avg=_clv_avg_global)
                kelly_fraction_val = raw['recommended_pct'] / 100.0
                unit_dollar = kelly_fraction_val * _unit_size_display
                return f"${raw['stake']:.2f} (Kelly: ${unit_dollar:.2f})"
            except Exception:
                return "—"

        display_df["Kelly"] = filtered.apply(_kelly_display, axis=1)

        # Edge signal
        display_df["Signal"] = filtered["edge"].apply(edge_rating)

        # NegBin delta — shows how much overdispersion correction shifted the fair prob
        if "negbin_delta" in filtered.columns:
            def _nb_label(d):
                if abs(d) < 0.005:
                    return "—"
                return f"{d:+.1%} 📊" if d > 0 else f"{d:+.1%}"
            display_df["NB Δ"] = filtered["negbin_delta"].apply(_nb_label)
            display_df["NB Δ"].name = "NB Δ"

        # ── Line Shopping (item 2) — FD vs DK odds + Best Book tag ──
        if "fd_odds" in filtered.columns and "dk_odds" in filtered.columns:
            def _fmt_book_odds(v):
                if pd.isna(v) or v is None: return "—"
                return f"+{int(v)}" if v > 0 else str(int(v))

            def _best_book(row):
                fd  = row.get("fd_odds")
                dk  = row.get("dk_odds")
                if pd.isna(fd) or fd is None: return "DK" if (not pd.isna(dk) and dk is not None) else "—"
                if pd.isna(dk) or dk is None: return "FD"
                return "FD" if fd >= dk else "DK"   # higher american = better payout

            def _book_spread(row):
                fd = row.get("fd_odds"); dk = row.get("dk_odds")
                if pd.isna(fd) or pd.isna(dk) or fd is None or dk is None: return "—"
                diff = int(fd) - int(dk)
                if diff == 0: return "Equal"
                return f"FD {diff:+d}" if diff > 0 else f"DK {-diff:+d}"

            display_df["FD"] = filtered.apply(lambda r: _fmt_book_odds(r.get("fd_odds")), axis=1)
            display_df["DK"] = filtered.apply(lambda r: _fmt_book_odds(r.get("dk_odds")), axis=1)
            display_df["Bet At"] = filtered.apply(_best_book, axis=1)
            display_df["Spread"] = filtered.apply(_book_spread, axis=1)
            _has_line_shop = True
        else:
            _has_line_shop = False

        # Line movement
        def get_move(row):
            key = snapshot_key(row["player"], row["market"], row["line"])
            mv = movement_map.get(key, {})
            return format_movement(mv.get("diff", 0)) if mv else ""
        display_df["Move"] = filtered.apply(get_move, axis=1)

        # Sharp line vs best available
        def get_sharp(row):
            key = (row["player"].lower(), row["market"], row["line"])
            sl = sharp_map.get(key, {})
            if sl:
                return f"{sl['consensus_odds']:+d} ({sl['sharp_book']})"
            return ""
        display_df["Sharp Line"] = filtered.apply(get_sharp, axis=1)

        # Injury status
        has_nb   = "NB Δ" in display_df.columns
        has_conf = "Conf" in display_df.columns

        _shop_cols = (["FD", "DK", "Bet At", "Spread"] if _has_line_shop else [])

        if has_status and "status_label" in filtered.columns:
            display_df["Status"] = filtered["status_label"]
            col_names = ["Player", "Team/Game", "Prop", "Line", "Odds",
                         "Book Implied", "Fair Est.", "Edge",
                         *(["Conf"] if has_conf else []),
                         "Kelly", "Signal",
                         *(["NB Δ"] if has_nb else []),
                         *_shop_cols,
                         "Move", "Sharp Line",
                         "Status"]
        else:
            col_names = ["Player", "Team/Game", "Prop", "Line", "Odds",
                         "Book Implied", "Fair Est.", "Edge",
                         *(["Conf"] if has_conf else []),
                         "Kelly", "Signal",
                         *(["NB Δ"] if has_nb else []),
                         *_shop_cols,
                         "Move", "Sharp Line"]

        display_df.columns = col_names
        for col in ["Book Implied", "Fair Est.", "Edge"]:
            display_df[col] = display_df[col].apply(
                lambda x: f"{x:.1%}" if pd.notna(x) else "N/A")
        display_df["Odds"] = display_df["Odds"].apply(
            lambda x: f"+{int(x)}" if pd.notna(x) and x > 0 else (f"{int(x)}" if pd.notna(x) else "N/A"))

        # Show MLB pitcher matchups above table
        if sport == "MLB":
            from lineup_checker import get_mlb_pitcher_alert
            matchups = filtered["team"].unique()[:4]
            pitcher_info = " | ".join([f"{m}: {get_mlb_pitcher_alert(m, sport)}" for m in matchups if get_mlb_pitcher_alert(m, sport)])
            if pitcher_info:
                st.caption(f"⚾ Probable pitchers: {pitcher_info}")

        def highlight_edge(val):
            try:
                num = float(val.strip("%")) / 100
                if num >= 0.05:
                    return "background-color: rgba(0,255,136,0.2); color: #00ff88; font-weight: bold"
                elif num >= 0.03:
                    return "background-color: rgba(0,255,136,0.1); color: #00dd77"
                elif num > 0:
                    return "background-color: rgba(255,215,0,0.1); color: #ffd700"
                return "background-color: rgba(255,60,60,0.1); color: #ff6060"
            except Exception:
                return ""

        st.dataframe(display_df.style.map(highlight_edge, subset=["Edge"]),
                     use_container_width=True, hide_index=True, height=440)

        # ── Line Shopping expander ────────────────────────────────────────────
        try:
            from line_shopper import build_shopping_summary
            if "shop_alert" in filtered.columns:
                _shop_df = build_shopping_summary(filtered)
                _n_alerts = len(_shop_df)
                _expander_label = (
                    f"🔔 Line Shopping — {_n_alerts} alert(s) found"
                    if _n_alerts > 0
                    else "🔔 Line Shopping — no alerts (all books within 5 pts)"
                )
                with st.expander(_expander_label, expanded=(_n_alerts > 0)):
                    if _n_alerts > 0:
                        st.caption(
                            "Lines 5+ pts better than current odds — check these books before betting"
                        )
                        st.dataframe(_shop_df, use_container_width=True, hide_index=True)
                    else:
                        st.info(
                            "No significant line differences detected. "
                            "FanDuel and DraftKings are within 5 pts on all current props."
                        )
        except Exception:
            pass

        # ── Hot Streak expander ───────────────────────────────────────────────
        try:
            if "streak" in filtered.columns:
                _hot_rows = filtered[filtered["hot"] == True] if "hot" in filtered.columns else pd.DataFrame()
                _n_hot = len(_hot_rows)
                _streak_label = (
                    f"🔥 Hot Streaks — {_n_hot} player(s) on a run"
                    if _n_hot > 0
                    else "🔥 Hot Streaks — no players with 4/5 streak"
                )
                with st.expander(_streak_label, expanded=(_n_hot > 0)):
                    if _n_hot > 0:
                        st.caption("Players who exceeded this line in 4+ of their last 5 games")
                        _streak_display = _hot_rows[
                            [c for c in ["player", "team", "market", "line", "over_odds", "edge", "streak"]
                             if c in _hot_rows.columns]
                        ].copy()
                        _streak_display["market"] = _streak_display["market"].map(
                            lambda k: market_labels.get(k, k)
                        )
                        _streak_display.columns = [
                            {"player": "Player", "team": "Team/Game", "market": "Prop",
                             "line": "Line", "over_odds": "Odds", "edge": "Edge",
                             "streak": "Streak (last 5)"}.get(c, c)
                            for c in _streak_display.columns
                        ]
                        if "Odds" in _streak_display.columns:
                            _streak_display["Odds"] = _streak_display["Odds"].apply(
                                lambda x: f"+{int(x)}" if pd.notna(x) and x > 0 else (str(int(x)) if pd.notna(x) else "—")
                            )
                        if "Edge" in _streak_display.columns:
                            _streak_display["Edge"] = _streak_display["Edge"].apply(
                                lambda x: f"{x:.1%}" if pd.notna(x) else "—"
                            )
                        st.dataframe(_streak_display, use_container_width=True, hide_index=True)
                    else:
                        st.info("No players currently on a 4/5 hot streak for their listed line.")
        except Exception:
            pass

        # ── ESPN Injury Alerts ────────────────────────────────────────────────
        try:
            if "injury_status" in df.columns:
                _inj_rows = df[df["injury_status"].isin(["Out", "Doubtful", "Questionable"])]
                _n_inj = len(_inj_rows)
                _inj_label = (
                    f"🚑 Injury Alerts — {_n_inj} prop(s) with injured players"
                    if _n_inj > 0
                    else "🚑 Injury Alerts — no flagged injuries"
                )
                with st.expander(_inj_label, expanded=(_n_inj > 0)):
                    if _n_inj > 0:
                        st.caption("⚠️ These players have active injury flags from ESPN. Bet with caution.")
                        _inj_disp = _inj_rows[[c for c in ["player","team","market","line","over_odds","edge","injury_status"] if c in _inj_rows.columns]].copy()
                        _inj_disp["market"] = _inj_disp["market"].map(lambda k: market_labels.get(k, k))
                        _inj_disp.columns = [{"player":"Player","team":"Team/Game","market":"Prop","line":"Line","over_odds":"Odds","edge":"Edge","injury_status":"Injury Status"}.get(c,c) for c in _inj_disp.columns]
                        if "Odds" in _inj_disp.columns:
                            _inj_disp["Odds"] = _inj_disp["Odds"].apply(lambda x: f"+{int(x)}" if pd.notna(x) and x > 0 else (str(int(x)) if pd.notna(x) else "—"))
                        if "Edge" in _inj_disp.columns:
                            _inj_disp["Edge"] = _inj_disp["Edge"].apply(lambda x: f"{x:.1%}" if pd.notna(x) else "—")
                        def _inj_color(s):
                            colors = {"Out": "background-color:#ff4444;color:white", "Doubtful": "background-color:#ff8c00;color:white", "Questionable": "background-color:#ffd700;color:black"}
                            return [colors.get(v, "") for v in s]
                        st.dataframe(_inj_disp.style.apply(_inj_color, subset=["Injury Status"]) if "Injury Status" in _inj_disp.columns else _inj_disp, use_container_width=True, hide_index=True)
                    else:
                        st.info("No injury flags from ESPN for current props.")
        except Exception:
            pass

        # ── ESPN News Feed ────────────────────────────────────────────────────
        try:
            with st.expander(f"📰 ESPN News — {sport}", expanded=False):
                from espn_service import get_news
                _news = get_news(sport, limit=8)
                if _news:
                    for _item in _news:
                        st.markdown(f"**{_item['headline']}**")
                        if _item.get("description"):
                            st.caption(_item["description"])
                        if _item.get("link"):
                            st.markdown(f"[Read →]({_item['link']})&nbsp;&nbsp;<span style='color:#555;font-size:11px;'>{_item.get('published','')[:10]}</span>", unsafe_allow_html=True)
                        st.divider()
                else:
                    st.info("No ESPN news available right now.")
        except Exception:
            pass

        col_dl, col_email, col_tg = st.columns(3)
        with col_dl:
            csv = filtered.to_csv(index=False).encode("utf-8")
            st.download_button("📥 Download CSV", data=csv,
                               file_name=f"{sport.lower()}_value_bets.csv",
                               mime="text/csv", use_container_width=True,
                               key=f"dl_{sport}")
        with col_email:
            if st.button("📧 Email All Sports Slip", use_container_width=True, key=f"email_{sport}"):
                try:
                    import importlib
                    sys.path.insert(0, str(Path(__file__).parent.parent))
                    import send_daily_bets
                    importlib.reload(send_daily_bets)
                    with st.spinner("Scraping all sports…"):
                        results = send_daily_bets.send_email(all_sports=True)
                    sent = results.get("sent", [])
                    failed = results.get("failed", [])
                    st.success(f"✅ All-sports slip sent to {len(sent)} recipient(s): {', '.join(sent)}")
                    if failed:
                        st.warning(f"⚠️ Failed: {', '.join(f[0] for f in failed)}")
                except Exception as e:
                    st.error(f"Email error: {e}")

        with col_tg:
            from discord_bot import is_configured as dc_ok, send_daily_slip as dc_slip
            from telegram_bot import is_configured as tg_ok_btn, broadcast as tg_broadcast, fmt_daily_slip as tg_fmt
            dc_ready = dc_ok()
            tg_ready = tg_ok_btn()
            push_label = "📱 Push to Discord" if dc_ready else ("📱 Push to Telegram" if tg_ready else "📱 Push Alerts")
            push_ready = dc_ready or tg_ready
            if st.button(push_label, use_container_width=True, key=f"push_{sport}",
                         disabled=not push_ready,
                         help="Add DISCORD_WEBHOOK_URL or TELEGRAM credentials to .env"):
                try:
                    from parlay_builder import build_parlay_report
                    from bet_tracker import get_stats
                    report = build_parlay_report(filtered)
                    top_picks = filtered.head(10).to_dict("records")
                    for p in top_picks:
                        p["prop_label"] = market_labels.get(p.get("market",""), p.get("market",""))
                    for _k, parlay in report.get("parlays", {}).items():
                        for leg in parlay.get("legs", []):
                            leg["prop_label"] = market_labels.get(leg.get("market",""), leg.get("market",""))
                    _uid = st.session_state.get("user_id")
                    stats = get_stats(user_id=_uid)
                    record = {"wins": stats["wins"], "losses": stats["losses"], "roi": stats["roi"]}
                    sent = 0
                    if dc_ready:
                        ok = dc_slip(top_picks, report.get("parlays"), record, sport)
                        if ok: sent += 1
                    if tg_ready:
                        msg = tg_fmt(top_picks, report.get("parlays"), record)
                        res = tg_broadcast(msg)
                        sent += len(res["sent"])
                    st.success(f"✅ Pushed to {sent} channel(s)!")
                except Exception as e:
                    st.error(f"Push error: {e}")
            if not push_ready:
                st.caption("Add DISCORD_WEBHOOK_URL to .env")

        # ── Subscriber Manager ──
        with st.expander("👥 Manage Subscribers", expanded=False):
            from subscribers import load_subscribers, add_subscriber, remove_subscriber
            from telegram_bot import (load_tg_subscribers, add_tg_subscriber,
                                      remove_tg_subscriber, is_configured as tg_ok)

            tab_email, tab_tg = st.tabs(["📧 Email", "📱 Telegram"])

            with tab_email:
                subs = load_subscribers()
                if subs:
                    st.markdown(f"**{len(subs)} email subscriber(s):**")
                    for email in subs:
                        c1, c2 = st.columns([4, 1])
                        c1.markdown(f"📧 {email}")
                        if c2.button("Remove", key=f"rm_{email}_{sport}"):
                            ok, msg = remove_subscriber(email)
                            st.toast(msg)
                            st.rerun()
                else:
                    st.info("No email subscribers yet.")
                st.divider()
                with st.form(f"add_sub_{sport}", clear_on_submit=True):
                    new_email = st.text_input("Add email", placeholder="client@example.com")
                    if st.form_submit_button("➕ Add", use_container_width=True):
                        if new_email:
                            ok, msg = add_subscriber(new_email)
                            st.toast(msg)
                            st.rerun()

            with tab_tg:
                if not tg_ok():
                    st.warning("Telegram not configured. Run `python setup_telegram.py` to connect.")
                else:
                    tg_subs = load_tg_subscribers()
                    if tg_subs:
                        st.markdown(f"**{len(tg_subs)} Telegram subscriber(s):**")
                        for cid in tg_subs:
                            c1, c2 = st.columns([4, 1])
                            c1.markdown(f"📱 Chat ID: `{cid}`")
                            if c2.button("Remove", key=f"rm_tg_{cid}_{sport}"):
                                ok, msg = remove_tg_subscriber(cid)
                                st.toast(msg)
                                st.rerun()
                    else:
                        st.info("No Telegram subscribers yet.")
                    st.divider()
                    with st.form(f"add_tg_sub_{sport}", clear_on_submit=True):
                        new_cid = st.text_input("Add Telegram Chat ID",
                                                placeholder="e.g. 123456789",
                                                help="Subscriber must message your bot first, then run setup_telegram.py to find their ID")
                        if st.form_submit_button("➕ Add", use_container_width=True):
                            if new_cid:
                                ok, msg = add_tg_subscriber(new_cid.strip())
                                st.toast(msg)
                                st.rerun()
            st.markdown("")  # spacing

    # ── Parlay Builder ──
    if len(filtered) > 0:
        st.divider()
        st.markdown("### 🎰 Parlay Builder")
        if _tiers and not _tiers.can(_current_tier, "parlays"):
            st.markdown("""
            <div style='background:rgba(0,212,255,0.08);border:1px solid #00d4ff;
                        border-radius:12px;padding:1.5rem;text-align:center'>
                <h3>🔒 Standard Feature</h3>
                <p style='color:#aaa'>Upgrade to <strong>Standard</strong> ($9/mo) to unlock the Parlay Builder.</p>
            </div>
            """, unsafe_allow_html=True)
            if _SUPABASE_CONFIGURED:
                import auth_ui
                auth_ui.show_upgrade_modal("standard", key="parlays")
            return
        from parlay_builder import build_parlay_report

        stake = st.number_input("Stake per parlay ($)", min_value=1.0, max_value=10000.0,
                                value=10.0, step=5.0, key=f"stake_{sport}")

        # SGP pool: same market/team/player filters, no edge-threshold cut.
        sgp_pool = df[
            (df["market"].isin(selected_markets))
            & (df["team"].isin(selected_teams if selected_teams else df["team"].unique()))
            & (df["player"].str.contains(player_search, case=False, na=False) if player_search else True)
        ].copy()

        # ── Lazy SGP cache ────────────────────────────────────────────────────
        # Use session_state keyed by sport + data hash to avoid the Streamlit
        # @st.cache_data closure-collision bug (all sport tabs define identically-
        # coded nested functions → same cache namespace → wrong parlay returned).
        import hashlib as _hl

        def _df_hash(d: pd.DataFrame) -> str:
            try:
                key = str(round(d["edge"].sum(), 6)) + str(len(d)) + str(d["over_odds"].sum() if "over_odds" in d.columns else 0)
                return _hl.md5(key.encode()).hexdigest()[:12]
            except Exception:
                return "empty"

        _parlay_key = f"parlay_report_{sport}_{_df_hash(filtered)}_{_df_hash(sgp_pool)}_{stake}"
        # Expire cache after 5 min so stale parlays don't linger all day
        _parlay_ts_key = _parlay_key + "_ts"
        import time as _time
        _now = _time.time()
        if (_parlay_key not in st.session_state or
                _now - st.session_state.get(_parlay_ts_key, 0) > 300):
            with st.spinner("⚡ Building parlays & SGPs…"):
                try:
                    from odds_client import quota_exhausted as _qe
                    _gl_ok = not _qe()
                except Exception:
                    _gl_ok = True
                _gl_for_parlay = _get_game_lines_cached(sport) if _gl_ok else None
                st.session_state[_parlay_key] = build_parlay_report(
                    filtered, stake=stake, full_df=sgp_pool, sport=sport,
                    game_lines_df=_gl_for_parlay,
                )
                st.session_state[_parlay_ts_key] = _now
        report = st.session_state[_parlay_key]

        _gf = report.get("games_filtered", 0)
        if _gf:
            st.info(f"⏱️ **{_gf} game{'s' if _gf > 1 else ''} excluded** — already past the 50% mark. Props from those games are hidden to keep parlay legs betable.")

        st.markdown("#### 🏆 Top 20 Best Edge Candidates")
        st.caption("Top 5 per prop market within -300 to +300 odds — sorted by edge, best value first.")
        if report["top10"]:
            top_df = pd.DataFrame(report["top10"])
            # Ensure required columns exist with safe fallbacks
            if "market" not in top_df.columns:
                top_df["market"] = top_df.get("prop_label", top_df.get("prop", "unknown"))
            if "team" not in top_df.columns:
                top_df["team"] = ""
            if "book_implied" not in top_df.columns:
                top_df["book_implied"] = top_df.get("implied", 0.5)
            if "edge" not in top_df.columns:
                top_df["edge"] = 0.0
            if "fair_est" not in top_df.columns:
                top_df["fair_est"] = top_df.get("book_implied", 0.5)
            top_df["prop"] = top_df["market"].map(lambda k: market_labels.get(k, k))
            _display_cols = [c for c in ["player", "prop", "line", "team", "over_odds", "book_implied", "edge"] if c in top_df.columns]
            disp_df = top_df[_display_cols].copy()
            disp_df.columns = ["Player", "Prop", "Line", "Team/Game", "Odds", "Book Implied", "Edge"][:len(_display_cols)]
            if "Odds" in disp_df.columns:
                disp_df["Odds"] = disp_df["Odds"].apply(lambda x: f"+{int(x)}" if int(x) > 0 else f"{int(x)}")
            if "Book Implied" in disp_df.columns:
                disp_df["Book Implied"] = disp_df["Book Implied"].apply(lambda x: f"{x:.1%}")
            if "Edge" in disp_df.columns:
                disp_df["Edge"] = disp_df["Edge"].apply(lambda x: f"{x:.1%}")
            st.dataframe(disp_df, use_container_width=True, hide_index=True)

            # ── Manual Parlay Builder ─────────────────────────────────────────
            st.markdown("#### 🛠️ Manual Parlay Builder")
            st.caption("Select legs from the Top 20 above to build a custom parlay.")

            _top_rows = report["top10"]
            _leg_labels = [
                f"{r.get('player','?')} — {market_labels.get(r.get('market', r.get('prop_label', r.get('prop','?'))), r.get('market', r.get('prop_label', r.get('prop','?'))))} O{r.get('line',0.5)} "
                f"({'+'if int(r.get('over_odds',0))>0 else ''}{int(r.get('over_odds',0))}) "
                f"[Edge: {r.get('edge',0):+.1%}]"
                for r in _top_rows
            ]
            _label_to_row = dict(zip(_leg_labels, _top_rows))

            _parlay_key_ms = f"manual_parlay_sel_{sport}"
            # Filter out any stale defaults that no longer exist in current options
            _valid_defaults = [l for l in st.session_state.get(_parlay_key_ms, []) if l in _leg_labels]
            _selected_labels = st.multiselect(
                "Pick 2–20 legs:",
                options=_leg_labels,
                default=_valid_defaults,
                key=_parlay_key_ms,
                placeholder="Choose players from the Top 20…",
                max_selections=20,
            )
            _selected_rows = [_label_to_row[l] for l in _selected_labels if l in _label_to_row]

            if len(_selected_rows) >= 2:
                # ── Compute combined parlay ──
                from parlay_builder import parlay_payout, parlay_ev
                from edge_model import gaussian_copula_joint

                _legs_odds  = [int(r["over_odds"]) for r in _selected_rows]
                _payout     = parlay_payout(_legs_odds, stake)
                _ev         = parlay_ev(_selected_rows, stake)

                def _r_market(r):
                    return r.get("market", r.get("prop_label", r.get("prop", "prop")))
                def _r_player(r):
                    return r.get("player", "?")

                # Copula joint probability (accounts for correlations)
                _copula_legs = [{"fair_est": r.get("fair_est", r.get("book_implied", 0.5)),
                                  "market": _r_market(r),
                                  "player": _r_player(r)} for r in _selected_rows]
                _joint_prob  = gaussian_copula_joint(_copula_legs)
                _naive_prob  = 1.0
                for r in _selected_rows:
                    _naive_prob *= r.get("fair_est", r.get("book_implied", 0.5))

                # Display metrics
                _mc1, _mc2, _mc3, _mc4, _mc5 = st.columns(5)
                _mc1.metric("Legs", len(_selected_rows))
                _mc2.metric("Combined Odds", _payout.get("american_odds", "—"))
                _mc3.metric(f"Payout (${stake:.0f})", f"${_payout.get('payout', 0):.2f}")
                _mc4.metric("Joint Prob (Copula)", f"{_joint_prob:.2%}")
                _ev_dollars = _ev.get("ev_dollars", 0)
                _mc5.metric("EV", f"${_ev_dollars:+.2f}", delta_color="normal" if _ev_dollars >= 0 else "inverse")

                # Leg breakdown table
                _leg_rows = []
                for r in _selected_rows:
                    _o = int(r.get("over_odds", 0))
                    _mkt = _r_market(r)
                    _leg_rows.append({
                        "Player":    _r_player(r),
                        "Prop":      market_labels.get(_mkt, _mkt),
                        "Line":      r.get("line", 0.5),
                        "Odds":      f"+{_o}" if _o > 0 else str(_o),
                        "Fair Prob": f"{r.get('fair_est', r.get('book_implied', 0)):.1%}",
                        "Edge":      f"{r.get('edge', 0):+.1%}",
                        "Team/Game": r.get("team", ""),
                    })
                st.dataframe(pd.DataFrame(_leg_rows), use_container_width=True, hide_index=True)

                # Corr warning if same-player legs detected
                _players = [_r_player(r) for r in _selected_rows]
                if len(_players) != len(set(_players)):
                    st.warning("⚠️ Same-player legs detected — correlation penalty applied to joint probability.")
                if _naive_prob > 0 and _joint_prob < _naive_prob * 0.85:
                    st.info(f"📉 Correlation reduces joint prob from {_naive_prob:.2%} → {_joint_prob:.2%} "
                            f"({(_joint_prob/_naive_prob - 1)*100:.1f}%)")

                # Log to bet tracker button
                _combined_american = _payout.get("american_odds", "+100")
                try:
                    _combined_int = int(str(_combined_american).replace("+", ""))
                except (ValueError, TypeError):
                    _combined_int = 100  # fallback for "N/A" on very low-prob parlays
                if st.button("📝 Log This Parlay to Tracker", key=f"log_manual_parlay_{sport}"):
                    from bet_tracker import add_bet
                    _leg_desc = " + ".join(
                        f"{_r_player(r)} {market_labels.get(_r_market(r), _r_market(r))} O{r.get('line',0.5)}"
                        for r in _selected_rows
                    )
                    add_bet(
                        sport=sport,
                        player="Manual Parlay",
                        prop=f"{len(_selected_rows)}-Leg: {_leg_desc}",
                        line=0.0,
                        odds=_combined_int,
                        stake=stake,
                        notes=f"Manual parlay built from Top 20 | EV ${_ev_dollars:+.2f}",
                        is_parlay=True,
                    )
                    st.success("✅ Parlay logged to bet tracker!")

            elif len(_selected_rows) == 1:
                st.info("Select at least 2 legs to build a parlay.")

        else:
            st.info("No value plays found after edge filtering. Try lowering the Min Edge slider.")

        st.divider()
        st.markdown("""
<div style="display:flex;align-items:center;gap:10px;margin:8px 0 4px;">
  <span style="font-size:20px;">📋</span>
  <span style="font-size:18px;font-weight:800;color:#e2e8f0;letter-spacing:-0.3px;">Multi-Game Parlays</span>
</div>""", unsafe_allow_html=True)
        pos_games   = report.get("pos_edge_games", 0)
        total_games = report.get("total_games", 0)
        multi_possible = pos_games >= 3

        if not multi_possible:
            st.info(
                f"**{pos_games} game{'s' if pos_games != 1 else ''} with positive-edge plays today** "
                f"(out of {total_games} total). Need 3+ for a cross-game parlay."
                + (" 2-leg shown below." if pos_games == 2 else "")
            )

        # ── Multi-game parlays (2/3/4/5-leg) — stacked cards, mobile-friendly ──
        show_legs = [2, 3, 4, 5] if "2_leg" in report["parlays"] else [3, 4, 5]
        for n in show_legs:
            pkey = f"{n}_leg"
            if pkey not in report["parlays"]:
                needed = n - pos_games
                st.markdown(
                    f'<p style="color:#64748b;font-size:13px;margin:4px 0 12px;">'
                    f'🔒 {n}-Leg Parlay — need {needed} more game{"s" if needed!=1 else ""} with value plays.</p>',
                    unsafe_allow_html=True)
                continue

            p    = report["parlays"][pkey]
            pout = p["payout"]
            ev       = p.get("ev", {})
            ev_pct   = ev.get("ev_pct", 0)
            ev_sign  = "+" if ev_pct >= 0 else ""
            ev_col   = "#34d399" if ev_pct > 0 else "#ff6060"
            win_prob = ev.get("win_prob") or 0
            if not win_prob:
                _wp = 1.0
                for _l in p.get("legs", []):
                    _wp *= min(max(float(_l.get("fair_est") or 0.5), 0.001), 0.999)
                win_prob = round(_wp, 4)
            amer     = pout["american_odds"]
            amer_fmt = f"+{amer}" if isinstance(amer, (int, float)) and amer > 0 else str(amer)

            # Build legs HTML
            legs_html = ""
            for j, leg in enumerate(p["legs"], 1):
                prop     = market_labels.get(leg.get("market", ""), leg.get("market", ""))
                edge_val = leg.get("edge", 0)
                edge_col = "#34d399" if edge_val > 0 else "#ff6060"
                try:
                    odds_i   = int(leg["over_odds"])
                    odds_fmt = f"+{odds_i}" if odds_i > 0 else str(odds_i)
                except Exception:
                    odds_fmt = str(leg.get("over_odds", ""))
                conf = " ✅" if leg.get("edge_confirmed") else ""
                legs_html += f"""
<div style="display:flex;justify-content:space-between;align-items:flex-start;
            padding:10px 0;border-bottom:1px solid rgba(255,255,255,0.06);">
  <div style="flex:1;min-width:0;">
    <div style="color:#e2e8f0;font-size:14px;font-weight:600;
                white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">
      {j}. {leg['player']}{conf}
    </div>
    <div style="color:#94a3b8;font-size:12px;margin-top:2px;">
      {prop} O{leg.get('line','')}
      <span style="color:#a78bfa;font-weight:700;"> {odds_fmt}</span>
      &nbsp;·&nbsp;<span style="color:#64748b;">{leg.get('team','')}</span>
    </div>
  </div>
  <div style="margin-left:12px;flex-shrink:0;">
    <span style="color:{edge_col};font-size:13px;font-weight:700;">{ev_sign if edge_val>=0 else ''}{edge_val:.1%}</span>
  </div>
</div>"""

            st.markdown(f"""
<div style="background:linear-gradient(160deg,#12121f 0%,#1a1a2e 100%);
            border:1px solid #2e2e4a;border-radius:16px;padding:0;
            margin-bottom:16px;overflow:hidden;">

  <!-- Header bar -->
  <div style="background:linear-gradient(90deg,#4f46e5 0%,#7c3aed 100%);
              padding:10px 16px;display:flex;justify-content:space-between;align-items:center;">
    <span style="color:#fff;font-size:13px;font-weight:800;letter-spacing:0.5px;">
      {n}-LEG PARLAY
    </span>
    <span style="color:rgba(255,255,255,0.75);font-size:12px;">
      Win {win_prob:.1%}
    </span>
  </div>

  <!-- Stats row -->
  <div style="display:flex;gap:0;border-bottom:1px solid #2e2e4a;">
    <div style="flex:1;padding:14px 16px;border-right:1px solid #2e2e4a;">
      <div style="color:#888;font-size:10px;text-transform:uppercase;letter-spacing:1px;font-weight:600;margin-bottom:4px;">Combined Odds</div>
      <div style="color:#a78bfa;font-size:26px;font-weight:900;line-height:1;">{amer_fmt}</div>
    </div>
    <div style="flex:1;padding:14px 16px;border-right:1px solid #2e2e4a;">
      <div style="color:#888;font-size:10px;text-transform:uppercase;letter-spacing:1px;font-weight:600;margin-bottom:4px;">Payout on ${pout['stake']:.0f}</div>
      <div style="color:#34d399;font-size:26px;font-weight:900;line-height:1;">${pout['payout']:.2f}</div>
    </div>
    <div style="flex:1;padding:14px 16px;">
      <div style="color:#888;font-size:10px;text-transform:uppercase;letter-spacing:1px;font-weight:600;margin-bottom:4px;">EV</div>
      <div style="color:{ev_col};font-size:26px;font-weight:900;line-height:1;">{ev_sign}{ev_pct:.1f}%</div>
    </div>
  </div>

  <!-- Legs -->
  <div style="padding:4px 16px 8px;">
    {legs_html}
  </div>

</div>""", unsafe_allow_html=True)

            btn_col1, btn_col2 = st.columns([3, 1])
            with btn_col1:
                if st.button(f"Log {n}-Leg Parlay to Tracker",
                             key=f"log_parlay_{sport}_{n}", use_container_width=True):
                    from bet_tracker import add_bet
                    for leg in p["legs"]:
                        prop = market_labels.get(leg.get("market", ""), leg.get("market", ""))
                        mkt  = leg.get("market", "")
                        sk   = (leg["player"].lower(), mkt, float(leg.get("line", 0.5)))
                        sl   = sharp_map.get(sk, {})
                        add_bet(
                            sport=sport,
                            player=leg["player"],
                            prop=f"{prop} O{leg.get('line','')} [{n}-leg parlay]",
                            line=leg.get("line", 0.5),
                            odds=int(leg["over_odds"]),
                            stake=round(stake / n, 2),
                            book="",
                            notes=f"Auto-logged from {n}-leg parlay | {amer_fmt} combined",
                            sharp_odds=sl.get("consensus_odds"),
                            fair_est=leg.get("fair_est"),
                        )
                    st.success(f"{n} legs logged to Tracker!")
            with btn_col2:
                # Build share text for this parlay
                _parlay_lines = "\n".join(
                    f"  {j}. {leg['player']} — "
                    f"{market_labels.get(leg.get('market',''), leg.get('market',''))} "
                    f"O{leg.get('line','')} "
                    f"({('+' if int(leg['over_odds'])>0 else '')}{int(leg['over_odds'])})"
                    for j, leg in enumerate(p["legs"], 1)
                )
                _share_parlay = (
                    f"🎰 {n}-Leg Parlay | {sport}\n"
                    f"{_parlay_lines}\n"
                    f"📈 Combined: {amer_fmt}  |  Win prob: {win_prob:.1%}  |  EV: {ev_sign}{ev_pct:.1f}%\n"
                    f"💰 ${pout['stake']:.0f} → ${pout['payout']:.2f}\n"
                    f"— via Sports Betting Plus"
                )
                _share_btn(_share_parlay, f"parlay_{sport}_{n}", width="100%")

        # ── Log All Parlays + SGPs ──
        _has_parlays = bool(report["parlays"])
        _has_sgps    = bool(report.get("sgps"))
        _diverse     = report.get("diverse_sgps", {})
        _has_diverse = bool(_diverse and any(_diverse.values()))
        if _has_parlays or _has_sgps or _has_diverse:
            _n_parlays = len(report["parlays"])
            _n_sgps    = len(report.get("sgps", []))
            _n_div     = sum(len(v) for v in _diverse.values())
            _label = f"📝 Log Everything to Tracker"
            _parts = []
            if _n_parlays: _parts.append(f"{_n_parlays} parlay{'s' if _n_parlays!=1 else ''}")
            if _n_sgps:    _parts.append(f"{_n_sgps} SGP{'s' if _n_sgps!=1 else ''}")
            if _n_div:     _parts.append(f"{_n_div} best SGP combo{'s' if _n_div!=1 else ''}")
            if _parts:
                _label += f" ({', '.join(_parts)})"
            if st.button(_label, key=f"log_all_parlays_{sport}", use_container_width=True, type="primary"):
                from bet_tracker import add_bet
                total_logged = 0

                # Multi-game parlays
                for pkey, p in report["parlays"].items():
                    n_legs_key = int(pkey.split("_")[0])
                    pout = p["payout"]
                    for leg in p["legs"]:
                        prop = market_labels.get(leg.get("market", ""), leg.get("market", ""))
                        sk = (leg["player"].lower(), leg.get("market",""), float(leg.get("line", 0.5)))
                        sl = sharp_map.get(sk, {})
                        add_bet(
                            sport=sport, player=leg["player"],
                            prop=f"{prop} O{leg.get('line','')} [{n_legs_key}-leg parlay]",
                            line=leg.get("line", 0.5), odds=int(leg["over_odds"]),
                            stake=round(stake / n_legs_key, 2), book="",
                            notes=f"Auto-logged {n_legs_key}-leg parlay | {pout['american_odds']} combined",
                            sharp_odds=sl.get("consensus_odds"), fair_est=leg.get("fair_est"),
                        )
                        total_logged += 1

                # Regular SGPs
                for sgp in report.get("sgps", []):
                    n_legs_key = len(sgp["legs"])
                    pout = sgp["payout"]
                    for leg in sgp["legs"]:
                        prop = market_labels.get(leg.get("market", ""), leg.get("market", ""))
                        sk = (leg["player"].lower(), leg.get("market",""), float(leg.get("line", 0.5)))
                        sl = sharp_map.get(sk, {})
                        add_bet(
                            sport=sport, player=leg["player"],
                            prop=f"{prop} O{leg.get('line','')} [SGP]",
                            line=leg.get("line", 0.5), odds=int(leg["over_odds"]),
                            stake=round(stake / n_legs_key, 2), book="",
                            notes=f"Auto-logged SGP {sgp['game']} | {pout['american_odds']} combined",
                            sharp_odds=sl.get("consensus_odds"), fair_est=leg.get("fair_est"),
                        )
                        total_logged += 1

                # Best diverse SGP combos (all sizes)
                for size_key, combos in _diverse.items():
                    n_legs_key = int(size_key.split("_")[0])
                    for ci, sgp in enumerate(combos, 1):
                        pout = sgp["payout"]
                        for leg in sgp["legs"]:
                            prop = market_labels.get(leg.get("market", ""), leg.get("market", ""))
                            sk = (leg["player"].lower(), leg.get("market",""), float(leg.get("line", 0.5)))
                            sl = sharp_map.get(sk, {})
                            add_bet(
                                sport=sport, player=leg["player"],
                                prop=f"{prop} O{leg.get('line','')} [SGP combo #{ci}]",
                                line=leg.get("line", 0.5), odds=int(leg["over_odds"]),
                                stake=round(stake / n_legs_key, 2), book="",
                                notes=f"Auto-logged best {n_legs_key}-leg SGP combo #{ci} | {sgp['game']} | {pout['american_odds']}",
                                sharp_odds=sl.get("consensus_odds"), fair_est=leg.get("fair_est"),
                            )
                            total_logged += 1

                st.success(f"✅ Logged {total_logged} total legs to Tracker! ({', '.join(_parts)})")

        # ── Diverse SGP combos — always shown ──
        diverse = report.get("diverse_sgps", {})
        if diverse and any(diverse.values()):
            st.divider()
            st.markdown("#### 🎲 Best SGP Combinations")
            st.caption("Top 5 diverse same-game combos per leg count — ranked by combined edge × correlation penalty.")

            size_tabs = st.tabs([f"{n}-Leg SGPs" for n in [3, 4, 5] if f"{n}_leg" in diverse and diverse[f"{n}_leg"]])
            tab_idx = 0
            for n in [3, 4, 5]:
                key = f"{n}_leg"
                if key not in diverse or not diverse[key]:
                    continue
                with size_tabs[tab_idx]:
                    tab_idx += 1
                    combos = diverse[key]
                    for ci, sgp in enumerate(combos):
                        pout = sgp["payout"]
                        pen  = sgp.get("independence_penalty", 1.0)
                        ev   = sgp.get("combined_ev", 0)
                        ev_pct  = ev * 100
                        ev_sign = "+" if ev_pct >= 0 else ""
                        ev_col  = "#34d399" if ev_pct > 0 else "#ff6060"
                        amer    = pout["american_odds"]
                        amer_fmt = f"+{amer}" if isinstance(amer, (int, float)) and amer > 0 else str(amer)
                        win_prob = sgp.get("win_prob") or 0
                        if not win_prob:
                            _wp = 1.0
                            for _l in sgp.get("legs", []):
                                _wp *= min(max(float(_l.get("fair_est") or 0.5), 0.001), 0.999)
                            win_prob = round(_wp, 4)

                        # Build legs HTML
                        legs_html = ""
                        for j, leg in enumerate(sgp["legs"], 1):
                            prop     = market_labels.get(leg.get("market", ""), leg.get("market", ""))
                            edge_val = leg.get("edge", 0)
                            edge_col = "#34d399" if edge_val > 0 else "#ff6060"
                            odds_i   = int(leg["over_odds"])
                            odds_fmt = f"+{odds_i}" if odds_i > 0 else str(odds_i)
                            legs_html += f"""
<div style="display:flex;justify-content:space-between;align-items:flex-start;
            padding:10px 0;border-bottom:1px solid rgba(255,255,255,0.06);">
  <div style="flex:1;min-width:0;">
    <div style="color:#e2e8f0;font-size:14px;font-weight:600;
                white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">
      {j}. {leg['player']}
    </div>
    <div style="color:#94a3b8;font-size:12px;margin-top:2px;">
      {prop} O{leg.get('line','')}
      <span style="color:#a78bfa;font-weight:700;"> {odds_fmt}</span>
      &nbsp;·&nbsp;<span style="color:#64748b;">{leg.get('team','')}</span>
    </div>
  </div>
  <div style="margin-left:12px;flex-shrink:0;">
    <span style="color:{edge_col};font-size:13px;font-weight:700;">{'+' if edge_val>=0 else ''}{edge_val:.1%}</span>
  </div>
</div>"""

                        st.markdown(f"""
<div style="background:linear-gradient(160deg,#12121f 0%,#1a1a2e 100%);
            border:1px solid #2e2e4a;border-radius:16px;padding:0;
            margin-bottom:16px;overflow:hidden;">
  <div style="background:linear-gradient(90deg,#0891b2 0%,#7c3aed 100%);
              padding:10px 16px;display:flex;justify-content:space-between;align-items:center;">
    <span style="color:#fff;font-size:13px;font-weight:800;letter-spacing:0.5px;">
      #{ci+1} · {n}-LEG SGP — {sgp['game']}
    </span>
    <span style="color:rgba(255,255,255,0.75);font-size:12px;">
      Win {win_prob:.1%}
    </span>
  </div>
  <div style="display:flex;gap:0;border-bottom:1px solid #2e2e4a;">
    <div style="flex:1;padding:14px 16px;border-right:1px solid #2e2e4a;">
      <div style="color:#888;font-size:10px;text-transform:uppercase;letter-spacing:1px;font-weight:600;margin-bottom:4px;">Combined Odds</div>
      <div style="color:#a78bfa;font-size:26px;font-weight:900;line-height:1;">{amer_fmt}</div>
    </div>
    <div style="flex:1;padding:14px 16px;border-right:1px solid #2e2e4a;">
      <div style="color:#888;font-size:10px;text-transform:uppercase;letter-spacing:1px;font-weight:600;margin-bottom:4px;">Payout on ${pout['stake']:.0f}</div>
      <div style="color:#34d399;font-size:26px;font-weight:900;line-height:1;">${pout['payout']:.2f}</div>
    </div>
    <div style="flex:1;padding:14px 16px;">
      <div style="color:#888;font-size:10px;text-transform:uppercase;letter-spacing:1px;font-weight:600;margin-bottom:4px;">EV</div>
      <div style="color:{ev_col};font-size:26px;font-weight:900;line-height:1;">{ev_sign}{ev_pct:.1f}%</div>
    </div>
  </div>
  <div style="padding:4px 16px 8px;">{legs_html}</div>
</div>""", unsafe_allow_html=True)

                        # Log + Share buttons
                        d_log_col, d_share_col = st.columns([3, 1])
                        with d_log_col:
                            if st.button(f"Log SGP #{ci+1} to Tracker",
                                         key=f"log_div_{sport}_{n}_{ci}", use_container_width=True):
                                from bet_tracker import add_bet
                                for leg in sgp["legs"]:
                                    prop = market_labels.get(leg.get("market", ""), leg.get("market", ""))
                                    sk = (leg["player"].lower(), leg.get("market",""), float(leg.get("line", 0.5)))
                                    sl = sharp_map.get(sk, {})
                                    add_bet(
                                        sport=sport, player=leg["player"],
                                        prop=f"{prop} O{leg.get('line','')} [Best SGP #{ci+1}]",
                                        line=leg.get("line", 0.5), odds=int(leg["over_odds"]),
                                        stake=round(stake / n, 2), book="",
                                        notes=f"Auto-logged best {n}-leg SGP #{ci+1} | {sgp['game']} | {amer_fmt}",
                                        sharp_odds=sl.get("consensus_odds"), fair_est=leg.get("fair_est"),
                                    )
                                st.success(f"✅ SGP #{ci+1} legs logged!")
                        with d_share_col:
                            _div_lines = "\n".join(
                                f"  {j}. {leg['player']} — "
                                f"{market_labels.get(leg.get('market',''), leg.get('market',''))} "
                                f"O{leg.get('line','')} "
                                f"({('+' if int(leg['over_odds'])>0 else '')}{int(leg['over_odds'])})"
                                for j, leg in enumerate(sgp["legs"], 1)
                            )
                            _share_div = (
                                f"🔗 Best {n}-Leg SGP #{ci+1} — {sgp['game']} | {sport}\n"
                                f"{_div_lines}\n"
                                f"📈 Combined: {amer_fmt}  |  EV: {ev_sign}{ev_pct:.1f}%\n"
                                f"💰 ${pout['stake']:.0f} → ${pout['payout']:.2f}\n"
                                f"— via Sports Betting Plus"
                            )
                            _share_btn(_share_div, f"div_{sport}_{n}_{ci}", width="100%")

        st.divider()
        st.markdown("#### 🔗 Same-Game Parlays (SGPs)")
        st.caption("Different players, same game. One prop per player — diverse markets, correlation-adjusted EV scoring.")
        if report["sgps"]:
            for i, sgp in enumerate(report["sgps"]):
                pout     = sgp["payout"]
                penalty  = sgp.get("independence_penalty", 1.0)
                ev_score = sgp.get("combined_ev", 0)
                ev_pct   = ev_score * 100
                ev_sign  = "+" if ev_pct >= 0 else ""
                ev_col   = "#34d399" if ev_pct > 0 else "#ff6060"
                quality  = "🔥 Strong" if ev_score > 0.04 else ("✅ Good" if ev_score > 0.02 else "🟡 Marginal")
                amer     = pout["american_odds"]
                amer_fmt = f"+{amer}" if isinstance(amer, (int, float)) and amer > 0 else str(amer)
                win_prob = sgp.get("win_prob") or 0
                if not win_prob:
                    _wp = 1.0
                    for _l in sgp.get("legs", []):
                        _wp *= min(max(float(_l.get("fair_est") or 0.5), 0.001), 0.999)
                    win_prob = round(_wp, 4)
                ctax     = sgp.get("correlation_tax", {})
                r_ij     = ctax.get("r_ij", 1.0)
                tax_pct  = ctax.get("correlation_tax_pct", 0.0)
                fair_american = ctax.get("fair_american", "—")
                tax_color = "🔴" if tax_pct >= 40 else ("🟡" if tax_pct >= 20 else "🟢")

                # Build legs HTML
                legs_html = ""
                for j, leg in enumerate(sgp["legs"], 1):
                    prop     = market_labels.get(leg.get("market", ""), leg.get("market", ""))
                    edge_val = leg.get("edge", 0)
                    edge_col = "#34d399" if edge_val > 0 else "#ff6060"
                    odds_i   = int(leg["over_odds"])
                    odds_fmt = f"+{odds_i}" if odds_i > 0 else str(odds_i)
                    nb_delta = leg.get("negbin_delta", 0)
                    nb_str   = f" <span style='color:#64748b;font-size:11px;'>[NB{nb_delta:+.1%}]</span>" if abs(nb_delta) >= 0.005 else ""
                    legs_html += f"""
<div style="display:flex;justify-content:space-between;align-items:flex-start;
            padding:10px 0;border-bottom:1px solid rgba(255,255,255,0.06);">
  <div style="flex:1;min-width:0;">
    <div style="color:#e2e8f0;font-size:14px;font-weight:600;
                white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">
      {j}. {leg['player']}
    </div>
    <div style="color:#94a3b8;font-size:12px;margin-top:2px;">
      {prop} O{leg.get('line','')}
      <span style="color:#a78bfa;font-weight:700;"> {odds_fmt}</span>
      &nbsp;·&nbsp;<span style="color:#64748b;">{leg.get('team','')}</span>{nb_str}
    </div>
  </div>
  <div style="margin-left:12px;flex-shrink:0;">
    <span style="color:{edge_col};font-size:13px;font-weight:700;">{'+' if edge_val>=0 else ''}{edge_val:.1%}</span>
  </div>
</div>"""

                # Correlation tax row (only when present)
                ctax_html = ""
                if ctax:
                    ctax_html = (
                        f"<div style='background:rgba(255,255,255,0.04);border-radius:8px;"
                        f"padding:8px 12px;margin:8px 0 4px;font-size:12px;color:#94a3b8;'>"
                        f"<b style='color:#e2e8f0;'>Correlation Tax:</b> {tax_color} "
                        f"r={r_ij:.2f} &nbsp;|&nbsp; Tax: {tax_pct:+.1f}% &nbsp;|&nbsp; Fair payout: {fair_american}"
                        f"<br><span style='color:#64748b;font-size:11px;'>{ctax.get('verdict','')}</span>"
                        f"</div>"
                    )

                st.markdown(f"""
<div style="background:linear-gradient(160deg,#12121f 0%,#1a1a2e 100%);
            border:1px solid #2e2e4a;border-radius:16px;padding:0;
            margin-bottom:16px;overflow:hidden;">
  <!-- Header -->
  <div style="background:linear-gradient(90deg,#0f766e 0%,#7c3aed 100%);
              padding:10px 16px;display:flex;justify-content:space-between;align-items:center;">
    <span style="color:#fff;font-size:13px;font-weight:800;letter-spacing:0.5px;">
      🔗 SGP — {sgp['game']}
    </span>
    <span style="color:rgba(255,255,255,0.8);font-size:12px;font-weight:600;">
      {quality} &nbsp;·&nbsp; Win {win_prob:.1%}
    </span>
  </div>
  <!-- Stats row -->
  <div style="display:flex;gap:0;border-bottom:1px solid #2e2e4a;">
    <div style="flex:1;padding:14px 16px;border-right:1px solid #2e2e4a;">
      <div style="color:#888;font-size:10px;text-transform:uppercase;letter-spacing:1px;font-weight:600;margin-bottom:4px;">Combined Odds</div>
      <div style="color:#a78bfa;font-size:26px;font-weight:900;line-height:1;">{amer_fmt}</div>
    </div>
    <div style="flex:1;padding:14px 16px;border-right:1px solid #2e2e4a;">
      <div style="color:#888;font-size:10px;text-transform:uppercase;letter-spacing:1px;font-weight:600;margin-bottom:4px;">Payout on ${pout['stake']:.0f}</div>
      <div style="color:#34d399;font-size:26px;font-weight:900;line-height:1;">${pout['payout']:.2f}</div>
    </div>
    <div style="flex:1;padding:14px 16px;">
      <div style="color:#888;font-size:10px;text-transform:uppercase;letter-spacing:1px;font-weight:600;margin-bottom:4px;">EV</div>
      <div style="color:{ev_col};font-size:26px;font-weight:900;line-height:1;">{ev_sign}{ev_pct:.1f}%</div>
    </div>
  </div>
  <!-- Legs + corr tax -->
  <div style="padding:4px 16px 8px;">
    {legs_html}
    {ctax_html}
  </div>
</div>""", unsafe_allow_html=True)

                # Log + Share buttons
                sgp_log_col, sgp_share_col = st.columns([3, 1])
                with sgp_log_col:
                    if st.button("📝 Log SGP to Tracker",
                                 key=f"log_sgp_{sport}_{i}", use_container_width=True):
                        from bet_tracker import add_bet
                        n_legs = len(sgp["legs"])
                        for leg in sgp["legs"]:
                            prop = market_labels.get(leg.get("market", ""), leg.get("market", ""))
                            mkt  = leg.get("market", "")
                            sk   = (leg["player"].lower(), mkt, float(leg.get("line", 0.5)))
                            sl   = sharp_map.get(sk, {})
                            add_bet(
                                sport=sport, player=leg["player"],
                                prop=f"{prop} O{leg.get('line','')} [SGP]",
                                line=leg.get("line", 0.5), odds=int(leg["over_odds"]),
                                stake=round(stake / n_legs, 2), book="",
                                notes=f"Auto-logged from SGP {sgp['game']} | {amer_fmt} combined",
                                sharp_odds=sl.get("consensus_odds"), fair_est=leg.get("fair_est"),
                            )
                        st.success("✅ SGP legs logged to Tracker!")
                with sgp_share_col:
                    _sgp_lines = "\n".join(
                        f"  {j}. {leg['player']} — "
                        f"{market_labels.get(leg.get('market',''), leg.get('market',''))} "
                        f"O{leg.get('line','')} "
                        f"({('+' if int(leg['over_odds'])>0 else '')}{int(leg['over_odds'])})"
                        for j, leg in enumerate(sgp["legs"], 1)
                    )
                    _share_sgp = (
                        f"🔗 SGP — {sgp['game']} | {sport}\n"
                        f"{_sgp_lines}\n"
                        f"📈 Combined: {amer_fmt}  |  EV: {ev_sign}{ev_pct:.1f}%\n"
                        f"💰 ${pout['stake']:.0f} → ${pout['payout']:.2f}\n"
                        f"— via Sports Betting Plus"
                    )
                    _share_btn(_share_sgp, f"sgp_{sport}_{i}", width="100%")
        else:
            st.info("No games with 3+ unique value players found.")

    st.divider()

    # ── Charts ──
    st.markdown("### 📈 Visual Analysis")
    tab1, tab2, tab3, tab4 = st.tabs(["🔍 Fair vs Book", "📊 Top Plays", "📉 Edge Distribution", "🔗 Correlation"])

    with tab1:
        if len(filtered) > 0:
            fig = px.scatter(filtered, x="book_implied", y="fair_est", color="edge",
                             color_continuous_scale="RdYlGn", range_color=[-0.05, 0.12],
                             hover_data={"player": True, "team": True, "market": True, "edge": ":.2%"},
                             title="Fair Probability vs Book Implied",
                             labels={"book_implied": "Book Implied %", "fair_est": "Fair Est. %"},
                             height=480)
            fig.add_trace(go.Scatter(x=[0.45, 0.90], y=[0.45, 0.90], mode="lines",
                                     name="No Edge", line=dict(color="rgba(255,255,255,0.2)", dash="dash")))
            fig.update_layout(**PLOT_LAYOUT)
            st.plotly_chart(fig, use_container_width=True, config={"responsive": True})

    with tab2:
        if len(filtered) > 0:
            top_df2 = filtered.head(15).sort_values("edge", ascending=True).copy()
            top_df2["label"] = top_df2["player"] + " (" + top_df2["market"].map(
                lambda k: market_labels.get(k, k)) + ")"
            fig2 = px.bar(top_df2, x="edge", y="label", color="edge",
                          color_continuous_scale="RdYlGn", orientation="h",
                          hover_data=["team", "fair_est", "book_implied"],
                          title="Top 15 Value Plays by Edge",
                          labels={"edge": "Edge", "label": "Player (Prop)"}, height=500)
            fig2.update_layout(showlegend=False, **PLOT_LAYOUT)
            st.plotly_chart(fig2, use_container_width=True, config={"responsive": True})

    with tab3:
        if len(filtered) > 1:
            fig3 = px.histogram(filtered, x="edge", nbins=25, color="market",
                                title="Edge Distribution by Market",
                                labels={"edge": "Edge"}, height=400)
            fig3.add_vline(x=edge_threshold, line_dash="dash",
                           line_color="rgba(255,100,100,0.7)",
                           annotation_text="Threshold",
                           annotation_font_color="#ff6060")
            fig3.update_layout(**PLOT_LAYOUT)
            st.plotly_chart(fig3, use_container_width=True, config={"responsive": True})

    with tab4:
        # ── Prop Correlation Heatmap ──
        if len(filtered) >= 2:
            try:
                import numpy as _np
                # Build matrix for top-N plays by confidence
                heat_df = filtered.head(20).copy()
                labels = (heat_df["player"].str.split().str[-1].fillna("?") +
                          "\n" + heat_df["market"].str.replace("_", " ", regex=False).fillna("?"))
                n = len(heat_df)
                mat = _np.zeros((n, n))
                for ii in range(n):
                    for jj in range(n):
                        if ii == jj:
                            mat[ii, jj] = 1.0
                        else:
                            same_p = (heat_df.iloc[ii]["player"] == heat_df.iloc[jj]["player"])
                            mat[ii, jj] = get_market_pair_rho(
                                heat_df.iloc[ii]["market"],
                                heat_df.iloc[jj]["market"],
                                same_p,
                            )

                fig_heat = go.Figure(data=go.Heatmap(
                    z=mat,
                    x=labels.tolist(),
                    y=labels.tolist(),
                    colorscale=[
                        [0.0, "#1a2a5a"],
                        [0.5, "#1a1a24"],
                        [1.0, "#7c3aed"],
                    ],
                    zmin=-1, zmax=1,
                    colorbar=dict(title="ρ", tickfont=dict(color="#888")),
                    hovertemplate="%{y} × %{x}<br>ρ = %{z:.2f}<extra></extra>",
                ))
                fig_heat.update_layout(
                    title="Prop Correlation Matrix (Top 20 plays)",
                    height=500,
                    xaxis=dict(tickfont=dict(size=9, color="#888")),
                    yaxis=dict(tickfont=dict(size=9, color="#888")),
                    **PLOT_LAYOUT,
                )
                st.plotly_chart(fig_heat, use_container_width=True, config={"responsive": True})
                st.caption(
                    "Purple = highly correlated (same player, overlapping markets). "
                    "Dark = uncorrelated. Avoid stacking high-ρ legs in parlays — "
                    "the book's SGP price already penalises you for the correlation."
                )
            except Exception as _e:
                st.info(f"Heatmap unavailable: {_e}")
        else:
            st.info("Need at least 2 props to draw correlation heatmap.")

    # ── Player News / Injury Feed ──
    st.divider()
    with st.expander("📰 Player News & Injury Feed", expanded=False):
        try:
            from news_feed import render_news_sidebar as _render_news
            _players = filtered["player"].dropna().unique().tolist()[:40]
            _render_news(_players, sport)
        except Exception as _ne:
            st.caption(f"News unavailable: {_ne}")

    # ── AI Chat ──
    if GROQ_API_KEY:
        st.divider()
        st.markdown("### 🤖 AI Analyst")
        chat_key = f"chat_{sport}"
        if chat_key not in st.session_state:
            st.session_state[chat_key] = []
        for msg in st.session_state[chat_key]:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
        if prompt := st.chat_input(f"Ask about today's {sport} picks...", key=f"chat_input_{sport}"):
            st.session_state[chat_key].append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)
            top_picks = filtered.head(10)[["player", "team", "market", "line",
                                            "over_odds", "book_implied", "fair_est", "edge"]].to_dict("records")
            with st.chat_message("assistant"):
                with st.spinner("Thinking..."):
                    try:
                        response = run_ai_analysis(top_picks, question=prompt)
                        st.markdown(response)
                        st.session_state[chat_key].append({"role": "assistant", "content": response})
                    except Exception as e:
                        st.error(f"AI error: {e}")


# ── ML Models Tab ─────────────────────────────────────────────────────────────
def _render_ml_tab():
    import sys as _sys
    _sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))

    st.markdown("## 🤖 ML Predictive Models")
    st.markdown(
        "LightGBM prop prediction, Platt-scaling calibration, and steam/RLM detection — "
        "all trained on your own bet history and odds snapshots."
    )

    # ── Tabs within ML tab ──
    cal_tab, lgbm_tab, steam_tab = st.tabs(
        ["🎯 Calibration Engine", "📊 LightGBM Models", "⚡ Steam & RLM Detector"]
    )

    # ── Calibration ──────────────────────────────────────────────────────────
    with cal_tab:
        st.markdown("### 🎯 Edge Score Calibration")
        st.markdown(
            "Platt scaling maps raw model signals → calibrated win probabilities "
            "so Kelly sizing is mathematically correct. "
            "**Brier score ≤ 0.22 = good. Coin-flip baseline = 0.25.**"
        )
        try:
            from calibration import calibration_status, train_calibrator, brier_interpretation

            status = calibration_status()
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Graded Bets", status["n_graded"])
            c2.metric("Win Rate", f"{status['win_rate']}%" if status["win_rate"] else "—")
            c3.metric("Brier Score", status["brier_score"] if status["brier_score"] else "—",
                      help="Lower = better calibrated. Coin-flip = 0.25")
            c4.metric("Method", status["method"].title() if status["method"] else "—")

            if status["brier_score"]:
                st.info(brier_interpretation(status["brier_score"]))

            if status["status"] == "untrained":
                st.warning(f"⚠️ Calibrator not trained yet. Need {status['min_platt']} graded bets (have {status['n_graded']}).")

            if status["trained_at"]:
                st.caption(f"Last trained: {status['trained_at'][:19]}")

            # Reliability diagram
            rel = status.get("reliability", {})
            if rel.get("mean_pred") and rel.get("frac_pos"):
                import plotly.graph_objects as _go
                fig = _go.Figure()
                fig.add_trace(_go.Scatter(
                    x=rel["mean_pred"], y=rel["frac_pos"],
                    mode="lines+markers", name="Calibration curve",
                    line=dict(color="#00d4ff", width=2),
                    marker=dict(size=8),
                ))
                fig.add_trace(_go.Scatter(
                    x=[0, 1], y=[0, 1],
                    mode="lines", name="Perfect calibration",
                    line=dict(color="#555", dash="dash"),
                ))
                fig.update_layout(
                    title="Reliability Diagram (closer to diagonal = better)",
                    xaxis_title="Mean Predicted Probability",
                    yaxis_title="Fraction of Positives (actual win rate)",
                    height=270,
                    paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
                    font=dict(color="#eee"),
                )
                st.plotly_chart(fig, use_container_width=True, config={"responsive": True})

            if st.button("🔄 Retrain Calibrator", key="retrain_cal"):
                with st.spinner("Training calibrator on historical bets…"):
                    result = train_calibrator(force=True)
                if result["status"] == "ok":
                    st.success(f"✅ {result['msg']}")
                    st.rerun()
                else:
                    st.warning(result.get("msg", "Training failed"))

        except Exception as _e:
            st.error(f"Calibration module error: {_e}")

    # ── LightGBM ─────────────────────────────────────────────────────────────
    with lgbm_tab:
        st.markdown("### 📊 LightGBM Per-Sport Models")
        st.markdown(
            "Gradient boosting models trained on your graded bet history. "
            "Once trained, these replace manual edge scores with data-driven predictions. "
            "**AUC > 0.55 = beating random. AUC > 0.65 = strong.**"
        )
        try:
            from ml_model import model_status, train_models

            statuses = model_status()
            cols = st.columns(len(statuses))
            for col, (sport, info) in zip(cols, statuses.items()):
                with col:
                    icon = {"MLB": "⚾", "NBA": "🏀", "WNBA": "🏀", "NHL": "🏒"}.get(sport, "🎯")
                    st.markdown(f"**{icon} {sport}**")
                    if info["status"] == "trained":
                        auc_val = info.get("cv_auc")
                        auc_str = f"{auc_val:.4f}" if auc_val else "N/A"
                        color   = "#00ff88" if auc_val and auc_val >= 0.65 else (
                                  "#f9c74f" if auc_val and auc_val >= 0.55 else "#ff6060")
                        st.markdown(
                            f"<span style='color:{color};font-weight:bold'>✅ Trained</span>",
                            unsafe_allow_html=True,
                        )
                        st.metric("CV AUC", auc_str)
                        st.metric("Brier", f"{info.get('brier_score', '—')}")
                        st.metric("Samples", info["n_trained"])
                        st.caption(f"Win rate: {info['win_rate']}%")
                    else:
                        st.markdown("⏳ **Not trained**")
                        st.caption(info.get("msg", ""))
                        st.metric("Graded bets", info["n_graded"])

            st.markdown("---")
            feat_col, train_col = st.columns([2, 1])
            with feat_col:
                st.markdown("**Features used:**")
                st.markdown(
                    "- Implied probability (de-vigged)\n"
                    "- Opening → current odds delta (line movement)\n"
                    "- Market group, line value, odds bucket\n"
                    "- CLV at placement (if logged)\n"
                    "- Underdog flag"
                )
            with train_col:
                if st.button("🚀 Train All Models", key="train_lgbm"):
                    with st.spinner("Training LightGBM models…"):
                        results = train_models(force=True)
                    ok = [s for s, r in results.items() if r.get("status") == "ok"]
                    skip = [s for s, r in results.items() if r.get("status") != "ok"]
                    if ok:
                        st.success(f"✅ Trained: {', '.join(ok)}")
                    if skip:
                        st.info(f"⏭ Skipped (need more data): {', '.join(skip)}")
                    if ok:
                        st.rerun()

        except Exception as _e:
            st.error(f"ML model module error: {_e}")

    # ── Steam / RLM ──────────────────────────────────────────────────────────
    with steam_tab:
        st.markdown("### ⚡ Steam Moves & Reverse Line Movement")
        st.markdown(
            "Detected from your odds snapshots. **Steam** = rapid line movement (sharp/syndicate money). "
            "**RLM** = line drifts toward underdog side (sharp fade of public action)."
        )
        try:
            from steam_detector import detect_steam_moves, detect_rlm, load_snapshots, steam_summary

            _snaps = load_snapshots()

            # Controls
            sc1, sc2, sc3 = st.columns(3)
            _sport_filter  = sc1.selectbox("Sport filter", ["All", "MLB", "NBA", "WNBA", "NHL"], key="steam_sport")
            _min_move      = sc2.slider("Min move (cents)", 1, 20, 5, key="steam_min") / 100
            _signal_filter = sc3.selectbox("Signal type", ["All", "Steam only", "RLM only", "Steam+RLM"], key="steam_sig")

            with st.spinner("Scanning snapshots…"):
                all_flags = detect_steam_moves(_snaps, min_move=_min_move)

            # Sport filter
            SPORT_MARKETS = {
                "MLB":  {"pitcher_strikeouts","pitcher_outs_recorded","pitcher_hits_allowed",
                         "pitcher_walks","pitcher_earned_runs","batter_hits","batter_total_bases",
                         "batter_home_runs","batter_rbis","batter_runs_scored","batter_stolen_bases",
                         "batter_hits_runs_rbis"},
                "NBA":  {"player_points","player_rebounds","player_assists","player_threes",
                         "player_steals","player_blocks","player_points_rebounds_assists",
                         "player_points_rebounds","player_points_assists","player_double_double"},
                "WNBA": {"player_points","player_rebounds","player_assists","player_threes",
                         "player_steals","player_blocks","player_points_rebounds_assists"},
                "NHL":  {"player_goals","player_assists","player_points",
                         "player_shots_on_goal","player_saves","player_power_play_points"},
            }
            if _sport_filter != "All":
                _markets = SPORT_MARKETS.get(_sport_filter, set())
                all_flags = [f for f in all_flags if f["market"] in _markets]

            # Signal filter
            if _signal_filter == "Steam only":
                all_flags = [f for f in all_flags if f["signal"] == "steam"]
            elif _signal_filter == "RLM only":
                all_flags = [f for f in all_flags if "rlm" in f["signal"]]
            elif _signal_filter == "Steam+RLM":
                all_flags = [f for f in all_flags if f["signal"] == "steam+rlm"]

            # Summary metrics
            summ = steam_summary(all_flags)
            m1, m2, m3, m4, m5 = st.columns(5)
            m1.metric("Total Flags", summ.get("total", 0))
            m2.metric("🔴 Strong",   summ.get("strong", 0))
            m3.metric("🟡 Moderate", summ.get("moderate", 0))
            m4.metric("🔄 RLM",      summ.get("rlm_count", 0))
            m5.metric("Avg Move",    f"{summ.get('avg_move_c', 0)}¢")

            # Table
            if all_flags:
                import pandas as _pd
                _df_steam = _pd.DataFrame([{
                    "Player":     f["player"],
                    "Market":     f["market"],
                    "Line":       f["line"],
                    "Open Odds":  f"{f['open_odds']:+d}",
                    "Curr Odds":  f"{f['curr_odds']:+d}",
                    "Move (¢)":   f["move_cents"],
                    "Direction":  "⬆️ Over" if f["move_direction"] == "toward_over" else "⬇️ Under",
                    "Signal":     "⚡+🔄" if f["signal"] == "steam+rlm" else "⚡",
                    "Strength":   f["strength"].title(),
                    "Edge Open":  f"{f['edge_open']}%",
                    "Edge Now":   f"{f['edge_current']}%",
                } for f in all_flags[:200]])

                def _color_strength(val):
                    if val == "Strong":   return "color: #00ff88; font-weight: bold"
                    if val == "Moderate": return "color: #f9c74f"
                    return "color: #aaa"

                st.dataframe(
                    _df_steam.style.map(_color_strength, subset=["Strength"]),
                    use_container_width=True, height=420,
                )
                st.caption(f"Showing {min(200, len(all_flags))} of {len(all_flags)} flags. "
                           "Data from odds_snapshots.json — updates when scraper runs.")
            else:
                st.info("No steam/RLM flags found with current filters.")

            # Move distribution chart
            if len(all_flags) >= 5:
                import plotly.graph_objects as _go2
                _moves = [f["move_cents"] for f in all_flags]
                _fig2 = _go2.Figure(_go2.Histogram(
                    x=_moves, nbinsx=30,
                    marker_color="#7c3aed", opacity=0.8,
                ))
                _fig2.update_layout(
                    title="Line Move Distribution (cents of implied probability)",
                    xaxis_title="Move Size (cents)",
                    yaxis_title="Count",
                    height=260,
                    paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
                    font=dict(color="#eee"),
                )
                st.plotly_chart(_fig2, use_container_width=True, config={"responsive": True})

        except Exception as _e:
            st.error(f"Steam detector error: {_e}")
            import traceback as _tb
            st.code(_tb.format_exc())


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    import os as _os
    _banner = _os.path.join(_os.path.dirname(__file__), "..", "static", "banner.png")
    if _os.path.exists(_banner):
        st.image(_banner, use_container_width=True)
    else:
        st.markdown("""
<div style="text-align:center;padding:36px 0 28px;">
  <div style="display:inline-block;background:linear-gradient(135deg,#7c3aed,#4f46e5);
              border-radius:14px;padding:12px 22px;margin-bottom:16px;">
    <span style="color:#fff;font-size:22px;font-weight:900;letter-spacing:-0.5px;">
      Sports Betting+
    </span>
  </div>
  <h1 style="margin:0;font-family:'Space Grotesk',sans-serif;font-size:2rem;font-weight:800;
             background:linear-gradient(90deg,#a78bfa,#7c3aed,#4f46e5);
             -webkit-background-clip:text;-webkit-text-fill-color:transparent;
             background-clip:text;letter-spacing:-0.5px;">
    Daily Props Dashboard
  </h1>
  <p style="color:#666;font-size:0.9rem;margin:6px 0 0;">
    Multi-Sport Player Props &nbsp;·&nbsp; Live Value Detection &nbsp;·&nbsp; Sharp Bettor Tools
  </p>
</div>
""", unsafe_allow_html=True)

    with st.sidebar:
        import os as _os
        _logo = _os.path.join(_os.path.dirname(__file__), "..", "static", "logo.png")
        _banner_sb = _os.path.join(_os.path.dirname(__file__), "..", "static", "banner.png")
        if _os.path.exists(_logo):
            st.image(_logo, use_container_width=True)
        elif _os.path.exists(_banner_sb):
            st.image(_banner_sb, use_container_width=True)
        else:
            st.markdown("""
<div style="background:linear-gradient(135deg,#7c3aed,#4f46e5);border-radius:12px;
            padding:10px 14px;margin-bottom:4px;text-align:center;">
  <span style="color:#fff;font-size:16px;font-weight:900;letter-spacing:-0.3px;">Sports Betting+</span>
</div>
""", unsafe_allow_html=True)
        st.divider()
        st.markdown("## ⚙️ Settings")
        use_live = st.toggle("Live Odds (The Odds API)", value=bool(ODDS_API_KEY),
                             disabled=not bool(ODDS_API_KEY))
        st.divider()
        st.markdown("## 💰 Kelly Bankroll")
        bankroll = st.number_input("My Bankroll ($)", min_value=10.0, max_value=1000000.0,
                                   value=1000.0, step=50.0, key="bankroll_input")
        kelly_mult = st.select_slider("Kelly Fraction",
                                      options=[0.1, 0.25, 0.5, 1.0],
                                      value=0.25,
                                      format_func=lambda x: {0.1: "1/10 (Very Safe)", 0.25: "1/4 (Recommended)", 0.5: "1/2 (Aggressive)", 1.0: "Full (Risky)"}[x],
                                      key="kelly_mult")
        st.caption("¼ Kelly is the professional standard. Full Kelly risks ruin.")

        # ── Bankroll Settings (unit size / kelly multiplier persisted to disk) ──
        st.markdown("---")
        st.subheader("Bankroll Settings")
        st.session_state.setdefault("settings", load_settings())
        _s = st.session_state["settings"]

        # ── Restore saved filters on first load of session ──────────────────
        if not st.session_state.get("_filters_restored") and _s.get("filters"):
            for _fsport, _fdata in _s["filters"].items():
                # Restore market checkboxes
                for _mkt, _checked in _fdata.get("markets", {}).items():
                    _chk_key = f"mkt_chk_{_fsport}_{_mkt}"
                    if _chk_key not in st.session_state:
                        st.session_state[_chk_key] = _checked
                # Restore edge slider
                _ekey = f"edge_slider_{_fsport}"
                if _ekey not in st.session_state and _fdata.get("edge") is not None:
                    st.session_state[_ekey] = float(_fdata["edge"])
                # Restore teams multiselect — only restore teams that exist TODAY
                # (stale matchups from a previous day would filter out all rows)
                _tkey = f"teams_{_fsport}"
                if _tkey not in st.session_state and _fdata.get("teams"):
                    try:
                        from scraper import scrape_props as _sp
                        _live_df = _sp(_fsport)
                        _live_teams = set(_live_df["team"].dropna().unique()) if not _live_df.empty else set()
                        _valid_saved = [t for t in _fdata["teams"] if t in _live_teams]
                        # Only restore if at least one saved team still exists today
                        if _valid_saved:
                            st.session_state[_tkey] = _valid_saved
                        # else leave unset so widget defaults to all_teams
                    except Exception:
                        pass  # leave unset, widget will default to all teams
                # Restore search
                _skey = f"search_{_fsport}"
                if _skey not in st.session_state and _fdata.get("search"):
                    st.session_state[_skey] = _fdata["search"]
                # Restore toggles
                for _tog in ("confirmed", "shop_alerts", "hot_streaks"):
                    _togkey = f"{_tog}_{_fsport}"
                    if _togkey not in st.session_state:
                        st.session_state[_togkey] = bool(_fdata.get(_tog, False))
            st.session_state["_filters_restored"] = True
        _starting_bankroll = st.number_input(
            "Starting Bankroll ($)",
            min_value=10.0,
            max_value=10_000_000.0,
            value=float(_s.get("starting_bankroll", 1000.0)),
            step=50.0,
            key="settings_starting_bankroll",
        )
        _unit_size = st.number_input(
            "Unit Size ($)",
            min_value=0.50,
            max_value=100_000.0,
            value=float(_s.get("unit_size", 10.0)),
            step=1.0,
            key="settings_unit_size",
        )
        _kelly_multiplier = st.number_input(
            "Kelly Multiplier",
            min_value=0.01,
            max_value=1.0,
            value=float(_s.get("kelly_multiplier", 0.25)),
            step=0.01,
            key="settings_kelly_multiplier",
        )
        if st.button("💾 Save Settings", key="save_settings_btn"):
            # Collect filter state for every live sport
            _filter_snapshot = {}
            for _fsport in [s for s, c in SPORTS_CONFIG.items() if c.get("status") == "live"]:
                _fmkts = {
                    mkt: bool(st.session_state.get(f"mkt_chk_{_fsport}_{mkt}", False))
                    for mkt in SPORTS_CONFIG[_fsport]["market_labels"]
                }
                _filter_snapshot[_fsport] = {
                    "markets":      _fmkts,
                    "edge":         st.session_state.get(f"edge_slider_{_fsport}", 0.0),
                    "teams":        st.session_state.get(f"teams_{_fsport}", []),
                    "search":       st.session_state.get(f"search_{_fsport}", ""),
                    "confirmed":    st.session_state.get(f"confirmed_{_fsport}", False),
                    "shop_alerts":  st.session_state.get(f"shop_alerts_{_fsport}", False),
                    "hot_streaks":  st.session_state.get(f"hot_streaks_{_fsport}", False),
                }
            _new_settings = {
                "starting_bankroll": _starting_bankroll,
                "unit_size":         _unit_size,
                "kelly_multiplier":  _kelly_multiplier,
                "filters":           _filter_snapshot,
            }
            save_settings(_new_settings)
            st.session_state["settings"] = _new_settings
            st.success("✅ Settings & filters saved!")

        # ── Kelly Portfolio Optimizer (sidebar) ──
        st.divider()
        with st.expander("📐 Kelly Portfolio Optimizer", expanded=False):
            st.caption("Allocate bankroll optimally across multiple correlated bets.")
            _kp_sport = st.selectbox("Sport", [s for s in SPORTS_CONFIG if SPORTS_CONFIG[s]["status"] == "live"],
                                     key="kp_sport")
            _kp_min_edge = st.slider("Min Edge %", 1, 15, 3, key="kp_min_edge") / 100
            _kp_max_total = st.slider("Max Total Exposure %", 5, 50, 20, key="kp_max_total") / 100
            if st.button("🔢 Optimize", key="kp_btn", use_container_width=True):
                with st.spinner("Optimizing…"):
                    try:
                        _kp_df, _ = load_data(_kp_sport, use_live)
                        _uid = st.session_state.get("user_id")
                        _kp_clv = get_clv_avg(n_recent=30, user_id=_uid)
                        if _kp_df is not None and not _kp_df.empty:
                            _kp_plays = [
                                r.to_dict()
                                for _, r in _kp_df.iterrows()
                                if float(r.get("edge", 0)) >= _kp_min_edge
                            ]
                            if _kp_plays:
                                _kp_result = kelly_portfolio(
                                    _kp_plays, bankroll,
                                    max_total_pct=_kp_max_total,
                                    clv_avg=_kp_clv,
                                )
                                for _kpr in _kp_result[:8]:
                                    st.markdown(
                                        f"**{_kpr['player']}** {_kpr['market'].replace('_',' ')}  \n"
                                        f"Portfolio: {_kpr['portfolio_pct']:.2f}% · "
                                        f"**${_kpr['stake']:.2f}** · EV ${_kpr['ev_on_stake']:+.2f}"
                                    )
                            else:
                                st.info("No plays meet the minimum edge threshold.")
                    except Exception as _kpe:
                        st.error(f"Optimizer error: {_kpe}")

        st.divider()
        st.markdown("## 🔍 Filters")

    # ── Parallel preload: warm all sport caches in background threads ──
    # This is the key performance upgrade — all sports load simultaneously so
    # tab switches are instant instead of each one waiting ~4s sequentially.
    preload_all_sports_parallel(use_live)

    # ── 🎯 Best 3 Bets Today ─────────────────────────────────────────────────
    _b3_col, _ = st.columns([1, 3])
    with _b3_col:
        if st.button("🎯 Best 3 Bets Today", use_container_width=True, type="primary",
                     help="Cross-sport: find the top 3 highest-confidence props right now and log them to tracker"):
            with st.spinner("Scanning all sports for today's best plays…"):
                from bet_tracker import add_bet
                _uid = st.session_state.get("user_id")
                _clv_avg_b3 = get_clv_avg(n_recent=30, user_id=_uid)
                _all_candidates = []
                for _sport in [s for s, c in SPORTS_CONFIG.items() if c.get("status") == "live"]:
                    try:
                        _df, _ = load_data(_sport, use_live)
                        if _df is None or _df.empty:
                            continue
                        for _, _row in _df.iterrows():
                            _score = edge_confidence_score(
                                float(_row.get("edge", 0)),
                                float(_row.get("fair_est", 0.5)),
                                bool(_row.get("edge_confirmed", False)),
                                int(_row.get("n_books", 1)),
                                float(_row.get("over_odds", -110)),
                                _clv_avg_b3,
                            )
                            _all_candidates.append({
                                "sport":    _sport,
                                "player":   _row.get("player", ""),
                                "team":     _row.get("team", ""),
                                "market":   _row.get("market", ""),
                                "line":     _row.get("line", ""),
                                "over_odds": _row.get("over_odds", -110),
                                "fair_est": _row.get("fair_est", 0.5),
                                "edge":     _row.get("edge", 0),
                                "confidence": _score,
                            })
                    except Exception:
                        pass

                _all_candidates.sort(key=lambda x: x["confidence"], reverse=True)
                _top3 = _all_candidates[:3]

                if not _top3:
                    st.warning("No plays found across live sports right now.")
                else:
                    _bankroll_b3 = st.session_state.get("bankroll_input", 1000.0)
                    _kmult_b3   = st.session_state.get("kelly_mult", 0.25)
                    _logged = []
                    for _p in _top3:
                        _lbl, _col = confidence_label(_p["confidence"])
                        try:
                            _rec_b3 = recommended_stake(_p["fair_est"], float(_p["over_odds"]),
                                            _bankroll_b3, _kmult_b3, _clv_avg_b3)
                            _stake_b3 = _rec_b3["stake"]
                        except Exception:
                            _stake_b3 = round(_bankroll_b3 * 0.02, 2)
                        add_bet(
                            _p["sport"], _p["player"],
                            f"{_p['market']} O{_p['line']}",
                            float(_p["line"]) if _p["line"] else 0.5,
                            int(float(_p["over_odds"])),
                            _stake_b3, "Best3Auto",
                            f"Auto-logged by Best 3 Bets · Confidence {_p['confidence']}/100",
                            fair_est=_p["fair_est"],
                        )
                        _logged.append(
                            f"**{_p['player']}** ({_p['sport']}) · {_p['market'].replace('_',' ')} "
                            f"O{_p['line']} @ {_p['over_odds']:+g} · {_lbl} {_p['confidence']}/100"
                        )

                    st.success(f"✅ Logged {len(_logged)} best bet(s) to Tracker:")
                    for _line in _logged:
                        st.markdown(f"- {_line}")

    # Build tab labels
    sport_tab_labels = [f"{SPORTS_CONFIG[s]['icon']} {s}" for s in SPORTS_CONFIG]
    all_tab_labels = sport_tab_labels + ["🤖 ML Models", "📈 CLV & ROI", "📊 Tracker", "🏆 Leaderboard"]
    all_tabs = st.tabs(all_tab_labels)

    sports_list = list(SPORTS_CONFIG.keys())
    _allowed = _tiers.allowed_sports(_current_tier) if _tiers else sports_list

    for i, (tab, sport) in enumerate(zip(all_tabs[:-len(["🤖 ML Models", "📈 CLV & ROI", "📊 Tracker", "🏆 Leaderboard"])], sports_list)):
        with tab:
            cfg = SPORTS_CONFIG[sport]
            status = cfg.get("status", "live")

            # Tier gate — non-free sports locked for free users
            if sport not in _allowed:
                st.markdown(f"## {cfg['icon']} {sport}")
                st.markdown("""
                <div style='background:rgba(0,212,255,0.08);border:1px solid #00d4ff;
                            border-radius:12px;padding:1.5rem;text-align:center;margin:1rem 0'>
                    <h3>🔒 Standard Feature</h3>
                    <p style='color:#aaa'>Upgrade to <strong>Standard</strong> ($9/mo)
                    to unlock all 6 sports.</p>
                </div>
                """, unsafe_allow_html=True)
                if _SUPABASE_CONFIGURED:
                    import auth_ui
                    auth_ui.show_upgrade_modal("standard", key=f"sports_{i}")
                continue

            if status == "coming_soon":
                st.markdown(f"## {cfg['icon']} {sport} — Coming Soon")
                st.info(f"📅 {cfg['coming_soon_msg']}")
                st.markdown("**Markets ready when the season starts:**")
                for label in cfg["market_labels"].values():
                    st.markdown(f"- {label}")
                st.caption("This tab auto-populates with live props once games are posted.")

            elif status == "needs_api":
                st.markdown(f"## {cfg['icon']} {sport}")
                st.warning(f"🔌 {cfg['coming_soon_msg']}")
                st.markdown("""
### How to enable Horse Racing:

**Option 1 — The Racing API** (~$30/mo) · [theracingapi.com](https://www.theracingapi.com)

Add to `.env`:
```
RACING_API_KEY=your_key_here
```

**Option 2 — RapidAPI Horse Racing** (free tier) · [rapidapi.com](https://rapidapi.com)
```
RAPIDAPI_KEY=your_key_here
```
**Data you'll get:** Race cards, morning line vs live odds, overlay value plays, exotic parlay builder.
                """)

            else:
                render_sport_tab(sport, use_live)

    # ML Models tab (fourth from last)
    with all_tabs[-4]:
        _render_ml_tab()

    # CLV & ROI tab (third from last)
    with all_tabs[-3]:
        render_clv_tab()

    # Tracker tab (second to last)
    with all_tabs[-2]:
        if _tiers and not _tiers.can(_current_tier, "tracker"):
            st.markdown("""
            <div style='background:rgba(0,212,255,0.08);border:1px solid #00d4ff;
                        border-radius:12px;padding:1.5rem;text-align:center;margin:1rem 0'>
                <h3>🔒 Premium Feature</h3>
                <p style='color:#aaa'>The Bet Tracker is available on <strong>Premium</strong> ($29/mo).</p>
            </div>
            """, unsafe_allow_html=True)
            if _SUPABASE_CONFIGURED:
                import auth_ui
                auth_ui.show_upgrade_modal("premium", key="tracker")
        else:
            render_bet_tracker()

    # Leaderboard tab (last)
    with all_tabs[-1]:
        render_leaderboard()

    st.divider()
    st.markdown("""
<div style="text-align:center;padding:28px 0 8px;border-top:1px solid #2a2a3a;margin-top:24px;">
  <div style="display:inline-block;background:linear-gradient(135deg,#7c3aed,#4f46e5);
              border-radius:10px;padding:8px 16px;margin-bottom:12px;">
    <span style="color:#fff;font-size:14px;font-weight:800;letter-spacing:-0.3px;">Sports Betting+</span>
  </div>
  <p style="color:#333;font-size:11px;margin:4px 0 2px;">
    Live odds via The Odds API &nbsp;·&nbsp; AI analysis by Groq &nbsp;·&nbsp; Stats via ESPN public API
  </p>
  <p style="color:#262630;font-size:11px;margin:0;">
    Always bet responsibly. Past performance does not guarantee future results.
  </p>
</div>
""", unsafe_allow_html=True)


# ── CLV Leaderboard ───────────────────────────────────────────────────────────
def render_leaderboard():
    """
    Public anonymous CLV leaderboard — shows top bettors by avg CLV.
    Requires users to opt in and choose a display handle.
    Data is fetched via the Supabase service role (read-only aggregate query).
    """
    st.markdown("## 🏆 CLV Leaderboard")
    st.caption(
        "Anonymous leaderboard ranked by Closing Line Value — the gold-standard measure of long-term edge. "
        "Opt in below to appear. Your real name is never shown."
    )

    # ── Opt-in toggle (for authenticated users) ──────────────────────────────
    if _SUPABASE_CONFIGURED:
        uid = st.session_state.get("user_id")
        if uid:
            import auth as _auth_mod
            profile = st.session_state.get("profile") or {}
            current_opt_in = bool(profile.get("leaderboard_opt_in", False))
            current_handle = profile.get("leaderboard_handle") or ""

            with st.expander("⚙️ My Leaderboard Settings", expanded=False):
                opt_in = st.toggle("Appear on leaderboard", value=current_opt_in,
                                   help="Your handle and CLV stats are shown anonymously. No personal info is revealed.")
                handle = st.text_input(
                    "Display handle",
                    value=current_handle,
                    max_chars=24,
                    placeholder="e.g. SharpBettor99",
                    help="Shown publicly. No real name, email, or betting history details are exposed.",
                )
                if st.button("💾 Save", key="lb_save"):
                    if opt_in and not handle.strip():
                        st.error("Enter a display handle to appear on the leaderboard.")
                    else:
                        try:
                            from supabase import create_client as _sc
                            _sb = _sc(
                                os.environ.get("SUPABASE_URL", ""),
                                os.environ.get("SUPABASE_ANON_KEY", ""),
                            )
                            access = st.session_state.get("access_token")
                            if access:
                                _sb.auth.set_session(access, st.session_state.get("refresh_token", ""))
                            _sb.table("profiles").update({
                                "leaderboard_opt_in": opt_in,
                                "leaderboard_handle": handle.strip() if opt_in else None,
                            }).eq("id", uid).execute()
                            # Refresh cached profile
                            if "profile" in st.session_state:
                                st.session_state["profile"]["leaderboard_opt_in"] = opt_in
                                st.session_state["profile"]["leaderboard_handle"] = handle.strip()
                            st.success("✅ Saved!" if opt_in else "✅ Removed from leaderboard.")
                            st.rerun()
                        except Exception as _e:
                            st.error(f"Save failed: {_e}")

    st.divider()

    # ── Fetch leaderboard data ─────────────────────────────────────────────────
    rows: list[dict] = []
    try:
        if _SUPABASE_CONFIGURED:
            from supabase import create_client as _sc2
            _sb2 = _sc2(os.environ.get("SUPABASE_URL",""), os.environ.get("SUPABASE_ANON_KEY",""))
            resp = _sb2.table("clv_leaderboard").select("*").execute()
            for r in (resp.data or []):
                rows.append({
                    "Handle":   r["handle"],
                    "Avg CLV":  float(r.get("avg_clv") or 0),
                    "CLV Bets": int(r.get("clv_bets") or 0),
                    "Win Rate": float(r.get("win_rate") or 0),
                })
            rows.sort(key=lambda r: r["Avg CLV"], reverse=True)
    except Exception:
        pass

    if not rows:
        st.info(
            "No leaderboard data yet. "
            "Be the first to opt in — log at least 10 bets with CLV data, "
            "then toggle **Appear on leaderboard** above."
        )
        return

    # ── Podium ────────────────────────────────────────────────────────────────
    import html as _html_mod
    medals = ["🥇", "🥈", "🥉"]
    podium_cols = st.columns(min(3, len(rows)))
    for idx, (col, row) in enumerate(zip(podium_cols, rows[:3])):
        clv_color = "#00ff88" if row["Avg CLV"] > 0 else "#ff6060"
        safe_handle = _html_mod.escape(str(row["Handle"]))
        col.markdown(f"""
        <div style='background:rgba(0,212,255,0.06);border:1px solid #00d4ff33;
                    border-radius:12px;padding:1rem;text-align:center;'>
            <div style='font-size:2rem'>{medals[idx]}</div>
            <div style='font-size:1.1rem;font-weight:700;margin:4px 0'>{safe_handle}</div>
            <div style='color:{clv_color};font-size:1.4rem;font-weight:800'>
                {row['Avg CLV']:+.2f}% CLV
            </div>
            <div style='color:#aaa;font-size:0.8rem'>{int(row['CLV Bets'])} bets · {row['Win Rate']}% win</div>
        </div>
        """, unsafe_allow_html=True)

    st.divider()

    # ── Full table ─────────────────────────────────────────────────────────────
    st.markdown("### 📊 Full Rankings")
    ranked_rows = [
        {
            "Rank":           f"#{i+1}",
            "Handle":         r["Handle"],
            "Avg CLV":        f"{r['Avg CLV']:+.2f}%",
            "CLV Bets":       r["CLV Bets"],
            "Win Rate":       f"{r['Win Rate']}%",
        }
        for i, r in enumerate(rows)
    ]
    st.dataframe(pd.DataFrame(ranked_rows), use_container_width=True, hide_index=True)
    st.caption(
        f"Updated live · Minimum 10 settled bets with CLV required · "
        f"{len(rows)} bettors on the board"
    )


if __name__ == "__main__":
    main()
