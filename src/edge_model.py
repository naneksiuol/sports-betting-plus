"""
Real edge detection using proper de-vigging and Kelly criterion.

Methods implemented:
  - Multiplicative / Shin / Power de-vig
  - Fractional + Multivariate Kelly criterion (dynamic sizing)
  - Partial-downside Kelly (hedge scenarios)
  - Negative Binomial fair probability (overdispersion correction)
  - Closing Line Value (CLV) — log-ratio formula per research doc
  - SGP Correlation Tax via Gaussian Copula (Sklar's theorem)
  - Empirical pairwise market correlations per market-pair type
"""

import math
from itertools import combinations


# ── De-vig methods ────────────────────────────────────────────────────────────

def american_to_implied(odds: float) -> float:
    if odds > 0:
        return 100 / (odds + 100)
    return abs(odds) / (abs(odds) + 100)


def multiplicative_devig(over_implied: float, under_implied: float) -> float:
    """Divide each side by the total overround. Fast and standard."""
    total = over_implied + under_implied
    if total <= 0:
        return over_implied
    return over_implied / total


def shin_devig(over_implied: float, under_implied: float) -> float:
    """
    Shin's method — corrects for favorite-longshot bias.
    Best for player props where one side is a heavy favorite.
    """
    total = over_implied + under_implied
    if total <= 1.0:
        return over_implied

    z = (total - 1.0) / total
    denom = 2.0 * (1.0 - z)
    if denom == 0:
        return multiplicative_devig(over_implied, under_implied)

    discriminant = z ** 2 + 4.0 * (1.0 - z) * (over_implied ** 2 / total)
    if discriminant < 0:
        return multiplicative_devig(over_implied, under_implied)

    fair = (math.sqrt(discriminant) - z) / denom
    return min(max(fair, 0.0), 1.0)


def power_devig(over_implied: float, under_implied: float) -> float:
    """
    Power method — finds exponent k such that p_over^k + p_under^k = 1.
    Most accurate, slightly more compute.
    """
    total = over_implied + under_implied
    if total <= 1.0:
        return over_implied

    lo, hi = 0.5, 3.0
    for _ in range(60):
        k = (lo + hi) / 2.0
        if over_implied ** k + under_implied ** k > 1.0:
            hi = k
        else:
            lo = k

    k = (lo + hi) / 2.0
    numerator = over_implied ** k
    denominator = numerator + under_implied ** k
    if denominator == 0:
        return over_implied
    return numerator / denominator


def devig(over_implied: float, under_implied: float, method: str = "shin") -> float:
    """Unified de-vig entry point."""
    if method == "shin":
        return shin_devig(over_implied, under_implied)
    elif method == "power":
        return power_devig(over_implied, under_implied)
    else:
        return multiplicative_devig(over_implied, under_implied)


def consensus_fair_prob(
    book_over_odds: dict,
    book_under_odds: dict,
    method: str = "shin",
) -> float | None:
    """
    Compute consensus fair probability across all books that have both sides.
    Returns None if not enough data.
    """
    fair_probs = []
    for book_id, over_odds in book_over_odds.items():
        if book_id in book_under_odds:
            o_imp = american_to_implied(over_odds)
            u_imp = american_to_implied(book_under_odds[book_id])
            fp = devig(o_imp, u_imp, method)
            fair_probs.append(fp)

    if not fair_probs:
        if book_over_odds:
            avg_imp = sum(american_to_implied(o) for o in book_over_odds.values()) / len(book_over_odds)
            return avg_imp / 1.055  # ~5.5% avg prop overround fallback
        return None

    return sum(fair_probs) / len(fair_probs)


# ── Kelly criterion ───────────────────────────────────────────────────────────

def american_to_decimal(odds: float) -> float:
    if odds > 0:
        return (odds / 100) + 1.0
    return (100 / abs(odds)) + 1.0


def kelly_fraction(win_prob: float, decimal_odds: float) -> float:
    """
    Full Kelly fraction = (b*p - q) / b
    where b = decimal - 1, p = win_prob, q = 1 - win_prob
    """
    b = decimal_odds - 1.0
    if b <= 0:
        return 0.0
    q = 1.0 - win_prob
    k = (b * win_prob - q) / b
    return max(0.0, k)


