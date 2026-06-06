"""
Parlay Builder — quantitative leg selection with market diversification,
correlation penalties, and EV-weighted scoring.

Selection logic:
  - Score each prop by EV score = edge * sqrt(fair_prob)
    (rewards high-edge plays but penalizes extreme longshots)
  - Multi-game parlays enforce:
      * One player per game (no stacking same game)
      * Max 2 legs of the same market type per parlay
      * No two correlated markets on the same player
  - SGPs enforce:
      * One prop per player (no correlated doubles)
      * Market diversity within the same game
      * Scored by combined independence-adjusted EV
"""

import pandas as pd
import math
from itertools import combinations

# ── Correlation groups: markets that are statistically correlated ─────────────
# Picking two from the same group for the same player is penalised / blocked.
CORRELATED_MARKETS = [
    # MLB batter — hits drive total bases, runs, HRR
    {"batter_hits", "batter_total_bases", "batter_hits_runs_rbis",
     "batter_runs_scored", "batter_rbis"},
    # MLB pitcher — strikeouts and outs are highly correlated
    {"pitcher_strikeouts", "pitcher_outs_recorded", "pitcher_hits_allowed"},
    # NBA/WNBA — points drives PRA and combo props
    {"player_points", "player_points_rebounds_assists",
     "player_points_rebounds", "player_points_assists"},
    # NBA/WNBA — rebounds combo
    {"player_rebounds", "player_points_rebounds_assists",
     "player_points_rebounds", "player_rebounds_assists"},
    # NBA/WNBA — assists combo
    {"player_assists", "player_points_rebounds_assists",
     "player_points_assists", "player_rebounds_assists"},
    # NBA/WNBA — steals/blocks
    {"player_steals", "player_blocks", "player_steals_blocks"},
    # NHL — goals/assists both feed points
    {"player_goals", "player_assists", "player_points"},
]

# Market category buckets for diversity enforcement
MARKET_BUCKETS = {
    # MLB batter
    "batter_hits":           "mlb_batter_hit",
    "batter_total_bases":    "mlb_batter_hit",
    "batter_hits_runs_rbis": "mlb_batter_hit",
    "batter_home_runs":      "mlb_batter_power",
    "batter_rbis":           "mlb_batter_rbi",
    "batter_runs_scored":    "mlb_batter_run",
    "batter_stolen_bases":   "mlb_batter_speed",
    # MLB pitcher
    "pitcher_strikeouts":    "mlb_pitcher_k",
    "pitcher_outs_recorded": "mlb_pitcher_out",
    "pitcher_hits_allowed":  "mlb_pitcher_hit",
    "pitcher_walks":         "mlb_pitcher_walk",
    # NBA/WNBA
    "player_points":                   "bball_pts",
    "player_rebounds":                 "bball_reb",
    "player_assists":                  "bball_ast",
    "player_threes":                   "bball_3pm",
    "player_steals":                   "bball_def",
    "player_blocks":                   "bball_def",
    "player_steals_blocks":            "bball_def",
    "player_turnovers":                "bball_to",
    "player_double_double":            "bball_dd",
    "player_points_rebounds_assists":  "bball_combo",
    "player_points_rebounds":          "bball_combo",
    "player_points_assists":           "bball_combo",
    "player_rebounds_assists":         "bball_combo",
    # NHL
    "player_goals":          "nhl_goal",
    "player_assists":        "nhl_ast",
    "player_points":         "nhl_pts",
    "player_shots_on_goal":  "nhl_shot",
    "player_saves":          "nhl_save",
    "player_blocked_shots":  "nhl_block",
    "player_hits":           "nhl_hit",
}


def american_to_decimal(odds: float) -> float:
    if odds > 0:
        return (odds / 100) + 1
    return (100 / abs(odds)) + 1


def decimal_to_american(dec: float) -> str:
    if dec >= 2.0:
        return f"+{int(round((dec - 1) * 100))}"
    return f"{int(round(-100 / (dec - 1)))}"


