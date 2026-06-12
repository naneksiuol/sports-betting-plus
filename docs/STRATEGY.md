# Strategy: From "Sports Betting Plus" to a Props-Intelligence Brand

*Five-agent think tank synthesis — June 2026. Agents: Market, Brand, Monetization, Product, Compliance. All findings grounded in this codebase.*

---

## The One-Paragraph Plan

Reposition as **PropLens** — an AI props-intelligence product that "shows its work": calibrated model probabilities for player props with a public, auditable track record (CLV + ROI + Brier score). This occupies an empty trust-based middle between Outlier/Props.cash (descriptive stats, no model) and OddsJam/Unabated ($100–300/mo pro tools). The feature set is ~80% built; the work is repricing, surfacing the calibrator, fixing claims language, and hardening the data pipeline.

**Positioning statement:** *"The props intelligence app that shows its work — calibrated AI probabilities for player props, with a public track record instead of guru picks."*

---

## 1. Market (viable, with conditions)

**Target segments (ranked by fit):**
1. **Sharp-curious recreational props bettors** — bets 3-7x/week, $10-50 stakes, lives on FD/DK/PrizePicks. WTP $10-30/mo. The edge board + parlay builder + Discord slips already match their workflow.
2. **Semi-pro grinders** who care about CLV and calibration. Smaller pool, highest retention and word-of-mouth. WTP $50-100/mo *if* calibration receipts are published.
3. **Pick'em players** (PrizePicks/Underdog states) — big TAM, needs pick'em-specific lines later.

**Competitive gap:** Nobody in the $10-30 band offers calibrated probabilities + closed-loop accountability. Outlier shows the past; OddsJam assumes you're sharp. CLV-as-receipts is the differentiator.

**Top demand risks:**
1. Trust deficit — "AI betting" reads scam-adjacent. Only cure: genuinely transparent public record (a bad public month is churn — the models must hold up).
2. Platform dependence — books limit winners, app stores and ad networks restrict gambling-adjacent products.
3. Free-alternative compression (Linemate, Pikkit, sportsbook-native stats) + structural off-season churn. The NFL/NCAAF promise must be real by September.

---

## 2. Brand: PropLens

**Winner: PropLens** (runner-up PropSignal — keep "The Signal" as the daily-slip product name: *"The Signal by PropLens"*).

Scoring of all candidates (memorability / trust / domain / TM-safety / searchability): PropLens 4/5/4/5/5. EdgePilot and BetWise Pro eliminated — "Bet-" prefix is a trademark minefield (BetMGM, BetRivers) and triggers ad restrictions.

- **Tagline:** *See the edge before you take it.*
- **Story:** Sportsbooks price thousands of props a day; most bettors see odds, not probabilities. PropLens runs calibrated models against FanDuel and DraftKings lines and shows you — transparently, with a public track record — where the market is wrong and by how much. We don't sell picks; we sharpen your view.
- **Voice rules:** Quantified, never breathless (no 🚀, no "locks"). Honest about variance (talk EV and long-run CLV; acknowledge losing days). Decision support, not tipster ("the model sees value here," never "bet this").
- **Trust signals to ship:** public immutable CLV record; weekly calibration plot + Brier score on a /transparency page; timestamped pre-game slips (Discord posts as proof); methodology page.
- **Visual:** deepen dark theme to #0E1117/#1A1F2B; replace neon green #00ff88 with signal teal **#2DD4BF**; edge gold #F5B83D for +EV; tabular monospace for all numbers (a trust signal in itself). Logo: two overlapping arcs whose intersection forms a teal "edge" sliver.

---

## 3. Monetization

Current `tiers.py` (free/$9/$29) is underpriced with too wide a gap. Restructure:

| Tier | Price (mo/yr) | Features (mapped to existing flags) |
|---|---|---|
| Free | $0 | MLB only, 10-min delay, 50-prop cap, basic edge model |
| **Edge** | $19 / $149 | All sports, parlay builder, game lines, Shin de-vig, 5-min refresh |
| **Sharp** | $49 / $399 | + bet tracker, AI analysis, alerts, 60s refresh, CLV dashboard |
| **Syndicate** | $99 / $799 | + raw probabilities/CSV export, early-line alerts, private Discord |

Needs gating (currently free): CLV tracking → Sharp+; full daily slips → Edge+ (free gets 1 teaser/day); export → Syndicate. Add `clv`, `slips`, `export` flags to TIERS — trivial with the existing `can()` helper. Grandfather existing subs.

**Revenue sequencing (90 days):**
- Days 0-30: reprice + gate + annual plans (pure config; lifts ARPU immediately)
- Days 31-60: affiliate layer — register in 2-3 states first; deep links in bet tracker ("Log this bet at X") and free board; expect CPA $150-350/FTD, ~$15-25k/yr at 5k users
- Days 61-90: B2B white-label Discord slips for betting communities — $299/mo (their branding, 2 sports) or $599/mo (all sports + CLV reporting); 5 communities ≈ $1.5-3k MRR at near-zero marginal cost; close before NFL season

