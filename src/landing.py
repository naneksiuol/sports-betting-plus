"""
Landing page — shown to unauthenticated visitors.
"""

import streamlit as st


def show_landing(on_login: callable, on_signup: callable):
    _inject_css()

    # ── Hero ──────────────────────────────────────────────────────────────────
    import os
    logo_path = os.path.join(os.path.dirname(__file__), "..", "static", "logo.png")
    if os.path.exists(logo_path):
        c1, c2, c3 = st.columns([2, 1, 2])
        with c2:
            st.image(logo_path, use_container_width=True)
    else:
        st.markdown('<div style="text-align:center;font-size:4rem">🎯</div>', unsafe_allow_html=True)

    st.markdown("""
    <div class="hero">
        <div class="hero-badge">⚡ LIVE ODDS · REAL EDGE · AI POWERED</div>
        <h1 class="hero-title">Sports Betting<br><span class="hero-accent">Plus Bot</span></h1>
        <p class="hero-sub">
            Real-time value bets on FanDuel &amp; DraftKings. AI-powered parlay builder,
            sharp line analysis, and bet tracker — MLB, NBA, NHL, NFL and more.
        </p>
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 1, 1])
    with col1:
        if st.button("🚀 Get Started Free", use_container_width=True, type="primary"):
            st.session_state["auth_mode"] = "signup"
            st.rerun()
    with col2:
        if st.button("🔑 Log In", use_container_width=True):
            st.session_state["auth_mode"] = "login"
            st.rerun()
    with col3:
        st.markdown("")  # spacer

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Stats bar ─────────────────────────────────────────────────────────────
    st.markdown("""
    <div class="stats-bar">
        <div class="stat"><span class="stat-num">6+</span><span class="stat-label">Sports</span></div>
        <div class="stat"><span class="stat-num">1000+</span><span class="stat-label">Daily Props</span></div>
        <div class="stat"><span class="stat-num">FD / DK</span><span class="stat-label">Focused</span></div>
        <div class="stat"><span class="stat-num">Real</span><span class="stat-label">Edge Model</span></div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Features ──────────────────────────────────────────────────────────────
    st.markdown("### What You Get")
    f1, f2, f3 = st.columns(3)
    with f1:
        st.markdown("""
        <div class="feature-card">
            <div class="feat-icon">📊</div>
            <h4>Sharp Edge Detection</h4>
            <p>Multi-book Shin de-vig finds where FanDuel and DraftKings are off the true market price.</p>
        </div>
        """, unsafe_allow_html=True)
    with f2:
        st.markdown("""
        <div class="feature-card">
            <div class="feat-icon">🎰</div>
            <h4>AI Parlay Builder</h4>
            <p>EV-scored multi-game and same-game parlays with correlation penalties and market diversity.</p>
        </div>
        """, unsafe_allow_html=True)
    with f3:
        st.markdown("""
        <div class="feature-card">
            <div class="feat-icon">📈</div>
            <h4>Bet Tracker</h4>
            <p>Log every bet, auto-grade MLB results, track your ROI and win rate over time.</p>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Pricing ───────────────────────────────────────────────────────────────
    st.markdown("### <div style='text-align:center'>Plans & Pricing</div>", unsafe_allow_html=True)
    p1, p2, p3 = st.columns(3)

    with p1:
        st.markdown("""
        <div class="price-card">
            <div class="plan-name">Free</div>
            <div class="plan-price">$0<span>/mo</span></div>
            <ul class="plan-features">
                <li>✅ MLB props only</li>
                <li>✅ Value bet finder</li>
                <li>✅ Up to 50 props</li>
                <li>❌ Parlays</li>
                <li>❌ Game lines</li>
                <li>❌ Bet tracker</li>
                <li>❌ AI analysis</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
        if st.button("Start Free", key="cta_free", use_container_width=True):
            st.session_state["auth_mode"] = "signup"
            st.rerun()

    with p2:
        st.markdown("""
        <div class="price-card featured">
            <div class="plan-badge">MOST POPULAR</div>
            <div class="plan-name">Standard</div>
            <div class="plan-price">$9<span>/mo</span></div>
            <ul class="plan-features">
                <li>✅ All 6 sports</li>
                <li>✅ Unlimited props</li>
                <li>✅ Parlay builder</li>
                <li>✅ Game lines</li>
                <li>✅ 5-min refresh</li>
                <li>❌ Bet tracker</li>
                <li>❌ AI analysis</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
        if st.button("Get Standard →", key="cta_standard", use_container_width=True, type="primary"):
            st.session_state["auth_mode"] = "signup"
            st.session_state["pending_tier"] = "standard"
            st.rerun()

    with p3:
        st.markdown("""
        <div class="price-card">
            <div class="plan-name">Premium</div>
            <div class="plan-price">$29<span>/mo</span></div>
            <ul class="plan-features">
                <li>✅ Everything in Standard</li>
                <li>✅ Bet tracker + grader</li>
                <li>✅ AI analysis (Groq)</li>
                <li>✅ Alerts</li>
                <li>✅ Near real-time data</li>
                <li>✅ Priority support</li>
                <li>✅ Early features</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
        if st.button("Go Premium →", key="cta_premium", use_container_width=True):
            st.session_state["auth_mode"] = "signup"
            st.session_state["pending_tier"] = "premium"
            st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("""
    <p style='text-align:center; color:#888; font-size:0.85rem'>
        Cancel anytime · No contracts · Billed monthly via Stripe
    </p>
    """, unsafe_allow_html=True)


def _inject_css():
    st.markdown("""
    <style>
    .hero { text-align: center; padding: 3rem 1rem 2rem; }
    .hero-badge {
        display: inline-block;
        background: rgba(0,255,136,0.15);
        color: #00ff88;
        border: 1px solid #00ff88;
        border-radius: 20px;
        padding: 4px 16px;
        font-size: 0.75rem;
        letter-spacing: 0.1em;
        margin-bottom: 1rem;
    }
    .hero-title { font-size: 3rem; font-weight: 800; line-height: 1.1; margin: 0.5rem 0; }
    .hero-accent { color: #00d4ff; }
    .hero-sub { color: #aaa; font-size: 1.1rem; max-width: 600px; margin: 1rem auto; }

    .stats-bar {
        display: flex; justify-content: center; gap: 3rem;
        padding: 1.5rem; background: rgba(255,255,255,0.04);
        border-radius: 12px; border: 1px solid rgba(255,255,255,0.08);
    }
    .stat { text-align: center; }
    .stat-num { display: block; font-size: 1.8rem; font-weight: 700; color: #00d4ff; }
    .stat-label { font-size: 0.8rem; color: #888; }

    .feature-card {
        background: rgba(255,255,255,0.04);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 12px;
        padding: 1.5rem;
        text-align: center;
        height: 200px;
    }
    .feat-icon { font-size: 2rem; margin-bottom: 0.5rem; }
    .feature-card h4 { margin: 0.5rem 0; color: #fff; }
    .feature-card p { color: #aaa; font-size: 0.9rem; }

    .price-card {
        background: rgba(255,255,255,0.04);
        border: 1px solid rgba(255,255,255,0.1);
        border-radius: 16px;
        padding: 1.5rem;
        position: relative;
        margin-bottom: 1rem;
    }
    .price-card.featured {
        border-color: #00d4ff;
        background: rgba(0,212,255,0.06);
    }
    .plan-badge {
        position: absolute; top: -12px; left: 50%; transform: translateX(-50%);
        background: #00d4ff; color: #000; font-size: 0.65rem;
        font-weight: 700; padding: 3px 12px; border-radius: 20px;
        letter-spacing: 0.08em;
    }
    .plan-name { font-size: 1.2rem; font-weight: 700; margin-bottom: 0.5rem; }
    .plan-price { font-size: 2.5rem; font-weight: 800; color: #00ff88; }
    .plan-price span { font-size: 1rem; color: #888; }
    .plan-features { list-style: none; padding: 0; margin: 1rem 0; }
    .plan-features li { padding: 0.3rem 0; font-size: 0.9rem; color: #ccc; }
    </style>
    """, unsafe_allow_html=True)
