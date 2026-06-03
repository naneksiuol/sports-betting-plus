import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path

st.set_page_config(
    page_title="Sports Betting Plus | MLB 1+ Hits Props",
    page_icon="⚾",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for premium feel
st.markdown("""
<style>
    .main-header {font-size: 2.5rem; font-weight: 700; color: #1a1a2e;}
    .metric-card {background-color: #f8f9fa; padding: 1rem; border-radius: 10px;}
    .value-positive {color: #28a745; font-weight: bold;}
    .value-negative {color: #dc3545;}
    .stDataFrame {font-size: 0.9rem;}
</style>
""", unsafe_allow_html=True)

@st.cache_data(ttl=3600)
def load_data():
    """Load and preprocess the hits board data."""
    data_path = Path("data/hits_board-1.csv")
    if not data_path.exists():
        st.error("Data file not found. Please ensure data/hits_board-1.csv exists in the repo root.")
        st.stop()
    
    df = pd.read_csv(data_path)
    
    # Clean last5 (some are empty strings)
    df['last5'] = pd.to_numeric(df['last5'], errors='coerce').fillna(0.0)
    
    # Calculate edge (positive = value bet)
    df['edge'] = df['fair_est'] - df['book_implied']
    
    # Clean odds display
    df['odds_display'] = df['odds_1plus'].apply(lambda x: f"{int(x)}" if pd.notna(x) else "N/A")
    
    return df


def main():
    df = load_data()
    
    # Header
    st.title("⚾ Sports Betting Plus")
    st.subheader("MLB 1+ Hits Props — Value Dashboard")
    st.caption("Find +EV bets where model fair probability exceeds book implied odds | Data as of latest board")
    
    # Sidebar Filters
    with st.sidebar:
        st.header("⚙️ Filters & Controls")
        
        edge_threshold = st.slider(
            "Minimum Edge (Fair Prob - Book Prob)",
            min_value=0.0,
            max_value=0.12,
            value=0.03,
            step=0.005,
            format="%.3f",
            help="Only show bets where the model thinks the true probability is at least this much higher than the book."
        )
        
        min_last5 = st.slider(
            "Minimum Last 5 Games Hit Rate",
            min_value=0.0,
            max_value=0.75,
            value=0.15,
            step=0.05,
            help="Filter players by recent form (hit rate in last 5 games)."
        )
        
        all_teams = sorted(df['team'].unique())
        selected_teams = st.multiselect(
            "Select Teams",
            options=all_teams,
            default=all_teams,
            help="Filter by specific teams or leave all selected."
        )
        
        player_search = st.text_input(
            "Search Player Name",
            placeholder="e.g. Ohtani, Soto, Witt",
            help="Case-insensitive partial match."
        )
        
        st.divider()
        st.markdown("**Quick Actions**")
        if st.button("Reset All Filters", use_container_width=True):
            st.rerun()
        
        st.caption("Tip: Higher edge + strong recent form = higher confidence value bets.")
    
    # Apply filters
    filtered = df[
        (df['edge'] >= edge_threshold) &
        (df['last5'] >= min_last5) &
        (df['team'].isin(selected_teams)) &
        (df['player'].str.contains(player_search, case=False, na=False))
    ].copy()
    
    # Sort by edge descending by default
    filtered = filtered.sort_values('edge', ascending=False)
    
    # ========== KPI CARDS ==========
    st.markdown("### 📊 Key Metrics")
    
    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    
    total_players = len(df)
    value_count = len(filtered)
    avg_edge = filtered['edge'].mean() if value_count > 0 else 0.0
    best_edge_row = filtered.iloc[0] if value_count > 0 else None
    
    with kpi1:
        st.metric("Total Players on Board", total_players)
    with kpi2:
        st.metric(
            "Value Bets Found", 
            value_count,
            delta=f"{value_count/total_players:.1%} of board" if total_players > 0 else None
        )
    with kpi3:
        st.metric("Average Edge (Value)", f"{avg_edge:.2%}")
    with kpi4:
        if best_edge_row is not None:
            st.metric(
                "Best Value Play",
                f"{best_edge_row['player']} ({best_edge_row['team']})",
                delta=f"+{best_edge_row['edge']:.2%} edge"
            )
        else:
            st.metric("Best Value Play", "No bets meet criteria")
    
    st.divider()
    
    # ========== MAIN TABLE ==========
    st.markdown(f"### 🎯 Value Bets Table ({len(filtered)} plays)")
    
    if len(filtered) == 0:
        st.warning("No value bets match your current filters. Try lowering the edge threshold or adjusting other filters.")
    else:
        # Prepare display dataframe
        display_cols = ['player', 'team', 'last5', 'odds_display', 'book_implied', 'fair_est', 'edge']
        display_df = filtered[display_cols].copy()
        display_df.columns = ['Player', 'Team', 'Last 5 Hit %', 'Odds (1+ Hit)', 'Book Implied %', 'Fair Est. %', 'Edge %']
        
        # Format percentages
        for col in ['Last 5 Hit %', 'Book Implied %', 'Fair Est. %', 'Edge %']:
            display_df[col] = display_df[col].apply(lambda x: f"{x:.1%}" if pd.notna(x) else "N/A")
        
        # Color code edge column using Styler
        def highlight_edge(val):
            try:
                num = float(val.strip('%')) / 100
                if num >= 0.05:
                    return 'background-color: #d4edda; color: #155724; font-weight: bold'  # strong green
                elif num >= 0.03:
                    return 'background-color: #c3e6cb; color: #155724'
                elif num > 0:
                    return 'background-color: #fff3cd; color: #856404'
                else:
                    return 'background-color: #f8d7da; color: #721c24'
            except:
                return ''
        
        styled_df = display_df.style.applymap(
            highlight_edge, 
            subset=['Edge %']
        )
        
        st.dataframe(
            styled_df,
            use_container_width=True,
            hide_index=True,
            height=420
        )
        
        # Download button
        csv = filtered.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Download Filtered Value Bets (CSV)",
            data=csv,
            file_name=f"value_bets_edge_{edge_threshold:.2f}.csv",
            mime="text/csv",
            use_container_width=True
        )
    
    st.divider()
    
    # ========== VISUALIZATIONS ==========
    st.markdown("### 📈 Visual Analysis")
    
    tab1, tab2, tab3 = st.tabs(["🔍 Fair vs Book Scatter", "📆 Top Value Plays", "📊 Edge Distribution"])
    
    with tab1:
        st.markdown("**Fair Probability vs Book Implied** — Points above the gray dashed line represent value bets (model > book). Color = Edge magnitude.")
        
        if len(filtered) > 0:
            fig_scatter = px.scatter(
                filtered,
                x="book_implied",
                y="fair_est",
                color="edge",
                color_continuous_scale="RdYlGn",
                range_color=[-0.05, 0.12],
                hover_data={
                    "player": True,
                    "team": True,
                    "last5": ":.1%",
                    "odds_1plus": True,
                    "edge": ":.2%"
                },
                title="Model Fair Estimate vs Book Implied Probability",
                labels={
                    "book_implied": "Book Implied Probability",
                    "fair_est": "Model Fair Probability",
                    "edge": "Edge"
                },
                height=550
            )
            
            # Add fair = book diagonal line
            fig_scatter.add_trace(
                go.Scatter(
                    x=[0.48, 0.78],
                    y=[0.48, 0.78],
                    mode="lines",
                    name="Fair = Book (no edge)",
                    line=dict(color="gray", width=2, dash="dash"),
                    showlegend=True
                )
            )
            
            fig_scatter.update_layout(
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                coloraxis_colorbar=dict(title="Edge", ticks="outside")
            )
            
            st.plotly_chart(fig_scatter, use_container_width=True)
        else:
            st.info("No data to plot with current filters.")
    
    with tab2:
        st.markdown("**Top 15 Value Bets by Edge** — Horizontal bar chart of the strongest discrepancies.")
        
        if len(filtered) > 0:
            top_n = min(15, len(filtered))
            top_df = filtered.head(top_n).sort_values('edge', ascending=True)
            
            fig_bar = px.bar(
                top_df,
                x="edge",
                y="player",
                color="edge",
                color_continuous_scale="RdYlGn",
                orientation="h",
                hover_data=["team", "last5", "fair_est", "book_implied"],
                title=f"Top {top_n} Highest Edge Plays",
                labels={"edge": "Probability Edge", "player": "Player"},
                height=550
            )
            fig_bar.update_layout(showlegend=False, yaxis={'categoryorder':'total ascending'})
            st.plotly_chart(fig_bar, use_container_width=True)
        else:
            st.info("No value bets to display.")
    
    with tab3:
        st.markdown("**Distribution of Edges Across Filtered Board** — See how much edge is available in your current view.")
        
        if len(filtered) > 1:
            fig_hist = px.histogram(
                filtered,
                x="edge",
                nbins=25,
                color_discrete_sequence=["#636EFA"],
                title="Edge Distribution (Filtered Players)",
                labels={"edge": "Probability Edge"},
                height=450
            )
            fig_hist.add_vline(x=edge_threshold, line_dash="dash", line_color="red", annotation_text="Your threshold")
            st.plotly_chart(fig_hist, use_container_width=True)
        else:
            st.info("Need at least 2 data points for histogram.")
    
    # Footer
    st.divider()
    st.caption(
        "Sports Betting Plus · Built with Streamlit & Plotly · Data-driven MLB prop analysis · "
        "Always bet responsibly. Past performance does not guarantee future results."
    )


if __name__ == "__main__":
    main()
