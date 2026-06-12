"""
Tier definitions — feature flags per subscription level.
Check features with: tiers.can(tier, "parlays")

Internal keys ("standard", "premium") are stored in Supabase profiles and
Stripe metadata — do NOT rename them. Display names live in "label".
Existing subscribers keep their current Stripe price (grandfathered);
new price points require new Price IDs in the Stripe dashboard, set via
STRIPE_STANDARD_PRICE_ID / STRIPE_PREMIUM_PRICE_ID / STRIPE_SYNDICATE_PRICE_ID.
"""

TIERS = {
    "free": {
        "label": "Free",
        "price_monthly": 0,
        "price_annual": 0,
        "price_id": None,
        "sports": ["MLB"],
        "parlays": False,
        "game_lines": False,
        "tracker": False,
        "ai_analysis": False,
        "alerts": False,
        "clv": False,
        "slips": False,              # full daily slip distribution
        "export": False,             # CSV / raw-probability export
        "refresh_seconds": 600,     # 10 min delayed
        "max_props": 50,             # cap shown props
        "edge_model": "basic",
    },
    "standard": {
        "label": "Edge",
        "price_monthly": 19,
        "price_annual": 149,
        "price_id": "price_1TfpdV24pu2fgt6EW58z5afY",
        "sports": ["MLB", "NBA", "WNBA", "NHL", "NFL", "NCAAF"],
        "parlays": True,
        "game_lines": True,
        "tracker": False,
        "ai_analysis": False,
        "alerts": False,
        "clv": False,
        "slips": True,
        "export": False,
        "refresh_seconds": 300,     # 5 min live
        "max_props": None,           # unlimited
        "edge_model": "shin",
    },
    "premium": {
        "label": "Sharp",
        "price_monthly": 49,
        "price_annual": 399,
        "price_id": "price_1Tfped24pu2fgt6EheFe6XlM",
        "sports": ["MLB", "NBA", "WNBA", "NHL", "NFL", "NCAAF"],
        "parlays": True,
        "game_lines": True,
        "tracker": True,
        "ai_analysis": True,
        "alerts": True,
        "clv": True,
        "slips": True,
        "export": False,
        "refresh_seconds": 60,      # near real-time
        "max_props": None,
        "edge_model": "shin",
    },
    "syndicate": {
        "label": "Syndicate",
        "price_monthly": 99,
        "price_annual": 799,
        "price_id": None,           # set STRIPE_SYNDICATE_PRICE_ID to enable
        "sports": ["MLB", "NBA", "WNBA", "NHL", "NFL", "NCAAF"],
        "parlays": True,
        "game_lines": True,
        "tracker": True,
        "ai_analysis": True,
        "alerts": True,
        "clv": True,
        "slips": True,
        "export": True,
        "refresh_seconds": 60,
        "max_props": None,
        "edge_model": "shin",
    },
}

TIER_ORDER = ["free", "standard", "premium", "syndicate"]


def can(tier: str, feature: str) -> bool:
    """Return True if this tier has the given feature."""
    cfg = TIERS.get(tier, TIERS["free"])
    val = cfg.get(feature)
    if isinstance(val, bool):
        return val
    if isinstance(val, list):
        return bool(val)
    return val is not None


def allowed_sports(tier: str) -> list[str]:
    return TIERS.get(tier, TIERS["free"])["sports"]


def max_props(tier: str) -> int | None:
    return TIERS.get(tier, TIERS["free"])["max_props"]


def refresh_seconds(tier: str) -> int:
    return TIERS.get(tier, TIERS["free"])["refresh_seconds"]


def upgrade_prompt(feature: str, required_tier: str = "standard") -> str:
    label = TIERS[required_tier]["label"]
    price = TIERS[required_tier]["price_monthly"]
    return f"🔒 **{feature}** is available on the **{label}** plan (${price}/mo). [Upgrade →](#upgrade)"


def tier_badge(tier: str) -> str:
    badges = {"free": "⚪ Free", "standard": "🔵 Edge",
              "premium": "🔥 Sharp", "syndicate": "💎 Syndicate"}
    return badges.get(tier, "⚪ Free")
