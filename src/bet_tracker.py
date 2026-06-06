import json
import uuid
from pathlib import Path
from datetime import datetime

BETS_FILE = Path(__file__).parent.parent / "data" / "bets.json"


def load_bets() -> list[dict]:
    if not BETS_FILE.exists():
        return []
    try:
        return json.loads(BETS_FILE.read_text())
    except Exception:
        return []


def save_bets(bets: list[dict]):
    BETS_FILE.write_text(json.dumps(bets, indent=2))


def _american_to_dec(odds: float) -> float:
    if odds > 0:
        return (odds / 100) + 1
    return (100 / abs(odds)) + 1


def _compute_clv(placed_odds: float, reference_odds: float) -> float:
    """
    CLV = (1/bet_decimal) - (1/closing_decimal) expressed in percentage points.
    Positive = you got better odds than the sharp/closing line = proven long-term value.
    Uses the same formula as edge_model.closing_line_value for consistency.
    """
    try:
        from edge_model import closing_line_value
        return closing_line_value(placed_odds, reference_odds)
    except Exception:
        # Fallback if edge_model not available
        def imp(o):
            return 1 / _american_to_dec(o)
        return round((imp(reference_odds) - imp(placed_odds)) * 100, 2)


def add_bet(sport: str, player: str, prop: str, line: float, odds: int,
            stake: float, book: str = "", notes: str = "",
            sharp_odds: int = None, fair_est: float = None,
            is_parlay: bool = False) -> dict:
    """
    Log a bet. Automatically computes opening CLV if sharp_odds provided.
    sharp_odds = Pinnacle/Consensus line at bet placement time.
    fair_est   = Shin de-vigged fair probability at bet time.
    """
    opening_clv = None
    if sharp_odds and sharp_odds != 0:
        opening_clv = _compute_clv(odds, sharp_odds)

    bet = {
        "id": str(uuid.uuid4())[:8],
        "date": datetime.now().strftime("%Y-%m-%d"),
        "time": datetime.now().strftime("%H:%M"),
        "sport": sport,
        "player": player,
        "prop": prop,
        "line": line,
        "odds": odds,
        "stake": stake,
        "book": book,
        "result": "pending",
        "profit": None,
        # Sharp line stored at bet time
        "sharp_odds": sharp_odds,
        "fair_est": fair_est,
        "opening_clv": opening_clv,   # CLV vs sharp line at placement
        # Closing line (filled by auto-grader or manually)
        "closing_odds": None,
        "clv": None,                  # CLV vs true closing line (filled later)
        "notes": notes,
        "is_parlay": is_parlay,
    }
    bets = load_bets()
    bets.append(bet)
    save_bets(bets)
    return bet


def update_result(bet_id: str, result: str, closing_odds: int = None):
    """result: win | loss | push | pending"""
    bets = load_bets()
    for bet in bets:
        if bet["id"] == bet_id:
            bet["result"] = result
            odds = bet["odds"]
            stake = bet["stake"]

            if result == "win":
                bet["profit"] = round(
                    stake * (100 / abs(odds)) if odds < 0 else stake * (odds / 100), 2)
            elif result == "loss":
                bet["profit"] = -round(stake, 2)
            elif result == "push":
                bet["profit"] = 0.0
            else:
                bet["profit"] = None

            # Update CLV with true closing line if provided
            if closing_odds and closing_odds != 0:
                bet["closing_odds"] = closing_odds
                bet["clv"] = _compute_clv(odds, closing_odds)
            elif bet.get("sharp_odds") and not bet.get("clv"):
                # Fall back to opening sharp line as CLV proxy
                bet["clv"] = bet.get("opening_clv")

            break
    save_bets(bets)


def delete_bet(bet_id: str):
    bets = [b for b in load_bets() if b["id"] != bet_id]
    save_bets(bets)


def get_clv_avg(n_recent: int = 30) -> float | None:
    """
    Return average CLV over the most recent n_recent settled bets.
    Used to wire real CLV history into dynamic Kelly sizing.
    Returns None if insufficient data (<5 bets with CLV).
    """
    bets = load_bets()
    settled = [b for b in bets if b["result"] in ("win", "loss", "push")]
    # Use best available CLV — true closing first, then opening as proxy
    clv_vals = []
    for b in reversed(settled):  # most recent first
        clv = b.get("clv") or b.get("opening_clv")
        if clv is not None:
            clv_vals.append(float(clv))
        if len(clv_vals) >= n_recent:
            break
    if len(clv_vals) < 5:
        return None
    return round(sum(clv_vals) / len(clv_vals), 3)


def get_stats() -> dict:
    bets = load_bets()
    settled = [b for b in bets if b["result"] in ("win", "loss", "push")]
    wins = [b for b in settled if b["result"] == "win"]
    losses = [b for b in settled if b["result"] == "loss"]
    pending = [b for b in bets if b["result"] == "pending"]

    total_staked = sum(b["stake"] for b in settled)
    total_profit = sum(b["profit"] for b in settled if b["profit"] is not None)
    roi = (total_profit / total_staked * 100) if total_staked > 0 else 0
    win_rate = (len(wins) / len(settled) * 100) if settled else 0

    # CLV — prefer closing CLV, fall back to opening CLV
    clv_bets = [b for b in settled
                if b.get("clv") is not None or b.get("opening_clv") is not None]
    clv_values = [b.get("clv") or b.get("opening_clv") for b in clv_bets]
    avg_clv = sum(clv_values) / len(clv_values) if clv_values else None

    # Opening CLV for pending bets (early signal)
    pending_with_clv = [b for b in pending if b.get("opening_clv") is not None]
    avg_opening_clv = (sum(b["opening_clv"] for b in pending_with_clv) /
                       len(pending_with_clv)) if pending_with_clv else None

    # By sport
    by_sport = {}
    for b in settled:
        s = b["sport"]
        if s not in by_sport:
            by_sport[s] = {"wins": 0, "losses": 0, "profit": 0}
        if b["result"] == "win":
            by_sport[s]["wins"] += 1
        elif b["result"] == "loss":
            by_sport[s]["losses"] += 1
        by_sport[s]["profit"] += b["profit"] or 0

    return {
        "total_bets": len(bets),
        "settled": len(settled),
        "wins": len(wins),
        "losses": len(losses),
        "pending": len(pending),
        "win_rate": round(win_rate, 1),
        "total_staked": round(total_staked, 2),
        "total_profit": round(total_profit, 2),
        "roi": round(roi, 2),
        "avg_clv": round(avg_clv, 2) if avg_clv is not None else None,
        "avg_opening_clv": round(avg_opening_clv, 2) if avg_opening_clv is not None else None,
        "by_sport": by_sport,
        "all_bets": bets,
        "settled_bets": settled,
    }