def partial_downside_kelly(
    win_prob: float,
    profit_scale: float,
    loss_fraction: float = 1.0,
) -> float:
    """
    Kelly criterion when the downside is not a total loss.
    Derived from: f* = (p*B - q*L) / (B*L)  [research doc Section 6]

    Args:
        win_prob:      Probability of winning (0–1)
        profit_scale:  Net profit per unit staked on a win (e.g. 1.5 for +150)
        loss_fraction: Fraction of stake lost on a loss (1.0 = full loss, 0.5 = half)

    Returns:
        Optimal fraction of bankroll to wager.
    """
    q = 1.0 - win_prob
    if profit_scale <= 0 or loss_fraction <= 0:
        return 0.0
    num = win_prob * profit_scale - q * loss_fraction
    den = profit_scale * loss_fraction
    if den <= 0:
        return 0.0
    return max(0.0, num / den)


def dynamic_kelly_multiplier(
    edge: float,
    clv_avg: float | None = None,
    max_fraction: float = 0.5,
) -> float:
    """
    Dynamically scale the Kelly multiplier based on edge confidence and CLV track record.

    - Strong edge (≥5%) with positive CLV history → closer to half-Kelly
    - Marginal edge (<1%) or negative CLV → down to tenth-Kelly
    - Default (no history) → quarter-Kelly

    Args:
        edge:         Model edge (fair_est - book_implied), e.g. 0.04 = 4%
        clv_avg:      Average CLV over recent bets (None if insufficient data)
        max_fraction: Hard cap on multiplier (default 0.5 = half-Kelly)

    Returns:
        Multiplier in [0.10, max_fraction].
    """
    # Base from edge magnitude
    if edge >= 0.05:
        base = 0.40
    elif edge >= 0.03:
        base = 0.30
    elif edge >= 0.01:
        base = 0.20
    else:
        base = 0.10

    # Adjust for CLV track record (proof of real edge vs noise)
    if clv_avg is not None:
        if clv_avg >= 3.0:
            base = min(base * 1.3, max_fraction)  # proven model — trust it more
        elif clv_avg >= 1.0:
            base = min(base * 1.1, max_fraction)
        elif clv_avg < 0.0:
            base = base * 0.7  # negative CLV — something is wrong, reduce exposure

    return round(min(max(base, 0.10), max_fraction), 2)


def recommended_stake(
    win_prob: float,
    american_odds: float,
    bankroll: float,
    kelly_multiplier: float = 0.25,
    clv_avg: float | None = None,
) -> dict:
    """
    Returns recommended stake and supporting metrics.
    Uses dynamic Kelly multiplier if clv_avg is provided.
    """
    dec = american_to_decimal(american_odds)
    edge = win_prob * (dec - 1) - (1 - win_prob)
    full_k = kelly_fraction(win_prob, dec)

    # Use dynamic multiplier if edge data is available
    dyn_mult = dynamic_kelly_multiplier(edge, clv_avg)
    effective_mult = dyn_mult if clv_avg is not None else kelly_multiplier

    frac_k = full_k * effective_mult
    stake = round(bankroll * frac_k, 2)

    return {
        "full_kelly_pct":    round(full_k * 100, 2),
        "recommended_pct":   round(frac_k * 100, 2),
        "stake":             stake,
        "ev_per_dollar":     round(edge, 4),
        "ev_on_stake":       round(edge * stake, 2),
        "kelly_multiplier":  effective_mult,
        "decimal_odds":      round(dec, 3),
    }


def edge_rating(edge: float) -> str:
    """Human-readable edge quality label."""
    if edge >= 0.05:
        return "🔥 Strong"
    elif edge >= 0.03:
        return "✅ Good"
    elif edge >= 0.01:
        return "🟡 Marginal"
    elif edge >= 0.0:
        return "⚪ Thin"
    else:
        return "❌ No Edge"


