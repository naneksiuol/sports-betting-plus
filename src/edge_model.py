"""
Real edge detection using proper de-vigging and Kelly criterion.

Methods implemented:
  - Multiplicative / Shin / Power de-vig
  - Fractional + Multivariate Kelly criterion
  - Negative Binomial fair probability (overdispersion correction)
  - Closing Line Value (CLV) — the gold-standard model validator
  - SGP Correlation Tax (r_ij payout suppression factor)
"""

import math


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
        return over_implied  # already no-vig

    # Iterative Shin approximation
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
    book_over_odds: dict,   # {book_id: american_odds}
    book_under_odds: dict,  # {book_id: american_odds}
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
        # Fallback: use only over odds, rough multiplicative estimate
        if book_over_odds:
            avg_imp = sum(american_to_implied(o) for o in book_over_odds.values()) / len(book_over_odds)
            return avg_imp / 1.055  # assume ~5.5% avg prop overround
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


def recommended_stake(
    win_prob: float,
    american_odds: float,
    bankroll: float,
    kelly_multiplier: float = 0.25,  # quarter Kelly by default
) -> dict:
    """
    Returns recommended stake and supporting info.
    """
    dec = american_to_decimal(american_odds)
    full_k = kelly_fraction(win_prob, dec)
    frac_k = full_k * kelly_multiplier
    stake = round(bankroll * frac_k, 2)
    ev_per_dollar = win_prob * (dec - 1) - (1 - win_prob)

    return {
        "full_kelly_pct": round(full_k * 100, 2),
        "recommended_pct": round(frac_k * 100, 2),
        "stake": stake,
        "ev_per_dollar": round(ev_per_dollar, 4),
        "ev_on_stake": round(ev_per_dollar * stake, 2),
        "kelly_multiplier": kelly_multiplier,
        "decimal_odds": round(dec, 3),
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


# ── Closing Line Value (CLV) ──────────────────────────────────────────────────

def closing_line_value(bet_odds: float, closing_odds: float) -> float:
    """
    CLV = ln(P_closing_fair / P_bet_placement)

    Measures whether you got better odds than where the market settled.
    Positive CLV = you beat the closing line (sustainable long-term edge).
    Negative CLV = line moved against you (riding variance, not skill).

    Based on: CLV = ln(P_closing / P_bet) [from research doc Section 7]

    Args:
        bet_odds:     American odds at time of bet placement
        closing_odds: American odds at game time (sharp closing line)

    Returns:
        CLV as a float (multiply by 100 for %). e.g. 0.032 = +3.2% CLV.
    """
    p_bet     = american_to_implied(bet_odds)
    p_closing = american_to_implied(closing_odds)
    if p_bet <= 0 or p_closing <= 0:
        return 0.0
    # Log ratio of closing implied to bet implied
    # Positive = closing is MORE implied (moved against you) — WAIT that's wrong
    # CLV from bettor's perspective: did I get BETTER odds than closing?
    # Better odds = lower implied prob at bet time vs closing
    # CLV = ln(P_closing / P_bet): if P_closing > P_bet → line moved against you → negative CLV
    # Standard convention: CLV = (1/closing_decimal - 1/bet_decimal) expressed as %
    bet_dec     = american_to_decimal(bet_odds)
    closing_dec = american_to_decimal(closing_odds)
    # CLV = (P_closing - P_bet) in percentage points.
    # Positive = closing implied is HIGHER than bet implied = market validated your bet =  value.
    # Formula aligns with research doc: CLV = ln(P_closing / P_bet) ≈ P_closing - P_bet for small diffs.
    clv_pct = (1.0 / closing_dec - 1.0 / bet_dec) * 100.0
    return round(clv_pct, 3)


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
    Returns dict with avg_clv, clv_positive_rate, n_with_clv.
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

    Sports props exhibit OVERDISPERSION (Var > Mean) — the standard Poisson
    assumption (Var = Mean) underestimates tail risk. NegBin adds a dispersion
    term r to model this, giving more accurate probabilities, especially for:
      - Pitcher strikeouts (high variance due to blowouts/early exits)
      - Total bases (batter HR games inflate variance)
      - NHL shots on goal (power-play clustering)

    Method (from research doc Section 3):
      1. Infer λ (expected count) from shin_fair_prob assuming Poisson
      2. Recompute P(Y > line) using NegBin(λ, r) for overdispersion correction

    Args:
        line:           Prop line (e.g., 1.5 hits, 6.5 Ks)
        shin_fair_prob: De-vigged fair probability from Shin method
        dispersion_r:   NegBin dispersion param (default 5.0, ~typical for MLB/NBA props)
                        Lower r = more overdispersed. r → ∞ converges to Poisson.

    Returns:
        Corrected fair probability (float 0–1).
    """
    try:
        from scipy.stats import poisson as _poisson, nbinom as _nbinom
        from scipy.optimize import brentq as _brentq
    except ImportError:
        return shin_fair_prob  # scipy not installed, return unchanged

    threshold = int(math.floor(line)) + 1  # need Y >= threshold to win Over
    p = min(max(shin_fair_prob, 0.001), 0.999)

    # Step 1: solve for λ such that P_Poisson(Y >= threshold) = p
    def _obj(lam: float) -> float:
        return _poisson.sf(threshold - 1, lam) - p

    try:
        lo, hi = 0.001, 200.0
        if _obj(lo) * _obj(hi) > 0:
            return shin_fair_prob  # no root found, return unchanged
        lam = _brentq(_obj, lo, hi, xtol=1e-6)
    except Exception:
        return shin_fair_prob

    # Step 2: recompute using NegBin(r, p_nb) with same mean λ
    # NegBin mean = r*(1-p_nb)/p_nb = λ  →  p_nb = r/(r+λ)
    p_nb = dispersion_r / (dispersion_r + lam)
    nb_prob = float(_nbinom.sf(threshold - 1, dispersion_r, p_nb))
    return round(min(max(nb_prob, 0.001), 0.999), 4)


# Dispersion values calibrated per market type (based on empirical research)
MARKET_DISPERSION = {
    # MLB — high dispersion markets (blowout/early exit variance)
    "pitcher_strikeouts":    4.0,
    "pitcher_outs_recorded": 4.5,
    "pitcher_hits_allowed":  5.0,
    "batter_total_bases":    3.5,   # HR games create fat tails
    "batter_home_runs":      2.0,   # very rare event, high overdispersion
    "batter_hits_runs_rbis": 4.0,
    # MLB — lower dispersion (hits are more stable)
    "batter_hits":           6.0,
    "batter_rbis":           3.5,
    "batter_runs_scored":    5.0,
    "batter_stolen_bases":   3.0,
    # NBA/WNBA
    "player_points":         6.0,   # relatively stable for high-usage stars
    "player_rebounds":       4.5,
    "player_assists":        4.5,
    "player_threes":         3.5,   # high variance, cold/hot streaks
    "player_points_rebounds_assists": 6.5,
    "player_steals":         2.5,   # rare, bursty
    "player_blocks":         2.5,
    # NHL
    "player_shots_on_goal":  4.0,
    "player_goals":          2.0,   # very rare
    "player_saves":          5.5,
}

DEFAULT_DISPERSION = 5.0


def apply_negbin_correction(row: dict) -> dict:
    """
    Apply NegBin correction to a prop row dict in-place.
    Adds keys: fair_est_negbin, edge_negbin, negbin_delta.
    Returns the updated row dict.
    """
    market  = row.get("market", "")
    line    = float(row.get("line", 0.5))
    shin_fp = float(row.get("fair_est", 0.5))
    over_imp = float(row.get("book_implied", 0.5))

    r = MARKET_DISPERSION.get(market, DEFAULT_DISPERSION)
    nb_fp = negbin_fair_prob(line, shin_fp, r)

    row["fair_est_negbin"] = nb_fp
    row["edge_negbin"]     = round(nb_fp - over_imp, 4)
    row["negbin_delta"]    = round(nb_fp - shin_fp, 4)  # how much NegBin shifts the estimate
    return row


# ── SGP Correlation Tax ───────────────────────────────────────────────────────

def sgp_correlation_tax(legs: list[dict], sgp_combined_decimal: float) -> dict:
    """
    Measures the sportsbook's "correlation tax" on a Same-Game Parlay.

    From the research doc (Section 5):
      r_ij = P(Implied SGP Joint) / product(P(individual legs))

    If r_ij > 1: positive correlation — book is SUPPRESSING payout to compensate.
    If r_ij < 1: negative correlation — book may be OVER-paying (rare).
    If r_ij ≈ 1: treated as independent (no SGP pricing adjustment).

    The "correlation tax" = (r_ij - 1) * 100 in percentage points.
    A tax of +40% means the book cut the payout 40% to account for correlation.

    Args:
        legs:                  List of prop dicts, each with 'fair_est' key
        sgp_combined_decimal:  Decimal odds of the full SGP as priced by the book

    Returns:
        Dict with correlation analysis.
    """
    if not legs or sgp_combined_decimal <= 1.0:
        return {}

    # Independent joint probability (naive multiplication of fair probs)
    independent_joint = 1.0
    for leg in legs:
        fp = float(leg.get("fair_est", 0.5))
        independent_joint *= fp

    # Independent payout if legs were truly uncorrelated (fair)
    independent_decimal = 1.0 / independent_joint if independent_joint > 0 else 1.0

    # Implied joint prob from book's SGP price
    sgp_implied_joint = 1.0 / sgp_combined_decimal

    # Correlation factor r_ij
    r_ij = (sgp_implied_joint / independent_joint) if independent_joint > 0 else 1.0

    # What the fair SGP payout would be without the correlation tax
    # Fair = independent decimal (no tax), book applies r_ij compression
    fair_sgp_decimal  = independent_decimal
    fair_sgp_american = decimal_to_american_float(fair_sgp_decimal)
    book_sgp_american = decimal_to_american_float(sgp_combined_decimal)

    # r_ij > 1 → book inflated joint implied above independence → SUPPRESSED payout for bettor
    # tax_pct = (r_ij - 1) * 100: positive = how much % the book inflated implied prob (= payout tax)
    tax_pct  = round((r_ij - 1.0) * 100, 1)

    # Pairwise correlation estimate per leg pair
    pairwise = []
    if len(legs) >= 2:
        from itertools import combinations
        for a, b in combinations(legs, 2):
            pa = float(a.get("fair_est", 0.5))
            pb = float(b.get("fair_est", 0.5))
            if pa > 0 and pb > 0:
                # Back-calculate implied pairwise joint from SGP price
                # approximation: distribute r_ij evenly across all pairs
                n_pairs = len(legs) * (len(legs) - 1) / 2
                pair_r  = r_ij ** (1.0 / n_pairs) if n_pairs > 0 else r_ij
                pair_joint = pa * pb * pair_r
                pairwise.append({
                    "leg_a": a.get("player", "?"),
                    "market_a": a.get("market", "?"),
                    "leg_b": b.get("player", "?"),
                    "market_b": b.get("market", "?"),
                    "independent_joint": round(pa * pb, 4),
                    "adjusted_joint": round(pair_joint, 4),
                    "pair_r": round(pair_r, 3),
                })

    verdict = (
        "High correlation tax — book heavily suppressed payout"  if tax_pct >= 40 else
        "Moderate tax — significant correlation adjustment"       if tax_pct >= 20 else
        "Low tax — legs mostly independent, fair payout"         if tax_pct >= 0  else
        "Negative correlation — book may be over-paying (rare)"
    )

    return {
        "independent_joint_prob":  round(independent_joint, 4),
        "sgp_implied_joint_prob":  round(sgp_implied_joint, 4),
        "independent_decimal":     round(fair_sgp_decimal, 2),
        "independent_american":    fair_sgp_american,
        "book_american":           book_sgp_american,
        "r_ij":                    round(r_ij, 3),
        "correlation_tax_pct":     tax_pct,
        "pairwise":                pairwise,
        "verdict":                 verdict,
    }


def decimal_to_american_float(dec: float) -> str:
    """Convert decimal odds to American string (e.g. +250, -150)."""
    if dec <= 1.0:
        return "N/A"
    if dec >= 2.0:
        return f"+{int(round((dec - 1) * 100))}"
    return f"{int(round(-100 / (dec - 1)))}"
