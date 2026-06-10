"""
Landing page — shown to unauthenticated visitors.
Premium dark SaaS UI.
"""

import os
import streamlit as st


def show_landing(on_login: callable, on_signup: callable):
    _inject_css()

    # ── Banner (full-width, above the fold) ───────────────────────────────────
    _static = os.path.join(os.path.dirname(__file__), "..", "static")
    banner_path = os.path.join(_static, "banner.png")
    logo_path   = os.path.join(_static, "logo.png")
    img_path    = banner_path if os.path.exists(banner_path) else (logo_path if os.path.exists(logo_path) else None)
    if img_path:
        st.markdown('<div class="banner-wrap">', unsafe_allow_html=True)
        st.image(img_path, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown(f"""
    <div class="hero">
        <div class="hero-badge">⚡ LIVE ODDS · REAL EDGE · AI POWERED</div>
        <h1 class="hero-title">Beat the Book.<br><span class="hero-gradient">Every Day.</span></h1>
        <p class="hero-sub">
            Real-time value bets on FanDuel &amp; DraftKings. AI-powered parlay builder,
            sharp line analysis, and bet tracker — MLB, NBA, NHL, NFL and more.
        </p>
    </div>
    """, unsafe_allow_html=True)

    # CTA buttons — centred pair, responsive
    st.markdown('<div class="cta-row">', unsafe_allow_html=True)
    cta1, cta2, cta3, cta4, cta5 = st.columns([1, 1.2, 0.3, 1.2, 1])
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

    # ── Social proof bar ──────────────────────────────────────────────────────
    st.markdown("""
    <div class="stats-bar">
        <div class="stat">
            <span class="stat-num">1,000+</span>
            <span class="stat-label">Props Daily</span>
        </div>
        <div class="stat">
            <span class="stat-num">6</span>
            <span class="stat-label">Sports Covered</span>
        </div>
        <div class="stat">
            <span class="stat-num">5min</span>
            <span class="stat-label">Data Refresh</span>
        </div>
        <div class="stat">
            <span class="stat-num">FD + DK</span>
            <span class="stat-label">Books</span>
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
            <h3>Live Odds Scrape</h3>
            <p>We pull FanDuel &amp; DraftKings props every 5 minutes — no stale lines.</p>
        </div>
        <div class="step-card">
            <div class="step-num">2</div>
            <div class="step-icon">🧠</div>
            <h3>Edge Model Fires</h3>
            <p>Our multi-book de-vig model flags mispriced props with a positive expected value edge.</p>
        </div>
        <div class="step-card">
            <div class="step-num">3</div>
            <div class="step-icon">💰</div>
            <h3>You Bet With Edge</h3>
            <p>Place bets with confidence, track your results, and watch your ROI compound.</p>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<div style='margin-top:3.5rem'></div>", unsafe_allow_html=True)

    # ── Features grid ─────────────────────────────────────────────────────────
    st.markdown('<h2 class="section-title">Everything You Need to Win</h2>', unsafe_allow_html=True)
    st.markdown("""
    <div class="features-grid">
        <div class="feature-card">
            <div class="feat-icon">🔥</div>
            <h4>Steam Move Alerts</h4>
            <p>Sharp money detector flags lines moving against the public — follow the books that know.</p>
        </div>
        <div class="feature-card">
            <div class="feat-icon">📊</div>
            <h4>Multi-Book Edge Model</h4>
            <p>Consensus de-vig across 8+ books pinpoints where FD and DK are priced off the true market.</p>
        </div>
        <div class="feature-card">
            <div class="feat-icon">🎰</div>
            <h4>AI Parlay Builder</h4>
            <p>EV-scored, correlation-adjusted parlays — single-game and multi-game with market diversity.</p>
        </div>
        <div class="feature-card">
            <div class="feat-icon">📈</div>
            <h4>Bet Tracker + Auto-Grader</h4>
            <p>Log every bet, auto-grade results nightly, and see your true ROI and win rate over time.</p>
        </div>
        <div class="feature-card">
            <div class="feat-icon">🔔</div>
            <h4>Hot Streak Alerts</h4>
            <p>4/5 and 5/5 hit rate badges surface the props running hot before the public catches on.</p>
        </div>
        <div class="feature-card">
            <div class="feat-icon">🤖</div>
            <h4>ML Confidence Scores</h4>
            <p>LightGBM models trained per sport output a calibrated confidence score on every prop.</p>
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
                <li><span class="chk">✓</span> Value bet finder</li>
                <li><span class="chk">✓</span> Up to 50 props/day</li>
                <li><span class="ex">✗</span> Parlay builder</li>
                <li><span class="ex">✗</span> Game lines</li>
                <li><span class="ex">✗</span> Bet tracker</li>
                <li><span class="ex">✗</span> AI analysis</li>
            </ul>
        </div>
        <div class="price-card featured">
            <div class="plan-badge">MOST POPULAR</div>
            <div class="plan-name">Standard</div>
            <div class="plan-price">$9<span>/mo</span></div>
            <p class="plan-desc">Full access. Real edge. Every sport.</p>
            <ul class="plan-features">
                <li><span class="chk">✓</span> All 6 sports</li>
                <li><span class="chk">✓</span> Unlimited props</li>
                <li><span class="chk">✓</span> Parlay builder</li>
                <li><span class="chk">✓</span> Game lines</li>
                <li><span class="chk">✓</span> 5-min refresh</li>
                <li><span class="chk">✓</span> Line shopping</li>
                <li><span class="chk">✓</span> Hot streak alerts</li>
            </ul>
        </div>
        <div class="price-card">
            <div class="plan-name">Premium</div>
            <div class="plan-price">$29<span>/mo</span></div>
            <p class="plan-desc">For serious bettors who track every dollar.</p>
            <ul class="plan-features">
                <li><span class="chk">✓</span> Everything in Standard</li>
                <li><span class="chk">✓</span> Bet tracker + grader</li>
                <li><span class="chk">✓</span> AI analysis (fast inference)</li>
                <li><span class="chk">✓</span> Discord alerts</li>
                <li><span class="chk">✓</span> Near real-time data</li>
                <li><span class="chk">✓</span> Priority support</li>
                <li><span class="chk">✓</span> Early feature access</li>
            </ul>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Pricing CTA — stacks on mobile via CSS
    st.markdown('<div class="pricing-cta-row">', unsafe_allow_html=True)
    pc1, pc2, pc3 = st.columns(3)
    with pc1:
        if st.button("Start Free", key="cta_free", use_container_width=True):
            st.session_state["auth_mode"] = "signup"
            st.rerun()
    with pc2:
        if st.button("Get Standard →", key="cta_standard", use_container_width=True, type="primary"):
            st.session_state["auth_mode"] = "signup"
            st.session_state["pending_tier"] = "standard"
            st.rerun()
    with pc3:
        if st.button("Go Premium →", key="cta_premium", use_container_width=True):
            st.session_state["auth_mode"] = "signup"
            st.session_state["pending_tier"] = "premium"
            st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div style='margin-top:4rem'></div>", unsafe_allow_html=True)

    # ── Auth CTA section ──────────────────────────────────────────────────────
    st.markdown("""
    <div class="auth-cta-section">
        <h2 class="auth-cta-title">Ready to get an edge?</h2>
        <p class="auth-cta-sub">Join sharp bettors using real data to beat the book.</p>
        <div class="oauth-buttons">
            <div class="oauth-btn google-btn">
                <svg width="18" height="18" viewBox="0 0 18 18" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M17.64 9.2045C17.64 8.5663 17.5827 7.9527 17.4764 7.3636H9V10.845H13.8436C13.635 11.9700 13.0009 12.9231 12.0477 13.5613V15.8195H14.9564C16.6582 14.2527 17.64 11.9454 17.64 9.2045Z" fill="#4285F4"/>
                    <path d="M9 18C11.43 18 13.4673 17.1941 14.9564 15.8195L12.0477 13.5613C11.2418 14.1013 10.2109 14.4204 9 14.4204C6.65591 14.4204 4.67182 12.8372 3.96409 10.71H0.957275V13.0418C2.43818 15.9831 5.48182 18 9 18Z" fill="#34A853"/>
                    <path d="M3.96409 10.71C3.78409 10.17 3.68182 9.5931 3.68182 9C3.68182 8.4069 3.78409 7.83 3.96409 7.29V4.9582H0.957275C0.347727 6.1731 0 7.5477 0 9C0 10.4523 0.347727 11.8268 0.957275 13.0418L3.96409 10.71Z" fill="#FBBC05"/>
                    <path d="M9 3.5795C10.3214 3.5795 11.5077 4.0336 12.4405 4.9255L15.0218 2.344C13.4632 0.8918 11.4259 0 9 0C5.48182 0 2.43818 2.0168 0.957275 4.9582L3.96409 7.29C4.67182 5.1627 6.65591 3.5795 9 3.5795Z" fill="#EA4335"/>
                </svg>
                Continue with Google
            </div>
            <div class="oauth-btn apple-btn">
                <svg width="16" height="18" viewBox="0 0 16 18" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M13.2 9.5C13.19 7.81 14.01 6.5 15.67 5.54C14.74 4.21 13.33 3.47 11.48 3.33C9.73 3.19 7.82 4.37 7.13 4.37C6.4 4.37 4.72 3.38 3.37 3.38C0.58 3.42 -0.01 5.59 0 7.78C0.01 10.89 2.12 15.04 4.27 15C5.55 14.97 6.46 14.1 8.01 14.1C9.52 14.1 10.37 15 11.77 15C13.94 14.97 15.87 11.24 15.86 8.13C14.13 7.48 13.21 8.67 13.2 9.5ZM10.37 2.22C11.76 0.6 11.63 -0.86 11.59 -1.39C10.38 -1.32 8.97 -0.52 8.16 0.39C7.28 1.38 6.76 2.61 6.87 3.81C8.18 3.9 9.39 3.19 10.37 2.22Z" fill="white"/>
                </svg>
                Continue with Apple
            </div>
        </div>
        <p class="or-divider">— or —</p>
    </div>
    """, unsafe_allow_html=True)

    # Real Streamlit buttons below the HTML display layer
    st.markdown('<div class="auth-real-btns">', unsafe_allow_html=True)
    ab1, ab2, ab3 = st.columns([1, 2, 1])
    with ab2:
        if st.button("Sign Up with Email →", key="auth_cta_email", use_container_width=True, type="primary"):
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
        <p class="footer-copy">© 2026 Sports Betting Plus. All rights reserved.</p>
        <p class="footer-copy" style="font-size:0.72rem;margin-top:0.25rem;">For entertainment purposes only. Please bet responsibly. 18+ only.
        &nbsp;·&nbsp; <a href="#" style="color:#666;">Terms of Service</a>
        &nbsp;·&nbsp; <a href="#" style="color:#666;">Privacy Policy</a></p>
    </div>
    """, unsafe_allow_html=True)


def _inject_css():
    st.markdown("""
    <style>
    /* ── Base ── */
    [data-testid="stAppViewContainer"] {
        background: #0a0a0f !important;
    }
    [data-testid="stHeader"] { background: #0a0a0f !important; }
    section[data-testid="stSidebar"] { display: none; }
    .block-container {
        max-width: 1100px;
        padding: 0 0 3rem;
    }
    /* Re-add side padding for everything EXCEPT the banner */
    .hero, .stats-bar, .steps-row, .features-grid,
    .pricing-row, .auth-cta-section, .footer,
    .section-title, .cta-row, .pricing-cta-row {
        padding-left: 1.25rem;
        padding-right: 1.25rem;
        box-sizing: border-box;
    }
    @media (max-width: 640px) {
        .hero, .stats-bar, .steps-row, .features-grid,
        .pricing-row, .auth-cta-section, .footer,
        .section-title, .cta-row, .pricing-cta-row {
            padding-left: 0.75rem;
            padding-right: 0.75rem;
        }
    }

    /* ── Animated gradient text ── */
    @keyframes gradientShift {
        0%   { background-position: 0% 50%; }
        50%  { background-position: 100% 50%; }
        100% { background-position: 0% 50%; }
    }

    /* ── Banner ── */
    .banner-wrap {
        width: 100%;
        margin: -1rem 0 0.5rem;   /* pull flush to top, override Streamlit top padding */
        line-height: 0;
        overflow: hidden;
    }
    /* st.image renders inside [data-testid="stImage"] > img */
    .banner-wrap [data-testid="stImage"],
    .banner-wrap [data-testid="stImage"] img {
        width: 100% !important;
        max-height: 280px;
        object-fit: cover;
        object-position: center top;
        border-radius: 0 0 16px 16px;
        display: block;
    }
    .hero-logo {
        display: block;
        margin: 1.5rem auto 0.5rem;
        width: clamp(120px, 28vw, 220px);
        height: auto;
        object-fit: contain;
    }

    /* ── Hero ── */
    .hero {
        text-align: center;
        padding: 1.5rem 1rem 1.5rem;
    }
    .hero-badge {
        display: inline-block;
        background: rgba(139,92,246,0.15);
        color: #a78bfa;
        border: 1px solid rgba(139,92,246,0.4);
        border-radius: 20px;
        padding: 5px 18px;
        font-size: clamp(0.62rem, 1.5vw, 0.72rem);
        letter-spacing: 0.12em;
        font-weight: 600;
        margin-bottom: 1.2rem;
    }
    .hero-title {
        font-size: clamp(2rem, 7vw, 4rem);
        font-weight: 900;
        line-height: 1.1;
        margin: 0.4rem 0;
        color: #f1f1f5;
        letter-spacing: -0.02em;
    }
    .hero-gradient {
        background: linear-gradient(270deg, #a78bfa, #22d3ee, #a78bfa);
        background-size: 300% 300%;
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        animation: gradientShift 4s ease infinite;
    }
    .hero-sub {
        color: #94a3b8;
        font-size: clamp(0.9rem, 2.5vw, 1.1rem);
        max-width: 580px;
        margin: 1rem auto 1.5rem;
        line-height: 1.65;
    }

    /* ── CTA row ── */
    .cta-row { margin-bottom: 0.5rem; }

    /* ── Stats bar ── */
    .stats-bar {
        display: flex;
        justify-content: center;
        flex-wrap: wrap;
        gap: 0.5rem 2rem;
        padding: 1.5rem 1.5rem;
        background: #12121e;
        border-radius: 16px;
        border: 1px solid rgba(139,92,246,0.2);
        margin: 0 auto;
    }
    .stat { text-align: center; min-width: 80px; flex: 1 1 80px; }
    .stat-num {
        display: block;
        font-size: clamp(1.2rem, 3.5vw, 2rem);
        font-weight: 800;
        background: linear-gradient(135deg, #a78bfa, #22d3ee);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
    }
    .stat-label {
        font-size: clamp(0.65rem, 1.5vw, 0.78rem);
        color: #64748b;
        letter-spacing: 0.05em;
        text-transform: uppercase;
    }

    /* ── Section titles ── */
    .section-title {
        text-align: center;
        font-size: clamp(1.4rem, 4vw, 2.2rem);
        font-weight: 800;
        color: #f1f1f5;
        margin-bottom: 2rem;
        letter-spacing: -0.02em;
    }

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
        background: #12121e;
        border: 1px solid rgba(255,255,255,0.07);
        border-radius: 16px;
        padding: 2rem 1.25rem;
        text-align: center;
        position: relative;
        transition: border-color 0.2s, transform 0.2s;
    }
    .step-card:hover {
        border-color: rgba(139,92,246,0.45);
        transform: translateY(-3px);
    }
    .step-num {
        position: absolute;
        top: -14px;
        left: 50%;
        transform: translateX(-50%);
        background: linear-gradient(135deg, #7c3aed, #0891b2);
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
    .step-card h3 { font-size: 1.05rem; font-weight: 700; color: #f1f1f5; margin: 0.5rem 0 0.75rem; }
    .step-card p { font-size: 0.88rem; color: #94a3b8; line-height: 1.6; margin: 0; }

    /* ── Features grid ── */
    .features-grid {
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: 1.25rem;
    }
    @media (max-width: 768px) {
        .features-grid { grid-template-columns: repeat(2, 1fr); }
    }
    @media (max-width: 480px) {
        .features-grid { grid-template-columns: 1fr; }
    }
    .feature-card {
        background: #12121e;
        border: 1px solid rgba(255,255,255,0.07);
        border-radius: 14px;
        padding: 1.5rem 1.25rem;
        transition: border-color 0.2s, transform 0.2s;
    }
    .feature-card:hover {
        border-color: rgba(34,211,238,0.35);
        transform: translateY(-2px);
    }
    .feat-icon { font-size: 1.8rem; margin-bottom: 0.6rem; }
    .feature-card h4 { font-size: 0.97rem; font-weight: 700; color: #f1f1f5; margin: 0 0 0.5rem; }
    .feature-card p { font-size: 0.85rem; color: #94a3b8; line-height: 1.55; margin: 0; }

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
        background: #12121e;
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 18px;
        padding: 2rem 1.5rem 1.5rem;
        position: relative;
    }
    .price-card.featured {
        border: 2px solid #7c3aed;
        background: linear-gradient(145deg, #13101f, #12121e);
        box-shadow: 0 0 30px rgba(124,58,237,0.2);
    }
    .plan-badge {
        position: absolute;
        top: -13px;
        left: 50%;
        transform: translateX(-50%);
        background: linear-gradient(90deg, #7c3aed, #0891b2);
        color: #fff;
        font-size: 0.62rem;
        font-weight: 800;
        padding: 4px 14px;
        border-radius: 20px;
        letter-spacing: 0.1em;
        white-space: nowrap;
    }
    .plan-name { font-size: 1.1rem; font-weight: 700; color: #e2e8f0; margin-bottom: 0.5rem; }
    .plan-price { font-size: 2.8rem; font-weight: 900; color: #f1f1f5; line-height: 1; margin-bottom: 0.3rem; }
    .plan-price span { font-size: 1rem; color: #64748b; font-weight: 400; }
    .plan-desc { font-size: 0.82rem; color: #64748b; margin: 0 0 1rem; }
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
    .ex  { color: #475569; font-weight: 700; flex-shrink: 0; }

    /* Pricing CTA stacks to single column on mobile */
    .pricing-cta-row [data-testid="stHorizontalBlock"] {
        flex-wrap: wrap;
        gap: 0.5rem;
    }
    @media (max-width: 520px) {
        .pricing-cta-row [data-testid="stHorizontalBlock"] > div {
            min-width: 100% !important;
            flex: 1 1 100% !important;
        }
    }

    /* ── Auth CTA ── */
    .auth-cta-section {
        text-align: center;
        background: linear-gradient(145deg, #12121e, #0f0f1a);
        border: 1px solid rgba(139,92,246,0.2);
        border-radius: 20px;
        padding: 3rem 1.5rem 1.5rem;
    }
    .auth-cta-title {
        font-size: clamp(1.5rem, 5vw, 2.6rem);
        font-weight: 900;
        color: #f1f1f5;
        margin: 0 0 0.6rem;
        letter-spacing: -0.02em;
    }
    .auth-cta-sub { color: #94a3b8; font-size: 1rem; margin: 0 0 2rem; }
    .oauth-buttons {
        display: flex;
        justify-content: center;
        flex-wrap: wrap;
        gap: 1rem;
        margin-bottom: 1.25rem;
    }
    .oauth-btn {
        display: flex;
        align-items: center;
        gap: 0.6rem;
        padding: 0.7rem 1.4rem;
        border-radius: 10px;
        font-size: 0.9rem;
        font-weight: 600;
        cursor: pointer;
        min-width: 180px;
        max-width: 100%;
        justify-content: center;
    }
    .google-btn { background: #fff; color: #1a1a2e; border: none; }
    .apple-btn  { background: #1c1c1e; color: #f1f1f5; border: 1px solid rgba(255,255,255,0.15); }
    .or-divider { color: #475569; font-size: 0.85rem; margin: 0.25rem 0 1rem; }

    /* Hide the secondary (Google/Apple/LogIn/SignUp) buttons visually — they're
       functional fallbacks for the HTML-only OAuth display above */
    .auth-secondary-btns { margin-top: 0.5rem; opacity: 0.4; }
    .auth-secondary-btns button { font-size: 0.75rem !important; }

    /* ── Footer ── */
    .footer {
        text-align: center;
        padding: 2rem 1rem 1rem;
        border-top: 1px solid rgba(255,255,255,0.06);
    }
    .footer p { color: #64748b; font-size: 0.85rem; margin: 0.25rem 0; }
    .footer-copy { font-size: 0.75rem !important; color: #334155 !important; }

    /* ── Streamlit button overrides ── */
    div[data-testid="stButton"] > button {
        border-radius: 10px !important;
        font-weight: 600 !important;
        transition: opacity 0.15s !important;
    }
    div[data-testid="stButton"] > button:hover { opacity: 0.85 !important; }
    </style>
    """, unsafe_allow_html=True)
