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
    if df.empty:
        return df
    rows = df.to_dict("records")
    for r in rows:
        r["ev_score"] = _ev_score(r)
    ranked = pd.DataFrame(rows)
    return ranked.sort_values("ev_score", ascending=False)


# ── Multi-Game Parlay ─────────────────────────────────────────────────────────

def get_top_candidates(df: pd.DataFrame, min_odds: int = -500,
                       max_odds: int = 2000, n: int = 20,
                       per_market: int = 5) -> pd.DataFrame:
    """
    Top N props by edge — up to `per_market` picks per prop/market type.
    Ensures diversity: no single market floods the list.
    Sorted by edge descending. Default: top 20, max 5 per market.
    """
    if df.empty or "edge" not in df.columns:
        return df
    pool = df[(df["over_odds"] >= min_odds) & (df["over_odds"] <= max_odds)].copy()
    pool = pool.sort_values("edge", ascending=False)

    # If market column exists, group by it for diversity; otherwise just head(n)
    if "market" in pool.columns:
        selected = (
            pool.groupby("market", group_keys=False)
                .apply(lambda g: g.head(per_market))
                .sort_values("edge", ascending=False)
                .head(n)
        )
    else:
        selected = pool.head(n)
    return selected


def parlay_ev(legs: list[dict], stake: float = 10.0) -> dict:
    """
    Expected value of a multi-leg parlay.

    win_prob  = product of each leg's fair_est (independent legs assumption)
    EV        = win_prob × combined_decimal − 1  (as fraction of stake)

    Returns dict with win_prob, ev_fraction, ev_dollars, ev_pct.
    """
    if not legs:
        return {"win_prob": 0.0, "ev_fraction": 0.0, "ev_dollars": 0.0, "ev_pct": 0.0}

    win_prob = 1.0
    for leg in legs:
        win_prob *= min(max(float(leg.get("fair_est", 0.5)), 0.001), 0.999)

    dec_odds = [american_to_decimal(r["over_odds"]) for r in legs]
    combined_dec = 1.0
    for d in dec_odds:
        combined_dec *= d

    ev_fraction = win_prob * combined_dec - 1.0   # e.g. 0.08 = +8% EV
    return {
        "win_prob":    round(win_prob, 4),
        "ev_fraction": round(ev_fraction, 4),
        "ev_dollars":  round(ev_fraction * stake, 2),
        "ev_pct":      round(ev_fraction * 100, 2),
    }


def build_multi_game_parlay(df: pd.DataFrame, n_legs: int,
                            min_odds: int = -300, max_odds: int = 300,
                            min_leg_edge: float = 0.01) -> list[dict]:
    """
    Build an n-leg multi-game parlay.

    Rules (in priority order):
      1. One player per game — no stacking the same matchup
      2. One prop per player — best EV prop chosen if a player has multiple
      3. Each leg must have at least min_leg_edge (default 1%) individual edge
      4. Legs ranked by EV score = edge * sqrt(fair_prob)

    No bucket cap: batter_hits from five different games are five independent bets.
    Cross-game correlation is near zero regardless of market type; the "one per game"
    rule is the correct guard, not market-bucket filtering.
    """
    pool = df[(df["over_odds"] >= min_odds) & (df["over_odds"] <= max_odds)].copy()
    # Apply minimum edge floor per leg — only include props with genuine edge
    if "edge" in pool.columns:
        pool = pool[pool["edge"] >= min_leg_edge]
    ranked = _score_and_rank(pool)

    seen_games   = set()
    seen_players = set()
    legs         = []

    for _, row in ranked.iterrows():
        if row.get("ev_score", 0) <= 0:
            continue

        game   = row["team"]
        player = row["player"]

        if game in seen_games:
            continue
        if player in seen_players:
            continue

        seen_games.add(game)
        seen_players.add(player)
        legs.append(row.to_dict())

        if len(legs) == n_legs:
            break

    return legs


# ── Same-Game Parlay (SGP) ────────────────────────────────────────────────────