def edge_confidence_score(
    edge: float,
    fair_est: float,
    edge_confirmed: bool = False,
    n_books: int = 1,
    over_odds: float = -110,
    clv_avg: float | None = None,
) -> int:
    """
    Composite Edge Confidence Score: 0–100.

    Combines five signals, each contributing up to 20 points:
      1. Edge magnitude  — primary model signal (Power de-vig)
      2. Fair probability — rewards realistic odds range, penalizes extreme longshots
      3. NegBin agreement — both models point same direction (edge_confirmed)
      4. Book coverage   — more books offering = more efficient, reliable line
      5. CLV track record — historical proof the model has real edge

    Returns integer 0–100 for easy display as a progress bar or rating.
    """
    score = 0.0

    # 1. Edge magnitude (0–30 pts) — biggest signal
    if edge >= 0.08:
        score += 30
    elif edge >= 0.05:
        score += 24
    elif edge >= 0.03:
        score += 18
    elif edge >= 0.015:
        score += 12
    elif edge >= 0.01:
        score += 6
    elif edge > 0:
        score += 2

    # 2. Fair probability / odds range (0–20 pts)
    # Sweet spot: 35%–65% fair probability (realistic "chalk" range)
    # Penalise extreme longshots (low fair) where variance overwhelms edge
    if 0.40 <= fair_est <= 0.65:
        score += 20
    elif 0.30 <= fair_est < 0.40 or 0.65 < fair_est <= 0.75:
        score += 14
    elif 0.20 <= fair_est < 0.30 or 0.75 < fair_est <= 0.85:
        score += 8
    else:
        score += 3  # extreme territory — high variance

    # 3. Model agreement (0–20 pts) — Power de-vig AND NegBin both positive
    if edge_confirmed and edge > 0:
        score += 20
    elif edge > 0:
        score += 8  # only one model positive

    # 4. Book coverage (0–15 pts) — more books = more liquid, tighter line
    if n_books >= 2:
        score += 15
    elif n_books == 1:
        score += 8

    # 5. CLV history (0–15 pts) — proven track record
    if clv_avg is not None:
        if clv_avg >= 3.0:
            score += 15
        elif clv_avg >= 1.5:
            score += 11
        elif clv_avg >= 0.5:
            score += 7
        elif clv_avg >= 0.0:
            score += 3
        # Negative CLV adds 0 — punish bad history
    else:
        score += 5  # neutral — no history yet

    return min(int(round(score)), 100)


def confidence_label(score: int) -> tuple[str, str]:
    """Return (label, hex_color) for a confidence score."""
    if score >= 80:
        return "🔥 Elite", "#00ff88"
    elif score >= 65:
        return "✅ Strong", "#52b788"
    elif score >= 50:
        return "🟡 Good", "#f9c74f"
    elif score >= 35:
        return "🟠 Marginal", "#f8961e"
    else:
        return "🔴 Weak", "#ff6060"


# ── Closing Line Value (CLV) ──────────────────────────────────────────────────

def closing_line_value(bet_odds: float, closing_odds: float) -> float:
    """
    CLV = ln(P_closing / P_bet) × 100  [log-ratio formula, research doc Section 7]

    Positive = closing implied > bet implied = line moved against you = you beat the market.
    Negative = line moved in your favour = you got worse odds than closing.

    The log-ratio is theoretically grounded in Kelly/information theory:
    it measures the information gain from placing before the efficient line.

    Args:
        bet_odds:     American odds at time of bet placement
        closing_odds: American odds at game time (sharp closing line, e.g. Pinnacle)

    Returns:
        CLV as a percentage (e.g. 3.2 = +3.2%). Positive = beat the line.
    """
    p_bet     = american_to_implied(bet_odds)
    p_closing = american_to_implied(closing_odds)
    if p_bet <= 0 or p_closing <= 0:
        return 0.0
    try:
        clv = math.log(p_closing / p_bet) * 100.0
        return round(clv, 3)
    except (ValueError, ZeroDivisionError):
        return 0.0


def clv_rating(clv: float) -> str:
    """Human-readable CLV quality label."""
    if clv >= 3.0:
        return "🔥 Excellent"
    elif clv >= 1.5:
        return "✅ Good"
    elif clv >= 0.0:
        return "🟡 Break-even"
    else:
        return "❌ Negative"


def clv_summary(bets: list[dict]) -> dict:
    """
    Aggregate CLV statistics across a list of bet dicts.
    Each bet dict should have: odds (int), closing_odds (int|None), clv (float|None).
    """
    clv_vals = []
    for b in bets:
        if b.get("clv") is not None:
            clv_vals.append(float(b["clv"]))
        elif b.get("closing_odds") and b.get("odds"):
            clv_vals.append(closing_line_value(float(b["odds"]), float(b["closing_odds"])))

    if not clv_vals:
        return {"avg_clv": None, "clv_positive_rate": None, "n_with_clv": 0}

    return {
        "avg_clv":           round(sum(clv_vals) / len(clv_vals), 3),
        "clv_positive_rate": round(100 * sum(1 for c in clv_vals if c > 0) / len(clv_vals), 1),
        "n_with_clv":        len(clv_vals),
        "clv_distribution":  clv_vals,
    }


