"""
Landing page — shown to unauthenticated visitors.
Design matches the PropLens banner: dark bg, neon green accents,
ANALYZE · PREDICT · WIN theme.
"""

import os
import streamlit as st


def show_landing(on_login: callable, on_signup: callable):
    _inject_css()

    # ── Banner image (full-width, above the fold) ──────────────────────────────
    _static = os.path.join(os.path.dirname(__file__), "..", "static")
    banner_path = os.path.join(_static, "banner.png")
    if os.path.exists(banner_path):
        st.markdown('<div class="banner-wrap">', unsafe_allow_html=True)
        st.image(banner_path, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)
    else:
        # Inline hero replaces the image when banner.png isn't present
        st.markdown("""
<div class="hero-header">
  <div class="hero-logo-row">
    <div class="logo-icon">🎯</div>
    <div class="logo-text">
      <span class="logo-name">PROPLENS</span>
      <span class="logo-sub">PROPS INTELLIGENCE</span>
    </div>
  </div>
  <div class="ai-badge">⚡ AI POWERED</div>
</div>
""", unsafe_allow_html=True)

    # ── Hero copy ──────────────────────────────────────────────────────────────
    st.markdown("""
<div class="hero">
  <h1 class="hero-title">
    <span class="word-a">ANALYZE.</span>
    <span class="word-p"> PREDICT.</span>
    <span class="word-w"> WIN.</span>
  </h1>
  <p class="hero-sub">
    Calibrated AI probabilities for player props — with a public track record instead of guru picks.
    Find market inefficiencies on FanDuel &amp; DraftKings before the line moves.
  </p>
</div>
""", unsafe_allow_html=True)

    # CTA buttons
    st.markdown('<div class="cta-row">', unsafe_allow_html=True)
    _, cta2, _s, cta4, _ = st.columns([1, 1.2, 0.3, 1.2, 1])
    with cta2:
        if st.button("🚀 Start Free →", key="hero_signup", use_container_width=True, type="primary"):
            st.session_state["auth_mode"] = "signup"
            st.rerun()
    with cta4:
        if st.button("🔑 Log In", key="hero_login", use_container_width=True):
            st.session_state["auth_mode"] = "login"
            st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div style='margin-top:2rem'></div>", unsafe_allow_html=True)

    # ── Stats bar ─────────────────────────────────────────────────────────────
    st.markdown("""
<div class="stats-bar">
  <div class="stat"><span class="stat-num">1,000+</span><span class="stat-label">Props Daily</span></div>
  <div class="stat"><span class="stat-num">4</span><span class="stat-label">Sports Live</span></div>
  <div class="stat"><span class="stat-num">5 min</span><span class="stat-label">Data Refresh</span></div>
  <div class="stat"><span class="stat-num">FD + DK</span><span class="stat-label">Books</span></div>
  <div class="stat"><span class="stat-num">Public</span><span class="stat-label">Track Record</span></div>
</div>
""", unsafe_allow_html=True)

    st.markdown("<div style='margin-top:3.5rem'></div>", unsafe_allow_html=True)

    # ── Sport categories (matching banner layout) ─────────────────────────────
    st.markdown('<h2 class="section-title">Top Prop Categories</h2>', unsafe_allow_html=True)
    st.markdown("""
<div class="sports-grid">
  <div class="sport-card">
    <div class="sport-header">
      <span class="sport-emoji">⚾</span>
      <span class="sport-name">MLB</span>
    </div>
    <ul class="sport-props">
      <li>Hits</li><li>Home Runs</li><li>RBIs</li>
      <li>Total Bases</li><li>Strikeouts (Pitchers)</li>
      <li>Earned Runs (Pitchers)</li>
    </ul>
  </div>
  <div class="sport-card">
    <div class="sport-header">
      <span class="sport-emoji">🏀</span>
      <span class="sport-name">NBA</span>
    </div>
    <ul class="sport-props">
      <li>Points</li><li>Rebounds</li><li>Assists</li>
      <li>Threes Made</li><li>Steals</li><li>Blocks</li>
    </ul>
  </div>
  <div class="sport-card">
    <div class="sport-header">
      <span class="sport-emoji">🏀</span>
      <span class="sport-name">WNBA</span>
    </div>
    <ul class="sport-props">
      <li>Points</li><li>Rebounds</li><li>Assists</li>
      <li>Threes Made</li><li>Steals</li><li>Blocks</li>
    </ul>
  </div>
  <div class="sport-card">
    <div class="sport-header">
      <span class="sport-emoji">🏒</span>
      <span class="sport-name">NHL</span>
    </div>
    <ul class="sport-props">
      <li>Goals</li><li>Assists</li><li>Points</li>
      <li>Shots on Goal</li><li>Hits</li><li>Blocks</li>
    </ul>
  </div>
</div>
""", unsafe_allow_html=True)

    st.markdown("<div style='margin-top:3.5rem'></div>", unsafe_allow_html=True)

    # ── Four feature cards (matching banner) ──────────────────────────────────
    st.markdown('<h2 class="section-title">Everything You Need to Analyze the Props Market</h2>', unsafe_allow_html=True)
    st.markdown("""
<div class="features-grid">
  <div class="feature-card">
    <div class="feat-icon">📊</div>
    <h4>Top Player Props</h4>
    <p>Discover the highest-edge props from FanDuel &amp; DraftKings — de-vigged against 8+ books to find real market inefficiencies.</p>
  </div>
  <div class="feature-card">
    <div class="feat-icon">🎯</div>
    <h4>Smart Combos</h4>
    <p>Powerful correlation-aware parlay builder. Single-game SGPs and multi-game combos scored for EV so you only play combos that make sense.</p>
  </div>
  <div class="feature-card">
    <div class="feat-icon">🧠</div>
    <h4>AI Predictions</h4>
    <p>Data-driven projections from a calibrated LightGBM model. Win probability bands on every prop — not gut-feel, actual receipts.</p>
  </div>
  <div class="feature-card">
    <div class="feat-icon">✅</div>
    <h4>Bet Smarter</h4>
    <p>Make more informed decisions with confidence scores, CLV tracking, Kelly stake sizing, and a full injury + line-movement dashboard.</p>
  </div>
  <div class="feature-card">
    <div class="feat-icon">🔥</div>
    <h4>Steam Move Alerts</h4>
    <p>Sharp money detector flags lines moving against the public. Follow the books that know — before the line closes against you.</p>
  </div>
  <div class="feature-card">
    <div class="feat-icon">📈</div>
    <h4>Public Track Record</h4>
    <p>Complete W-L record, ROI, CLV, and Brier score on the <a href="?page=transparency" style="color:#4ade80;">Transparency</a> page — wins, losses, and all. No cherry-picking.</p>
  </div>
</div>
""", unsafe_allow_html=True)

    st.markdown("<div style='margin-top:3.5rem'></div>", unsafe_allow_html=True)

    # ── How it works ──────────────────────────────────────────────────────────
    st.markdown('<h2 class="section-title">How It Works</h2>', unsafe_allow_html=True)
    st.markdown("""
<div class="steps-row">
  <div class="step-card">
    <div class="step-num">1</div>
    <div class="step-icon">📡</div>
    <h3>Live Odds Pulled</h3>
    <p>FanDuel &amp; DraftKings props every 5 minutes — no stale lines, no manual updates.</p>
  </div>
  <div class="step-card">
    <div class="step-num">2</div>
    <div class="step-icon">🧠</div>
    <h3>Model Runs</h3>
    <p>Calibrated AI model flags mispriced props with edge, confidence score, and win probability band.</p>
  </div>
  <div class="step-card">
    <div class="step-num">3</div>
    <div class="step-icon">🎯</div>
    <h3>You Decide</h3>
    <p>All the data to make more informed decisions. We show you the analysis — you own the bet.</p>
  </div>
</div>
""", unsafe_allow_html=True)

    st.markdown("<div style='margin-top:3.5rem'></div>", unsafe_allow_html=True)

    # ── Pricing ───────────────────────────────────────────────────────────────
    st.markdown('<h2 class="section-title">Simple, Transparent Pricing</h2>', unsafe_allow_html=True)
    st.markdown("""
<div class="pricing-row">
  <div class="price-card">
    <div class="plan-name">Free</div>
    <div class="plan-price">$0<span>/mo</span></div>
    <p class="plan-desc">Dip your toes in. No card required.</p>
    <ul class="plan-features">
      <li><span class="chk">✓</span> MLB props only</li>
      <li><span class="chk">✓</span> Value bet finder (50 props/day)</li>
      <li><span class="chk">✓</span> Win probability bands</li>
      <li><span class="ex">✗</span> All sports</li>
      <li><span class="ex">✗</span> Parlay builder</li>
      <li><span class="ex">✗</span> Bet tracker</li>
      <li><span class="ex">✗</span> AI analysis</li>
    </ul>
  </div>
  <div class="price-card featured">
    <div class="plan-badge">MOST POPULAR</div>
    <div class="plan-name">Edge</div>
    <div class="plan-price">$19<span>/mo</span></div>
    <p class="plan-desc">All sports, real edge, every day.</p>
    <ul class="plan-features">
      <li><span class="chk">✓</span> MLB, NBA, WNBA, NHL, NFL, NCAAF</li>
      <li><span class="chk">✓</span> Unlimited props + parlay builder</li>
      <li><span class="chk">✓</span> Game lines (ML · Spread · Total)</li>
      <li><span class="chk">✓</span> Daily Discord slip</li>
      <li><span class="chk">✓</span> 5-min live refresh</li>
      <li><span class="chk">✓</span> Line shopping alerts</li>
      <li><span class="chk">✓</span> Hot streak alerts</li>
    </ul>
  </div>
  <div class="price-card">
    <div class="plan-name">Sharp</div>
    <div class="plan-price">$49<span>/mo</span></div>
    <p class="plan-desc">For serious bettors who track every dollar.</p>
    <ul class="plan-features">
      <li><span class="chk">✓</span> Everything in Edge</li>
      <li><span class="chk">✓</span> Bet tracker + nightly auto-grader</li>
      <li><span class="chk">✓</span> AI analysis per prop</li>
      <li><span class="chk">✓</span> CLV dashboard</li>
      <li><span class="chk">✓</span> Watchlist + injury push alerts</li>
      <li><span class="chk">✓</span> Near real-time data (60s)</li>
      <li><span class="chk">✓</span> Priority support</li>
    </ul>
  </div>
</div>
""", unsafe_allow_html=True)

    # Pricing CTAs
    st.markdown('<div class="pricing-cta-row">', unsafe_allow_html=True)
    pc1, pc2, pc3 = st.columns(3)
    with pc1:
        if st.button("Start Free", key="cta_free", use_container_width=True):
            st.session_state["auth_mode"] = "signup"
            st.rerun()
    with pc2:
        if st.button("Get Edge →", key="cta_standard", use_container_width=True, type="primary"):
            st.session_state["auth_mode"] = "signup"
            st.session_state["pending_tier"] = "standard"
            st.rerun()
    with pc3:
        if st.button("Go Sharp →", key="cta_premium", use_container_width=True):
            st.session_state["auth_mode"] = "signup"
            st.session_state["pending_tier"] = "premium"
            st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div style='margin-top:4rem'></div>", unsafe_allow_html=True)

    # ── Bottom CTA ────────────────────────────────────────────────────────────
    st.markdown("""
<div class="auth-cta-section">
  <div class="ai-pw-badge">AI POWERED. REAL EDGES. REAL RESULTS.</div>
  <h2 class="auth-cta-title">Ready to see the edge?</h2>
  <p class="auth-cta-sub">Join sharp bettors using calibrated model data to make more informed decisions.</p>
</div>
""", unsafe_allow_html=True)

    st.markdown('<div class="auth-real-btns">', unsafe_allow_html=True)
    _, ab2, _ = st.columns([1, 2, 1])
    with ab2:
        if st.button("Sign Up Free →", key="auth_cta_email", use_container_width=True, type="primary"):
            st.session_state["auth_mode"] = "signup"
            st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="auth-secondary-btns">', unsafe_allow_html=True)
    sb1, sb2 = st.columns(2)
    with sb1:
        if st.button("🔐 Log In", key="bottom_login", use_container_width=True):
            st.session_state["auth_mode"] = "login"
            st.rerun()
    with sb2:
        if st.button("🚀 Sign Up Free", key="bottom_signup", use_container_width=True, type="primary"):
            st.session_state["auth_mode"] = "signup"
            st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div style='margin-top:3rem'></div>", unsafe_allow_html=True)

    # ── Footer ────────────────────────────────────────────────────────────────
    st.markdown("""
<div class="footer">
  <p>Cancel anytime &nbsp;·&nbsp; No contracts &nbsp;·&nbsp; Billed monthly via Stripe</p>
  <p style="margin:0.5rem 0;"><a href="?page=transparency" style="color:#4ade80;font-size:0.85rem;">📊 Public Track Record &amp; Transparency</a></p>
  <p class="footer-copy">© 2026 PropLens. All rights reserved.</p>
  <p class="footer-copy">
    For informational and entertainment purposes only. Not betting advice — past performance does not
    guarantee future results. 21+ only. Not legal in all states; void where prohibited.<br>
    Gambling problem? Call or text <strong>1-800-GAMBLER</strong>.
    &nbsp;·&nbsp; <a href="#" style="color:#334155;">Terms</a>
    &nbsp;·&nbsp; <a href="#" style="color:#334155;">Privacy</a>
  </p>
</div>
""", unsafe_allow_html=True)