**Unit economics at 5k free signups:** 4% convert → 200 paid → blended ARPU ~$30 → **~$6.1k subscription MRR**; + affiliate ~$1.5k/mo + B2B ~$900 ≈ **$8.5k MRR (~$100k run-rate)** by day 90.

---

## 4. Product: MVP Gaps & Roadmap

| MVP feature | Status | Where |
|---|---|---|
| Top props by sport | ✅ Exists | `props_dashboard.py` render_sport_tab |
| Confidence score | ✅ Exists | `edge_confidence_score()` 0-100 |
| Probability band | ❌ Missing on board | `calibration.py` has it — only shown in buried ML tab |
| Injury/news alerts | ⚠️ Partial | In-app flags only; no push for watched players |
| Combo builder | ✅ Exists | `parlay_builder.py` (correlation-aware SGPs) |
| Watchlist/favorites | ❌ Missing | No per-user saved props anywhere |
| Mobile-first | ⚠️ Partial | One media query on a 4,000-line desktop app |
| "Why this prop" | ⚠️ Partial | Groq bulk analysis exists; no one-tap per-prop card |

**Top 5 changes (ranked, effort):**
1. **Pipeline reliability (M)** — remove the IP allowlist on the Odds API key (restrict by quota instead) so the deployed app fetches directly; keep the GitHub cache as fallback; add freshness badge + Discord ping when the scrape job misses its window. One PC reboot currently = stale product.
2. **Calibrated probability band on every prop card (S)** — the calibrator already trains itself; this is a display change and it's the credibility moat.
3. **Watchlist + injury push (M)** — star button → Supabase → existing Discord/Telegram send when a watched player flips Out/Doubtful.
4. **One-tap "Why this prop" card (S)** — single-prop Groq call over existing signals (edge, streak, steam, injury), cached per prop per day.
5. **Mobile "Top 5 today" card-stack view (M)** — default landing for mobile instead of dense tables.

**Retention loops:** daily graded digest ("Yesterday: 3-1. Today's board is live"); watchlist event pings (steam/injury/streak); weekly calibration report email ("our 60%+ picks hit 61% this month").

**Don't build yet:** more sports before the pipeline is solid; live in-game odds (5-min cache can't support it); native mobile app.

---

## 5. Compliance: Pre-Launch Checklist

The app never places or handles wagers (verified) — it's an analytics/decision-support tool, which keeps it out of operator licensing. Two caveats: affiliate revenue triggers state-by-state vendor registration (NJ/PA/CO etc.), and tout framing + revshare is the highest-FTC-scrutiny combo.

**Urgent (do today):**
- 🔴 **Rotate the Gmail app password** — hardcoded in `send_daily_bets.py:15`, `send_daily_bets.py.bak`, and `auto_grade.py:26` (committed to git history; scrub with filter-repo after rotating). Move to env var, delete the `.bak`.

**Before relaunch:**
- Change "18+ only" to **21+** in `landing.py` footer; add age attestation checkbox to signup (`auth_ui.py` — currently no age check at all)
- Add **1-800-GAMBLER** helpline to: landing footer, email footer (`send_daily_bets.py`), Discord footer (`discord_bot.py`), Telegram footer (`telegram_bot.py`)
- Rewrite outcome-promise copy in `landing.py`:
  - "Beat the Book. Every Day." → "Find market inefficiencies with model-driven analysis."
  - "watch your ROI compound" → "Track your results and understand your performance."
  - "Everything You Need to Win" → "Everything you need to analyze the props market."
  - "beat the book" CTA → "make more informed decisions"
- Record displays (W-L, ROI) are fine **only** as complete, untrimmed, methodology-disclosed records — pair every record post with "past performance does not guarantee future results"
- Add affiliate disclosure adjacent to any future sportsbook link + a disclosure page
- Add "void where prohibited / not legal in all states" to footers
- CAN-SPAM for email: unsubscribe link + physical address (currently absent)
- Add a privacy policy before charging (none in repo)

**Platform risk:** Stripe treats betting-advice subscriptions as high-risk and reviews landing pages — the claims rewrite above directly protects the Stripe account. Keep web distribution (Streamlit); don't casually wrap as a mobile app (app stores require licensing evidence for real-money-adjacent products).

---

## Sequenced Action List

| # | Action | Owner effort | Source |
|---|---|---|---|
| 1 | Rotate Gmail app password, env-var it, delete .bak | 30 min | Compliance |
| 2 | Remove Odds API key IP allowlist (or get static IP) | 15 min | Product |
| 3 | Rewrite 4 landing-page claims; 21+ + helpline footers | 1-2 h | Compliance |
| 4 | Reprice tiers ($19/$49/$99) + gate CLV/slips/export | 1 day | Monetization |
| 5 | Surface calibrated probability band on prop cards | 1 day | Product |
| 6 | Public /transparency page (CLV record, Brier, calibration plot) | 2-3 days | Market+Brand |
| 7 | Rebrand to PropLens (name, palette, copy) | 2-3 days | Brand |
| 8 | Watchlist + injury push | 3-5 days | Product |
| 9 | State affiliate registrations, then affiliate links | weeks (legal) | Monetization |
| 10 | B2B white-label slip pilot (3 Discord communities) | by Sept | Monetization |