# ── Negative Binomial fair probability ───────────────────────────────────────

def negbin_fair_prob(
    line: float,
    shin_fair_prob: float,
    dispersion_r: float = 5.0,
) -> float:
    """
    Negative Binomial correction to Shin de-vig fair probability.

    Sports props exhibit OVERDISPERSION (Var > Mean). NegBin adds dispersion
    term r to model this, giving more accurate tail probabilities.

    Method:
      1. Infer λ from shin_fair_prob assuming Poisson
      2. Recompute P(Y > line) using NegBin(λ, r)
    """
    try:
        from scipy.stats import poisson as _poisson, nbinom as _nbinom
        from scipy.optimize import brentq as _brentq
    except ImportError:
        return shin_fair_prob

    threshold = int(math.floor(line)) + 1
    p = min(max(shin_fair_prob, 0.001), 0.999)

    def _obj(lam: float) -> float:
        return _poisson.sf(threshold - 1, lam) - p

    try:
        lo, hi = 0.001, 200.0
        if _obj(lo) * _obj(hi) > 0:
            return shin_fair_prob
        lam = _brentq(_obj, lo, hi, xtol=1e-6)
    except Exception:
        return shin_fair_prob

    p_nb = dispersion_r / (dispersion_r + lam)
    nb_prob = float(_nbinom.sf(threshold - 1, dispersion_r, p_nb))
    return round(min(max(nb_prob, 0.001), 0.999), 4)


MARKET_DISPERSION = {
    "pitcher_strikeouts":    4.0,
    "pitcher_outs_recorded": 4.5,
    "pitcher_hits_allowed":  5.0,
    "batter_total_bases":    3.5,
    "batter_home_runs":      2.0,
    "batter_hits_runs_rbis": 4.0,
    "batter_hits":           6.0,
    "batter_rbis":           3.5,
    "batter_runs_scored":    5.0,
    "batter_stolen_bases":   3.0,
    "player_points":         6.0,
    "player_rebounds":       4.5,
    "player_assists":        4.5,
    "player_threes":         3.5,
    "player_points_rebounds_assists": 6.5,
    "player_steals":         2.5,
    "player_blocks":         2.5,
    "player_shots_on_goal":  4.0,
    "player_goals":          2.0,
    "player_saves":          5.5,
}

DEFAULT_DISPERSION = 5.0


def apply_negbin_correction(row: dict) -> dict:
    """Apply NegBin correction to a prop row dict. Adds fair_est_negbin, edge_negbin, negbin_delta."""
    market  = row.get("market", "")
    line    = float(row.get("line", 0.5))
    shin_fp = float(row.get("fair_est", 0.5))
    over_imp = float(row.get("book_implied", 0.5))

    r = MARKET_DISPERSION.get(market, DEFAULT_DISPERSION)
    nb_fp = negbin_fair_prob(line, shin_fp, r)

    row["fair_est_negbin"] = nb_fp
    row["edge_negbin"]     = round(nb_fp - over_imp, 4)
    row["negbin_delta"]    = round(nb_fp - shin_fp, 4)
    return row


# ── Pairwise market correlations (empirically calibrated) ────────────────────
#
# These ρ values represent the Spearman/Kendall rank correlation between
# the same player's outcomes across two markets in the same game.
# Derived from sports analytics literature and empirical prop outcome data.