def parlay_payout(legs: list[float], stake: float = 10.0) -> dict:
    dec = [american_to_decimal(o) for o in legs]
    combined = 1.0
    for d in dec:
        combined *= d
    profit = (combined - 1) * stake
    return {
        "legs": len(legs),
        "combined_decimal": round(combined, 3),
        "american_odds": decimal_to_american(combined),
        "stake": stake,
        "payout": round(profit + stake, 2),
        "profit": round(profit, 2),
    }


def _ev_score(row: dict) -> float:
    """
    EV score for a single leg.
    = edge * sqrt(fair_prob)
    Rewards high-edge plays while penalizing extreme longshots
    (a +500 prop needs a huge edge to justify parlay inclusion).
    """
    edge = row.get("edge", 0.0)
    fair = row.get("fair_est", 0.5)
    if edge <= 0 or fair <= 0:
        return 0.0
    return edge * math.sqrt(fair)


def _are_correlated(market_a: str, market_b: str) -> bool:
    """True if two markets are in the same correlation group."""
    for group in CORRELATED_MARKETS:
        if market_a in group and market_b in group:
            return True
    return False


def _market_bucket(market: str) -> str:
    return MARKET_BUCKETS.get(market, market)


def _score_and_rank(df: pd.DataFrame) -> pd.DataFrame:
    """Add ev_score column and return sorted copy."""
    rows = df.to_dict("records")
    for r in rows:
        r["ev_score"] = _ev_score(r)
    ranked = pd.DataFrame(rows)
    return ranked.sort_values("ev_score", ascending=False)


# ── Multi-Game Parlay ─────────────────────────────────────────────────────────

def get_top_candidates(df: pd.DataFrame, min_odds: int = -300,
                       max_odds: int = 300, n: int = 10) -> pd.DataFrame:
    """
    Top N candidates by EV score, within odds range.
    One row per (player, market) — already deduplicated upstream.
    """
    pool = df[(df["over_odds"] >= min_odds) & (df["over_odds"] <= max_odds)].copy()
    return _score_and_rank(pool).head(n)


def build_multi_game_parlay(df: pd.DataFrame, n_legs: int,
                            min_odds: int = -300, max_odds: int = 300) -> list[dict]:
    """
    Build an n-leg multi-game parlay with:
      - One player per game
      - No correlated markets on the same player
      - Max 2 legs sharing the same market bucket
      - Legs ranked by EV score (edge * sqrt(fair_prob))
    """
    pool = df[(df["over_odds"] >= min_odds) & (df["over_odds"] <= max_odds)].copy()
    ranked = _score_and_rank(pool)

    seen_games = set()
    seen_players = set()
    bucket_counts: dict[str, int] = {}
    player_markets: dict[str, list[str]] = {}
    legs = []

    for _, row in ranked.iterrows():
        if row.get("ev_score", 0) <= 0:
            continue

        game = row["team"]
        player = row["player"]
        market = row.get("market", "")
        bucket = _market_bucket(market)

        # Hard rules
        if game in seen_games:
            continue
        if player in seen_players:
            continue

        # Bucket cap: max 2 legs of same market bucket per parlay
        if bucket_counts.get(bucket, 0) >= 2:
            continue

        # Correlation check: don't add a market correlated to one already
        # on a DIFFERENT player if they're in the same game (SGP-style correlation)
        already_in_game_markets = [
            l["market"] for l in legs if l["team"] == game
        ]
        corr_conflict = any(_are_correlated(market, m) for m in already_in_game_markets)
        if corr_conflict:
            continue

        seen_games.add(game)
        seen_players.add(player)
        bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1
        player_markets.setdefault(player, []).append(market)
        legs.append(row.to_dict())

        if len(legs) == n_legs:
            break

    return legs


# ── Same-Game Parlay (SGP) ────────────────────────────────────────────────────