def _independence_penalty(legs: list[dict]) -> float:
    """
    Copula-based independence penalty for a set of SGP legs.

    Penalty = product(marginals) / copula_joint_probability

    When all legs are independent, ratio = 1.0 (no penalty).
    When legs are correlated, copula_joint > product → ratio < 1.0 (we're
    over-counting EV since the book charges a correlation tax).

    Falls back to the old flat 0.85-per-correlated-pair when scipy is absent.
    """
    try:
        from edge_model import gaussian_copula_joint
        import math

        probs = [min(max(float(r.get("fair_est", 0.5)), 0.001), 0.999) for r in legs]
        product_joint = 1.0
        for p in probs:
            product_joint *= p

        copula_joint = gaussian_copula_joint(legs)
        if copula_joint <= 0:
            return 1.0

        # Penalty = how much we over-count EV by assuming independence
        ratio = product_joint / copula_joint
        return min(max(ratio, 0.1), 1.0)

    except Exception:
        # Fallback: 15% flat penalty per correlated pair
        markets = [r.get("market", "") for r in legs]
        penalty = 1.0
        for a, b in combinations(markets, 2):
            if _are_correlated(a, b):
                penalty *= 0.85
        return penalty


def build_sgps(df: pd.DataFrame, min_odds: int = -300,
               n_sgps: int = 5, legs_per_sgp: int = 3,
               min_leg_edge: float = -0.03) -> list[dict]:
    """
    Build Same-Game Parlays from every game with 3+ distinct players.

    Selection strategy:
      - One prop per player (best-edge prop chosen per player)
      - No ev_score > 0 requirement — SGPs are built from the best available
        lines in each game, not just positive-edge ones. The combined edge
        across legs + correlation tax determines overall SGP value.
      - Legs with individual edge < min_leg_edge are excluded (floor on quality)
      - No bucket cap: correlation is already handled by the copula penalty in
        _independence_penalty; bucket filtering would block valid same-game stacks
      - SGPs scored by sum(edge per leg) * independence_penalty — surface the
        games where the book has the worst combined pricing
    """
    pool = df[df["over_odds"] >= min_odds].copy()
    pool = _score_and_rank(pool)

    game_groups = pool.groupby("team")
    sgp_candidates = []

    for game, group in game_groups:
        # Best edge prop per player — use edge (not ev_score) so odds range
        # doesn't penalise long-shot legs; floor keeps out truly broken lines
        candidates = (
            group[group["edge"] >= min_leg_edge]
            .sort_values("edge", ascending=False)
            .drop_duplicates(subset=["player"])
        )

        if len(candidates) < legs_per_sgp:
            continue

        # Greedy selection: highest-edge player first, one per player,
        # skip if same player would contribute two correlated markets
        selected: list[dict] = []
        used_players: set = set()
        used_markets: dict[str, str] = {}  # player → market already selected

        for _, row in candidates.iterrows():
            player = row["player"]
            market = row.get("market", "")

            if player in used_players:
                continue

            # Block same player with a correlated market (shouldn't happen after
            # drop_duplicates, but guard for safety)
            existing = used_markets.get(player, "")
            if existing and _are_correlated(market, existing):
                continue

            selected.append(row.to_dict())
            used_players.add(player)
            used_markets[player] = market

            if len(selected) == legs_per_sgp:
                break

        if len(selected) < legs_per_sgp:
            continue

        # Score: sum of individual edges weighted by correlation penalty
        ind_penalty = _independence_penalty(selected)
        combined_ev = sum(r.get("edge", 0) for r in selected) * ind_penalty

        # SGP min combined edge filter — skip SGPs where the copula-adjusted
        # combined edge is negative or negligible. No point betting a 3-leg SGP
        # just because one leg has +2% if the other two drag it below zero.
        if combined_ev <= 0.0:
            continue

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


# ── Diverse SGP combos (3/4/5-leg) ────────────────────────────────────────────