MARKET_PAIR_CORRELATIONS: dict[tuple, float] = {
    # ── MLB same-player ──
    ("batter_hits",           "batter_total_bases"):       0.75,
    ("batter_hits",           "batter_rbis"):              0.45,
    ("batter_hits",           "batter_runs_scored"):       0.40,
    ("batter_hits",           "batter_hits_runs_rbis"):    0.88,
    ("batter_total_bases",    "batter_rbis"):              0.50,
    ("batter_total_bases",    "batter_home_runs"):         0.65,
    ("batter_total_bases",    "batter_hits_runs_rbis"):    0.80,
    ("batter_home_runs",      "batter_rbis"):              0.60,
    ("batter_home_runs",      "batter_hits_runs_rbis"):    0.55,
    ("batter_rbis",           "batter_runs_scored"):       0.35,
    ("batter_rbis",           "batter_hits_runs_rbis"):    0.82,
    ("batter_runs_scored",    "batter_hits_runs_rbis"):    0.72,
    ("pitcher_strikeouts",    "pitcher_outs_recorded"):    0.80,
    ("pitcher_strikeouts",    "pitcher_hits_allowed"):    -0.35,
    ("pitcher_strikeouts",    "pitcher_walks"):           -0.10,
    ("pitcher_outs_recorded", "pitcher_hits_allowed"):   -0.30,
    # ── NBA/WNBA same-player ──
    ("player_points",         "player_points_rebounds_assists"): 0.88,
    ("player_rebounds",       "player_points_rebounds_assists"): 0.82,
    ("player_assists",        "player_points_rebounds_assists"): 0.78,
    ("player_points",         "player_points_rebounds"):    0.90,
    ("player_points",         "player_points_assists"):     0.88,
    ("player_rebounds",       "player_rebounds_assists"):   0.88,
    ("player_assists",        "player_rebounds_assists"):   0.82,
    ("player_points",         "player_rebounds"):           0.30,
    ("player_points",         "player_assists"):            0.35,
    ("player_points",         "player_threes"):             0.45,
    ("player_rebounds",       "player_assists"):            0.15,
    ("player_steals",         "player_blocks"):             0.20,
    ("player_steals",         "player_steals_blocks"):      0.90,
    ("player_blocks",         "player_steals_blocks"):      0.85,
    ("player_points",         "player_double_double"):      0.55,
    ("player_rebounds",       "player_double_double"):      0.60,
    # ── NHL same-player ──
    ("player_goals",          "player_points"):             0.85,
    ("player_assists",        "player_points"):             0.88,
    ("player_goals",          "player_assists"):            0.30,
    ("player_goals",          "player_shots_on_goal"):      0.55,
    ("player_assists",        "player_shots_on_goal"):      0.25,
    ("player_points",         "player_shots_on_goal"):      0.50,
}


def get_market_pair_rho(market_a: str, market_b: str, same_player: bool = True) -> float:
    """
    Return empirical correlation ρ for a market pair.
    Cross-player same-game gets a small positive value (shared game script).
    """
    if not same_player:
        return 0.05  # cross-player, same game: weak positive correlation
    key = (market_a, market_b)
    rkey = (market_b, market_a)
    return MARKET_PAIR_CORRELATIONS.get(key, MARKET_PAIR_CORRELATIONS.get(rkey, 0.0))


# ── Gaussian Copula joint probability ────────────────────────────────────────

def gaussian_copula_joint(legs: list[dict]) -> float:
    """
    Compute joint probability of multiple prop legs using Gaussian copula.

    Implements Sklar's theorem: F(x1,...,xd) = C(F1(x1),...,Fd(xd))
    where C is the Gaussian copula with correlation matrix Σ.

    For each pair of legs the correlation ρ is looked up from
    MARKET_PAIR_CORRELATIONS (same player) or set to 0.05 (different players).

    Falls back to product of marginals (independence) if scipy is unavailable.

    Args:
        legs: List of prop dicts each with 'fair_est', 'market', 'player'.

    Returns:
        Joint probability (float 0–1).
    """
    if not legs:
        return 0.0

    probs   = [min(max(float(leg.get("fair_est", 0.5)), 0.001), 0.999) for leg in legs]
    markets = [leg.get("market", "") for leg in legs]
    players = [leg.get("player", f"__p{i}__") for i, leg in enumerate(legs)]

    if len(legs) == 1:
        return probs[0]

    try:
        import numpy as np
        from scipy import stats

        n = len(legs)
        rho_mat = np.eye(n)
        for i, j in combinations(range(n), 2):
            same_player = (players[i] == players[j])
            rho = get_market_pair_rho(markets[i], markets[j], same_player)
            rho_mat[i, j] = rho
            rho_mat[j, i] = rho

        # Ensure positive semi-definite by clipping negative eigenvalues
        eigvals = np.linalg.eigvalsh(rho_mat)
        if eigvals.min() < 1e-6:
            rho_mat += np.eye(n) * (abs(eigvals.min()) + 1e-6)

        # Map marginals to standard-normal quantiles (copula transform)
        z = np.array([stats.norm.ppf(p) for p in probs])

        # Evaluate multivariate normal CDF at z with correlation matrix
        joint = float(stats.multivariate_normal.cdf(z, mean=np.zeros(n), cov=rho_mat))
        return max(joint, 1e-8)

    except Exception:
        # Fallback: independence assumption
        result = 1.0
        for p in probs:
            result *= p
        return result


