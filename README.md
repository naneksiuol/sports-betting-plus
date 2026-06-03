# Sports Betting Plus 🏆

**Advanced MLB Player Props Analysis & Value Betting Platform**

Repository for data-driven sports betting tools focused on MLB, starting with **1+ Hits Props**.

## 🚀 Features

- **Hits Board**: Real-time player props with book odds, implied probabilities, and model fair estimates.
- **Expected Stats**: xBA, xSLG, xwOBA, ERA vs xERA for pitchers and advanced batted ball metrics.
- **Value Detection**: Identify +EV bets where fair probability exceeds book implied odds.
- **Advanced Metrics**: Sweet spot %, barrel rate, hard hit %, whiff %, best speed, hyper speed for deeper analysis.

## 📊 Data Sources

- `data/hits_board-1.csv`: Daily hits prop board with last 5 games hit rate, American odds for 1+ hit, book implied prob, and fair model estimate.
- `data/expected_stats.csv`: Expected and actual batting/pitching stats (BA, SLG, wOBA, ERA, xERA) for 2026 season.
- `data/stats.csv`: Advanced Statcast-style metrics including K%, BB%, sweet spot, barrels, hard hit, exit velo metrics, whiff/swing %.

## 📁 Project Structure (Planned)

```
sports-betting-plus/
├── data/
│   ├── hits_board-1.csv
│   ├── expected_stats.csv
│   └── stats.csv
├── src/
│   ├── value_finder.py          # Script to scan for +EV bets
│   ├── stats_analyzer.py        # EDA and correlations
│   └── prop_dashboard.py        # Streamlit/Gradio interactive dashboard
├── notebooks/
│   └── hits_value_betting.ipynb
├── README.md
└── requirements.txt
└── .gitignore
```

## 🔍 How to Use (Coming Soon)

1. Load the hits board CSV
2. Filter where `fair_est > book_implied` (or close) for positive expected value
3. Cross-reference with expected stats (e.g. high xwOBA, hard hit rate) and recent form (last5) for confidence
4. Consider pitcher matchups from expected_stats.csv
5. Size bets according to edge, odds, and bankroll management

## 🛠️ Tech Stack

- Python (pandas, numpy, matplotlib/seaborn, plotly, scikit-learn)
- Streamlit or Gradio for beautiful interactive dashboards
- Jupyter for analysis
- Future: Live odds API integration, automated backtesting, Kelly criterion bet sizer, alerts

## 🎯 Goals

Build transparent, model-backed tools to uncover consistent edges in MLB player props markets. Focus on high-volume, beatable props like **1+ Hits**, total bases, RBIs, and strikeouts.

**"Edge lives in the data."**

---

*Initialized and structured by Grok | June 2026 | For @naneksiuol*