def _independence_penalty(markets: list[str]) -> float:
    """
    Returns a penalty multiplier 0..1.
    For every correlated pair found, reduce combined EV by 15%.
    Uncorrelated legs return 1.0 (no penalty).
    """
    penalty = 1.0
    for a, b in combinations(markets, 2):
        if _are_correlated(a, b):
            penalty *= 0.85
    return penalty


def build_sgps(df: pd.DataFrame, min_odds: int = -300,
               n_sgps: int = 3, legs_per_sgp: int = 3) -> list[dict]:
    """
    Build SGPs (same-game parlays) with:
      - One prop per player (best EV prop chosen per player)
      - Market bucket diversity within the game
      - Legs scored by independence-adjusted combined EV score
      - Avoid pure duplicates of the same market bucket
    """
    pool = df[df["over_odds"] >= min_odds].copy()
    pool = _score_and_rank(pool)

    game_groups = pool.groupby("team")
    sgp_candidates = []

    for game, group in game_groups:
        # Best EV prop per player (no doubles on same player)
        best_per_player = (
            group.sort_values("ev_score", ascending=False)
            .drop_duplicates(subset=["player"])
        )

        if len(best_per_player) < legs_per_sgp:
            continue

        # Greedy diverse selection: pick legs maximising EV with bucket diversity
        selected = []
        used_buckets: dict[str, int] = {}
        used_players: set = set()

        for _, row in best_per_player.iterrows():
            if row.get("ev_score", 0) <= 0:
                continue
            bucket = _market_bucket(row.get("market", ""))
            player = row["player"]

            if player in used_players:
                continue
            if used_buckets.get(bucket, 0) >= 1:  # strict: 1 per bucket in SGP
                continue

            selected.append(row.to_dict())
            used_buckets[bucket] = used_buckets.get(bucket, 0) + 1
            used_players.add(player)

            if len(selected) == legs_per_sgp:
                break

        if len(selected) < legs_per_sgp:
            continue

        # Score this SGP
        markets = [r.get("market", "") for r in selected]
        ind_penalty = _independence_penalty(markets)
        combined_ev = sum(r.get("ev_score", 0) for r in selected) * ind_penalty

        odds_list = [r["over_odds"] for r in selected]
        payout = parlay_payout(odds_list)

        # Compute SGP correlation tax (r_ij) — measures how much the book
        # suppresses payout relative to independent multiplication of fair probs.
        # r_ij > 1 means positive correlation present; book is charging a tax.
        from edge_model import sgp_correlation_tax
        corr_tax = sgp_correlation_tax(selected, payout["combined_decimal"])

        sgp_candidates.append({
            "game":                 game,
            "legs":                 selected,
            "payout":               payout,
            "combined_ev":          round(combined_ev, 4),
            "independence_penalty": round(ind_penalty, 3),
            "correlation_tax":      corr_tax,
        })

    # Sort SGPs by combined EV score, best first
    sgp_candidates.sort(key=lambda x: x["combined_ev"], reverse=True)
    return sgp_candidates[:n_sgps]


# ── Full Report ───────────────────────────────────────────────────────────────

def build_parlay_report(df: pd.DataFrame, stake: float = 10.0) -> dict:
    """Full parlay report: top candidates, 3/4/5-leg parlays, top SGPs."""
    top10 = get_top_candidates(df, min_odds=-300, max_odds=300, n=10)

    parlays = {}
    for n in [3, 4, 5]:
        legs = build_multi_game_parlay(df, n_legs=n, min_odds=-300, max_odds=300)
        if len(legs) == n:
            odds = [r["over_odds"] for r in legs]
            parlays[f"{n}_leg"] = {
                "legs": legs,
                "payout": parlay_payout(odds, stake),
            }

    sgps = build_sgps(df, min_odds=-300, n_sgps=3, legs_per_sgp=3)

    return {
        "top10": top10.to_dict("records"),
        "parlays": parlays,
        "sgps": sgps,
        "stake": stake,
    }
