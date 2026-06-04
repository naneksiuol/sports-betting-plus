import os
import requests
import pandas as pd

ODDS_API_BASE = "https://api.the-odds-api.com/v4"


def _api_key():
    key = os.environ.get("ODDS_API_KEY", "")
    if not key:
        raise ValueError("ODDS_API_KEY not set")
    return key


def get_mlb_hits_props() -> pd.DataFrame:
    """
    Fetch MLB batter hits player props from The Odds API.
    Returns a DataFrame with columns: player, team, book, market, over_odds, over_line, implied_prob
    """
    url = f"{ODDS_API_BASE}/sports/baseball_mlb/events"
    events_resp = requests.get(url, params={"apiKey": _api_key()}, timeout=15)
    events_resp.raise_for_status()
    events = events_resp.json()

    if not events:
        return pd.DataFrame()

    # Fetch props for each event (limit to avoid burning quota)
    rows = []
    for event in events[:20]:
        event_id = event["id"]
        home = event.get("home_team", "")
        away = event.get("away_team", "")

        props_url = f"{ODDS_API_BASE}/sports/baseball_mlb/events/{event_id}/odds"
        try:
            resp = requests.get(
                props_url,
                params={
                    "apiKey": _api_key(),
                    "markets": "batter_hits",
                    "oddsFormat": "american",
                    "regions": "us",
                },
                timeout=15,
            )
            if resp.status_code == 422:
                continue
            resp.raise_for_status()
        except requests.HTTPError:
            continue

        data = resp.json()
        bookmakers = data.get("bookmakers", [])
        if not bookmakers:
            continue

        for book in bookmakers:
            book_name = book["title"]
            for market in book.get("markets", []):
                if market["key"] != "batter_hits":
                    continue
                for outcome in market.get("outcomes", []):
                    if outcome.get("name") != "Over":
                        continue
                    american_odds = outcome["price"]
                    line = outcome.get("point", 0.5)
                    # Convert american odds to implied probability
                    if american_odds > 0:
                        implied = 100 / (american_odds + 100)
                    else:
                        implied = abs(american_odds) / (abs(american_odds) + 100)

                    player_name = outcome.get("description", outcome.get("name", "Unknown"))
                    # Determine team from game context (rough)
                    team = ""
                    rows.append(
                        {
                            "player": player_name,
                            "team": team,
                            "home_team": home,
                            "away_team": away,
                            "book": book_name,
                            "line": line,
                            "over_odds": american_odds,
                            "book_implied": round(implied, 4),
                        }
                    )

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)

    # Consensus: average implied prob across books per player+line
    consensus = (
        df.groupby(["player", "line"])
        .agg(
            book_implied=("book_implied", "mean"),
            over_odds=("over_odds", "mean"),
            home_team=("home_team", "first"),
            away_team=("away_team", "first"),
        )
        .reset_index()
    )

    # Simple fair estimate: add a 3% baseline edge to consensus (no-vig style approx)
    # Real model would use historical hit rates; this gives a working starting point
    consensus["fair_est"] = (consensus["book_implied"] * 1.05).clip(upper=0.99)
    consensus["edge"] = consensus["fair_est"] - consensus["book_implied"]
    consensus["team"] = consensus.apply(
        lambda r: f"{r['away_team']} @ {r['home_team']}", axis=1
    )

    return consensus[["player", "team", "line", "over_odds", "book_implied", "fair_est", "edge"]]


def get_remaining_requests() -> dict:
    """Check how many API requests remain."""
    url = f"{ODDS_API_BASE}/sports"
    resp = requests.get(url, params={"apiKey": _api_key()}, timeout=10)
    return {
        "requests_used": resp.headers.get("x-requests-used"),
        "requests_remaining": resp.headers.get("x-requests-remaining"),
        "requests_last": resp.headers.get("x-requests-last"),
    }