def build_diverse_sgps(
    df: pd.DataFrame,
    n_per_size: int = 5,
    leg_sizes: list[int] = [3, 4, 5],
    min_leg_edge: float = -0.03,
    max_players_per_game: int = 12,
) -> dict[str, list[dict]]:
    """
    For each leg size in leg_sizes, enumerate the top n_per_size diverse SGP
    combinations drawn from ANY game in df.

    Method:
      - Per game: take the top max_players_per_game players by edge (floor = min_leg_edge)
      - Enumerate all C(players, n_legs) combinations — fast for ≤12 players
      - Score each combo by sum(edge) (cheap) to rank quickly
      - For the top n_per_size × 2 candidates do full copula penalty scoring
      - Return top n_per_size across all games, sorted by combined_ev

    Returns dict: {"3_leg": [sgp1,...], "4_leg": [...], "5_leg": [...]}
    """
    from itertools import combinations as _comb
    from edge_model import sgp_correlation_tax

    pool = df[
        (df["over_odds"] >= -300) &
        (df["edge"] >= min_leg_edge)
    ].copy()

    result: dict[str, list[dict]] = {}

    for n_legs in leg_sizes:
        key = f"{n_legs}_leg"
        candidates = []

        for game, group in pool.groupby("team"):
            players = (
                group.sort_values("edge", ascending=False)
                .drop_duplicates(subset=["player"])
                .head(max_players_per_game)
            )
            if len(players) < n_legs:
                continue

            rows = players.to_dict("records")

            # Score all combos cheaply (sum of edges)
            quick_scored = []
            for idx_combo in _comb(range(len(rows)), n_legs):
                selected = [rows[i] for i in idx_combo]
                quick_score = sum(r.get("edge", 0) for r in selected)
                quick_scored.append((quick_score, selected))

            quick_scored.sort(key=lambda x: x[0], reverse=True)

            # Full copula scoring on top 2× candidates per game
            for _, selected in quick_scored[: n_per_size * 2]:
                ind_penalty  = _independence_penalty(selected)
                combined_ev  = sum(r.get("edge", 0) for r in selected) * ind_penalty
                # Skip combos with non-positive combined edge
                if combined_ev <= 0.0:
                    continue
                odds_list    = [r["over_odds"] for r in selected]
                payout       = parlay_payout(odds_list)
                corr_tax     = sgp_correlation_tax(selected, payout["combined_decimal"])

                candidates.append({
                    "game":                 game,
                    "legs":                 selected,
                    "payout":               payout,
                    "combined_ev":          round(combined_ev, 4),
                    "independence_penalty": round(ind_penalty, 3),
                    "correlation_tax":      corr_tax,
                })

        candidates.sort(key=lambda x: x["combined_ev"], reverse=True)
        result[key] = candidates[:n_per_size]

    return result


# ── Full Report ───────────────────────────────────────────────────────────────

def build_parlay_report(df: pd.DataFrame, stake: float = 10.0,
                        full_df: pd.DataFrame | None = None) -> dict:
    """
    Full parlay report.
    df       — filtered props (used for multi-game parlay leg selection)
    full_df  — all props before edge filter (used for SGP combo generation so
               games with thin-but-playable lines still appear in SGPs)
    """
    if df.empty or "over_odds" not in df.columns:
        return {"top10": [], "parlays": {}, "sgps": [], "diverse_sgps": {},
                "stake": stake, "pos_edge_games": 0, "total_games": 0}
    sgp_source = full_df if (full_df is not None and not full_df.empty) else df
    top10 = get_top_candidates(df, min_odds=-300, max_odds=300, n=20, per_market=5)

    # Count how many games have at least one positive-edge play
    pos_edge_games = (
        int(df[df["edge"] > 0]["team"].nunique())
        if "edge" in df.columns and not df.empty else 0
    )

    parlays = {}
    for n in [2, 3, 4, 5]:
        if pos_edge_games < n:
            continue  # not enough qualifying games for this leg count
        legs = build_multi_game_parlay(df, n_legs=n, min_odds=-300, max_odds=300, min_leg_edge=0.01)
        if len(legs) == n:
            odds = [r["over_odds"] for r in legs]
            parlays[f"{n}_leg"] = {
                "legs":   legs,
                "payout": parlay_payout(odds, stake),
                "ev":     parlay_ev(legs, stake),
            }

    sgps = build_sgps(sgp_source, min_odds=-300, n_sgps=5, legs_per_sgp=3)

    # Diverse multi-size SGPs — always shown, uses full prop pool for wider coverage
    diverse_sgps = build_diverse_sgps(sgp_source, n_per_size=5, leg_sizes=[3, 4, 5])

    return {
        "top10":          top10.to_dict("records"),
        "parlays":        parlays,
        "sgps":           sgps,
        "diverse_sgps":   diverse_sgps,
        "stake":          stake,
        "pos_edge_games": pos_edge_games,
        "total_games":    int(df["team"].nunique()) if not df.empty else 0,
    }