def _inject_css():
    st.markdown("""
<style>
/* ── Base ── */
[data-testid="stAppViewContainer"] { background: #060b07 !important; }
[data-testid="stHeader"] { background: #060b07 !important; }
section[data-testid="stSidebar"] { display: none; }
.block-container { max-width: 1100px; padding: 0 0 3rem; }

/* Side padding for content sections */
.hero, .hero-header, .stats-bar, .steps-row, .features-grid,
.pricing-row, .auth-cta-section, .footer, .sports-grid,
.section-title, .cta-row, .pricing-cta-row {
    padding-left: 1.25rem;
    padding-right: 1.25rem;
    box-sizing: border-box;
}
@media (max-width: 640px) {
    .hero, .hero-header, .stats-bar, .steps-row, .features-grid,
    .pricing-row, .auth-cta-section, .footer, .sports-grid,
    .section-title, .cta-row, .pricing-cta-row {
        padding-left: 0.75rem;
        padding-right: 0.75rem;
    }
}

/* ── Animations ── */
@keyframes gradientShift {
    0%   { background-position: 0% 50%; }
    50%  { background-position: 100% 50%; }
    100% { background-position: 0% 50%; }
}
@keyframes pulseGreen {
    0%, 100% { box-shadow: 0 0 0 0 rgba(74,222,128,0.4); }
    50%       { box-shadow: 0 0 0 8px rgba(74,222,128,0); }
}

/* ── Banner image ── */
.banner-wrap {
    width: 100%;
    margin: -1rem 0 0;
    line-height: 0;
    overflow: hidden;
}
.banner-wrap [data-testid="stImage"],
.banner-wrap [data-testid="stImage"] img {
    width: 100% !important;
    max-height: 340px;
    object-fit: cover;
    object-position: center top;
    border-radius: 0 0 16px 16px;
    display: block;
}

/* ── Inline hero (when no banner.png) ── */
.hero-header {
    display: flex;
    flex-direction: column;
    align-items: center;
    padding-top: 2.5rem;
    padding-bottom: 0.5rem;
    gap: 0.75rem;
}
.hero-logo-row {
    display: flex;
    align-items: center;
    gap: 0.75rem;
}
.logo-icon { font-size: 3rem; }
.logo-text {
    display: flex;
    flex-direction: column;
    line-height: 1.1;
}
.logo-name {
    font-size: clamp(2rem, 6vw, 3.5rem);
    font-weight: 900;
    letter-spacing: -0.03em;
    color: #fff;
    font-family: 'Space Grotesk', sans-serif;
}
.logo-name em { font-style: normal; color: #4ade80; }
.logo-sub {
    font-size: 0.75rem;
    letter-spacing: 0.25em;
    color: #4ade80;
    font-weight: 600;
    text-transform: uppercase;
}
.ai-badge {
    display: inline-block;
    background: #4ade80;
    color: #060b07;
    font-size: 0.72rem;
    font-weight: 900;
    letter-spacing: 0.15em;
    padding: 4px 16px;
    border-radius: 20px;
    text-transform: uppercase;
    animation: pulseGreen 2.5s ease infinite;
}

/* ── Hero copy ── */
.hero {
    text-align: center;
    padding: 1.8rem 1rem 1.5rem;
}
.hero-title {
    font-size: clamp(2.2rem, 8vw, 4.4rem);
    font-weight: 900;
    line-height: 1.05;
    margin: 0 0 1rem;
    letter-spacing: -0.02em;
}
.word-a { color: #fff; }
.word-p { color: #4ade80; }
.word-w {
    background: linear-gradient(90deg, #4ade80, #22d3ee);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}
.hero-sub {
    color: #94a3b8;
    font-size: clamp(0.9rem, 2.5vw, 1.1rem);
    max-width: 600px;
    margin: 0 auto 1.5rem;
    line-height: 1.65;
}

/* ── CTA row ── */
.cta-row { margin-bottom: 0.5rem; }

/* Green primary button override */
div[data-testid="stButton"] > button[kind="primary"] {
    background: linear-gradient(135deg, #16a34a, #15803d) !important;
    border: none !important;
    color: #fff !important;
    font-weight: 700 !important;
}
div[data-testid="stButton"] > button[kind="primary"]:hover {
    background: linear-gradient(135deg, #15803d, #166534) !important;
    opacity: 1 !important;
}

/* ── Stats bar ── */
.stats-bar {
    display: flex;
    justify-content: center;
    flex-wrap: wrap;
    gap: 0.5rem 2rem;
    padding: 1.5rem;
    background: #0c150d;
    border-radius: 16px;
    border: 1px solid rgba(74,222,128,0.15);
}
.stat { text-align: center; min-width: 80px; flex: 1 1 80px; }
.stat-num {
    display: block;
    font-size: clamp(1.2rem, 3.5vw, 2rem);
    font-weight: 800;
    background: linear-gradient(135deg, #4ade80, #22d3ee);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}
.stat-label {
    font-size: clamp(0.62rem, 1.5vw, 0.75rem);
    color: #4b5563;
    letter-spacing: 0.08em;
    text-transform: uppercase;
}

/* ── Section titles ── */
.section-title {
    text-align: center;
    font-size: clamp(1.4rem, 4vw, 2.1rem);
    font-weight: 800;
    color: #f1f5f9;
    margin-bottom: 1.75rem;
    letter-spacing: -0.02em;
}

/* ── Sport categories grid ── */
.sports-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 1rem;
}
@media (max-width: 768px) { .sports-grid { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 480px) { .sports-grid { grid-template-columns: 1fr; } }
.sport-card {
    background: #0c150d;
    border: 1px solid rgba(74,222,128,0.12);
    border-radius: 14px;
    padding: 1.25rem 1rem;
    transition: border-color 0.2s, transform 0.2s;
}
.sport-card:hover {
    border-color: rgba(74,222,128,0.4);
    transform: translateY(-2px);
}
.sport-header {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 0.75rem;
    border-bottom: 1px solid rgba(74,222,128,0.1);
    padding-bottom: 0.5rem;
}
.sport-emoji { font-size: 1.4rem; }
.sport-name {
    font-weight: 800;
    font-size: 1rem;
    color: #4ade80;
    letter-spacing: 0.05em;
}
.sport-props {
    list-style: none;
    padding: 0;
    margin: 0;
}
.sport-props li {
    font-size: 0.82rem;
    color: #94a3b8;
    padding: 0.2rem 0;
    display: flex;
    align-items: center;
    gap: 0.4rem;
}
.sport-props li::before {
    content: "·";
    color: #4ade80;
    font-weight: 700;
}

/* ── Features grid ── */
.features-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 1.25rem;
}
@media (max-width: 768px) { .features-grid { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 480px) { .features-grid { grid-template-columns: 1fr; } }
.feature-card {
    background: #0c150d;
    border: 1px solid rgba(74,222,128,0.1);
    border-radius: 14px;
    padding: 1.5rem 1.25rem;
    transition: border-color 0.2s, transform 0.2s;
}
.feature-card:hover {
    border-color: rgba(74,222,128,0.35);
    transform: translateY(-2px);
}
.feat-icon { font-size: 1.8rem; margin-bottom: 0.6rem; }
.feature-card h4 {
    font-size: 0.97rem;
    font-weight: 700;
    color: #f1f5f9;
    margin: 0 0 0.5rem;
}
.feature-card p { font-size: 0.85rem; color: #94a3b8; line-height: 1.55; margin: 0; }

/* ── How it works ── */
.steps-row {
    display: flex;
    gap: 1.25rem;
    flex-wrap: wrap;
    justify-content: center;
}
.step-card {
    flex: 1 1 220px;
    max-width: 320px;
    background: #0c150d;
    border: 1px solid rgba(74,222,128,0.1);
    border-radius: 16px;
    padding: 2rem 1.25rem;
    text-align: center;
    position: relative;
    transition: border-color 0.2s, transform 0.2s;
}
.step-card:hover {
    border-color: rgba(74,222,128,0.4);
    transform: translateY(-3px);
}
.step-num {
    position: absolute;
    top: -14px;
    left: 50%;
    transform: translateX(-50%);
    background: linear-gradient(135deg, #16a34a, #15803d);
    color: #fff;
    font-size: 0.75rem;
    font-weight: 800;
    width: 28px;
    height: 28px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
}
.step-icon { font-size: 2.2rem; margin-bottom: 0.75rem; }
.step-card h3 { font-size: 1.05rem; font-weight: 700; color: #f1f5f9; margin: 0.5rem 0 0.75rem; }
.step-card p { font-size: 0.88rem; color: #94a3b8; line-height: 1.6; margin: 0; }

/* ── Pricing ── */
.pricing-row {
    display: flex;
    gap: 1.25rem;
    flex-wrap: wrap;
    justify-content: center;
    margin-bottom: 1.25rem;
}
.price-card {
    flex: 1 1 220px;
    max-width: 320px;
    background: #0c150d;
    border: 1px solid rgba(74,222,128,0.1);
    border-radius: 18px;
    padding: 2rem 1.5rem 1.5rem;
    position: relative;
}
.price-card.featured {
    border: 2px solid #4ade80;
    background: linear-gradient(145deg, #0d1f0f, #0c150d);
    box-shadow: 0 0 30px rgba(74,222,128,0.15);
}
.plan-badge {
    position: absolute;
    top: -13px;
    left: 50%;
    transform: translateX(-50%);
    background: linear-gradient(90deg, #16a34a, #0891b2);
    color: #fff;
    font-size: 0.62rem;
    font-weight: 800;
    padding: 4px 14px;
    border-radius: 20px;
    letter-spacing: 0.1em;
    white-space: nowrap;
}
.plan-name { font-size: 1.1rem; font-weight: 700; color: #f1f5f9; margin-bottom: 0.5rem; }
.plan-price { font-size: 2.8rem; font-weight: 900; color: #f1f5f9; line-height: 1; margin-bottom: 0.3rem; }
.plan-price span { font-size: 1rem; color: #4b5563; font-weight: 400; }
.plan-desc { font-size: 0.82rem; color: #4b5563; margin: 0 0 1rem; }
.plan-features { list-style: none; padding: 0; margin: 0; }
.plan-features li {
    padding: 0.35rem 0;
    font-size: 0.88rem;
    color: #94a3b8;
    display: flex;
    align-items: center;
    gap: 0.5rem;
}
.chk { color: #4ade80; font-weight: 700; flex-shrink: 0; }
.ex  { color: #1f2937; font-weight: 700; flex-shrink: 0; }

/* Pricing CTA stacks on mobile */
.pricing-cta-row [data-testid="stHorizontalBlock"] { flex-wrap: wrap; gap: 0.5rem; }
@media (max-width: 520px) {
    .pricing-cta-row [data-testid="stHorizontalBlock"] > div {
        min-width: 100% !important;
        flex: 1 1 100% !important;
    }
}

/* ── Bottom CTA section ── */
.auth-cta-section {
    text-align: center;
    background: #0c150d;
    border: 1px solid rgba(74,222,128,0.15);
    border-radius: 20px;
    padding: 3rem 1.5rem 2rem;
}
.ai-pw-badge {
    display: inline-block;
    background: transparent;
    color: #4ade80;
    border: 1px solid rgba(74,222,128,0.4);
    border-radius: 20px;
    padding: 5px 18px;
    font-size: 0.72rem;
    letter-spacing: 0.12em;
    font-weight: 700;
    margin-bottom: 1.2rem;
}
.auth-cta-title {
    font-size: clamp(1.5rem, 5vw, 2.6rem);
    font-weight: 900;
    color: #f1f5f9;
    margin: 0 0 0.6rem;
    letter-spacing: -0.02em;
}
.auth-cta-sub { color: #94a3b8; font-size: 1rem; margin: 0 0 2rem; }

.auth-real-btns { margin-top: -0.5rem; }
.auth-secondary-btns { margin-top: 0.5rem; opacity: 0.35; }
.auth-secondary-btns button { font-size: 0.75rem !important; }

/* ── Footer ── */
.footer {
    text-align: center;
    padding: 2rem 1rem 1rem;
    border-top: 1px solid rgba(255,255,255,0.04);
}
.footer p { color: #4b5563; font-size: 0.85rem; margin: 0.25rem 0; }
.footer-copy { font-size: 0.72rem !important; color: #1f2937 !important; }

/* ── Streamlit button overrides ── */
div[data-testid="stButton"] > button {
    border-radius: 10px !important;
    font-weight: 600 !important;
    transition: opacity 0.15s !important;
    border-color: rgba(74,222,128,0.3) !important;
}
</style>
""", unsafe_allow_html=True)
