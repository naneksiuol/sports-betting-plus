# Sports Betting Plus ⚾

**Advanced MLB Player Props Analysis & Value Betting Platform**

Repository for data-driven sports betting tools focused on MLB, starting with **1+ Hits Props**.

## ⚡ Features

- **Hits Board**: Real-time player props with book odds, implied probabilities, and model fair estimates.
- **Interactive Streamlit Dashboard**: Beautiful, filterable UI to explore value bets instantly.
- **Expected Stats**: xBA, xSLG, xwOBA, ERA vs xERA for pitchers and advanced batted ball metrics (coming soon in dashboard).
- **Value Detection**: Identify +EV bets where fair probability exceeds book implied odds.
- **Advanced Metrics**: Sweet spot %, barrel rate, hard hit %, whiff %, best speed, hyper speed for deeper analysis.

## 🚀 Quick Start — Run the Dashboard

```bash
# 1. Clone the repo
git clone https://github.com/naneksiuol/sports-betting-plus.git
cd sports-betting-plus

# 2. Install dependencies (first time only)
pip install -r requirements.txt

# 3. Launch the interactive dashboard
streamlit run src/props_dashboard.py
```

The dashboard will open in your browser at `http://localhost:8501`.

**Dashboard Highlights:**
- Sidebar filters for edge threshold, recent form (last5), teams, and player search
- Live KPI cards (value bets count, average edge, best play)
- Color-coded sortable table of value bets
- Interactive Plotly scatter: Fair Prob vs Book Implied (points above diagonal = value)
- Top value plays bar chart
- Edge distribution histogram
- One-click CSV download of filtered bets

## 📊 Data Sources

- `data/hits_board-1.csv`: Daily hits prop board with last 5 games hit rate, American odds for 1+ hit, book implied prob, and fair model estimate.
- `data/expected_stats.csv`: Expected and actual batting/pitching stats (BA, SLG, wOBA, ERA, xERA) for 2026 season *(add to data/ folder to expand dashboard)*.
- `data/stats.csv`: Advanced Statcast-style metrics including K%, BB%, sweet spot, barrels, hard hit, exit velo metrics, whiff/swing % *(add to expand)*.

## 📁 Project Structure

```
sports-betting-plus/
├── data/
│   ├── hits_board-1.csv          ✅ Added
│   ├── expected_stats.csv        ⏳ Ready to add
│   └── stats.csv                 ⏳ Ready to add
├── src/
│   ├── value_finder.py           ✅ CLI value scanner
│   └── props_dashboard.py        ✅ Full Streamlit app
├── notebooks/                  ⏳ Future analysis notebooks
├── README.md
├── requirements.txt
└── .gitignore
```

## 🔍 How the Value Engine Works

1. Load the hits board CSV
2. Calculate **edge** = `fair_est` − `book_implied`
3. Filter where `edge >= threshold` (default 3%+)
4. Cross-reference with recent form (`last5`) and team
5. Visualize discrepancies on the Fair vs Book scatter (above the diagonal line = +EV)

## 🛠️ Tech Stack

- **Python**: pandas, numpy, plotly, streamlit
- **Visualization**: Interactive Plotly charts (scatter, bar, histogram)
- **Future**: Live odds API, backtesting engine, Kelly criterion sizer, multi-prop correlation analysis

## 🎯 Goals

Build transparent, model-backed tools to uncover consistent edges in MLB player props markets. Focus on high-volume, beatable props like **1+ Hits**, total bases, and strikeouts.

**"Edge lives in the data."**

---

*Sports Betting Plus · Built with Grok · June 2026 · For @naneksiuol*