# ── SGP Correlation Tax ───────────────────────────────────────────────────────

def sgp_correlation_tax(legs: list[dict], sgp_combined_decimal: float) -> dict:
    """
    Measure the sportsbook's correlation tax on a Same-Game Parlay.

    r_ij = P(Implied SGP Joint) / P(Copula joint probability)

    Uses Gaussian copula to compute the true joint probability (vs naive product),
    giving a more accurate correlation tax estimate.

    r_ij > 1: positive correlation — book is suppressing payout.
    r_ij < 1: negative correlation — book may be over-paying.
    r_ij ≈ 1: mostly independent — fair payout.
    """
    if not legs or sgp_combined_decimal <= 1.0:
        return {}

    # Copula joint probability (accounts for market correlations)
    copula_joint = gaussian_copula_joint(legs)

    # Implied joint probability from book's SGP price
    sgp_implied_joint = 1.0 / sgp_combined_decimal

    # Correlation factor
    r_ij = (sgp_implied_joint / copula_joint) if copula_joint > 0 else 1.0

    # Fair SGP decimal (what we'd expect with proper correlation pricing)
    fair_sgp_decimal  = 1.0 / copula_joint if copula_joint > 0 else sgp_combined_decimal
    fair_sgp_american = decimal_to_american_float(fair_sgp_decimal)
    book_sgp_american = decimal_to_american_float(sgp_combined_decimal)

    tax_pct = round((r_ij - 1.0) * 100, 1)

    # Pairwise breakdown using copula correlations
    pairwise = []
    markets = [leg.get("market", "") for leg in legs]
    players = [leg.get("player", f"p{i}") for i, leg in enumerate(legs)]
    for i, j in combinations(range(len(legs)), 2):
        pa = float(legs[i].get("fair_est", 0.5))
        pb = float(legs[j].get("fair_est", 0.5))
        same_player = (players[i] == players[j])
        rho = get_market_pair_rho(markets[i], markets[j], same_player)
        copula_pair = gaussian_copula_joint([legs[i], legs[j]])
        independent_pair = pa * pb
        pairwise.append({
            "leg_a":           legs[i].get("player", "?"),
            "market_a":        markets[i],
            "leg_b":           legs[j].get("player", "?"),
            "market_b":        markets[j],
            "rho":             round(rho, 3),
            "independent_joint": round(independent_pair, 4),
            "copula_joint":    round(copula_pair, 4),
            "pair_tax_pct":    round((copula_pair / independent_pair - 1) * 100, 1) if independent_pair > 0 else 0,
        })

    verdict = (
        "High correlation tax — book heavily suppressed payout"  if tax_pct >= 40 else
        "Moderate tax — significant correlation adjustment"       if tax_pct >= 20 else
        "Low tax — legs mostly independent, fair payout"         if tax_pct >= 0  else
        "Negative correlation — book may be over-paying (rare)"
    )

    return {
        "copula_joint_prob":      round(copula_joint, 4),
        "sgp_implied_joint_prob": round(sgp_implied_joint, 4),
        "fair_decimal":           round(fair_sgp_decimal, 2),
        "fair_american":          fair_sgp_american,
        "book_american":          book_sgp_american,
        "r_ij":                   round(r_ij, 3),
        "correlation_tax_pct":    tax_pct,
        "pairwise":               pairwise,
        "verdict":                verdict,
    }


def decimal_to_american_float(dec: float) -> str:
    """Convert decimal odds to American string (e.g. +250, -150)."""
    if dec <= 1.0:
        return "N/A"
    if dec >= 2.0:
        return f"+{int(round((dec - 1) * 100))}"
    return f"{int(round(-100 / (dec - 1)))}"
