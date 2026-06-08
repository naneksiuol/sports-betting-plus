"""
Auth UI — login, signup, and OAuth buttons rendered in Streamlit.
"""

import streamlit as st
import auth


def show_auth_page():
    """Show login or signup form depending on session state."""
    mode = st.session_state.get("auth_mode", "login")

    # Handle OAuth callback if present
    auth.handle_oauth_callback()

    _inject_css()

    col = st.columns([1, 2, 1])[1]
    with col:
        st.markdown("<div class='auth-card'>", unsafe_allow_html=True)

        if mode == "login":
            _show_login()
        else:
            _show_signup()

        st.markdown("</div>", unsafe_allow_html=True)


def _show_login():
    st.markdown("### 🔑 Log In")

    # OAuth buttons
    _oauth_buttons()
    st.markdown("<div class='divider'><span>or</span></div>", unsafe_allow_html=True)

    with st.form("login_form"):
        email = st.text_input("Email", placeholder="you@example.com")
        password = st.text_input("Password", type="password", placeholder="••••••••")
        submitted = st.form_submit_button("Log In", use_container_width=True, type="primary")
        if submitted:
            if not email or not password:
                st.error("Please fill in all fields.")
            else:
                with st.spinner("Logging in..."):
                    ok, err = auth.login(email, password)
                if ok:
                    st.success("Welcome back!")
                    st.rerun()
                else:
                    st.error(err)

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("Don't have an account? **Sign up free →**", use_container_width=True):
        st.session_state["auth_mode"] = "signup"
        st.rerun()

    if st.button("← Back to home", use_container_width=True):
        st.session_state.pop("auth_mode", None)
        st.rerun()


def _show_signup():
    st.markdown("### 🚀 Create Account")

    _oauth_buttons()
    st.markdown("<div class='divider'><span>or</span></div>", unsafe_allow_html=True)

    with st.form("signup_form"):
        name = st.text_input("Full Name", placeholder="John Smith")
        email = st.text_input("Email", placeholder="you@example.com")
        password = st.text_input("Password", type="password",
                                 placeholder="Min 8 characters",
                                 help="At least 8 characters")
        confirm = st.text_input("Confirm Password", type="password", placeholder="••••••••")
        submitted = st.form_submit_button("Create Free Account", use_container_width=True, type="primary")
        if submitted:
            if not all([name, email, password, confirm]):
                st.error("Please fill in all fields.")
            elif len(password) < 8:
                st.error("Password must be at least 8 characters.")
            elif password != confirm:
                st.error("Passwords don't match.")
            else:
                with st.spinner("Creating account..."):
                    ok, err = auth.signup(email, password, name)
                if ok:
                    st.success("✅ Account created! You can now log in.")
                    st.session_state["auth_mode"] = "login"
                    st.rerun()
                else:
                    st.error(err)

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("Already have an account? **Log in →**", use_container_width=True):
        st.session_state["auth_mode"] = "login"
        st.rerun()

    if st.button("← Back to home", use_container_width=True):
        st.session_state.pop("auth_mode", None)
        st.rerun()


def _oauth_buttons():
    c1, c2 = st.columns(2)
    with c1:
        if st.button("🔵  Continue with Google", use_container_width=True):
            try:
                url = auth.get_google_oauth_url()
                st.markdown(f'<meta http-equiv="refresh" content="0; url={url}">', unsafe_allow_html=True)
            except Exception as e:
                st.error(f"Google login error: {e}")
    with c2:
        if st.button("🍎  Continue with Apple", use_container_width=True):
            try:
                url = auth.get_apple_oauth_url()
                st.markdown(f'<meta http-equiv="refresh" content="0; url={url}">', unsafe_allow_html=True)
            except Exception as e:
                st.error(f"Apple login error: {e}")


def _inject_css():
    st.markdown("""
    <style>
    .auth-card {
        background: rgba(255,255,255,0.04);
        border: 1px solid rgba(255,255,255,0.1);
        border-radius: 16px;
        padding: 2rem;
        margin-top: 2rem;
    }
    .divider {
        display: flex; align-items: center; gap: 1rem;
        margin: 1rem 0; color: #666; font-size: 0.85rem;
    }
    .divider::before, .divider::after {
        content: ''; flex: 1; height: 1px; background: rgba(255,255,255,0.1);
    }
    </style>
    """, unsafe_allow_html=True)


def show_upgrade_modal(required_tier: str = "standard", key: str = ""):
    """Show an upgrade prompt when a gated feature is accessed."""
    from tiers import TIERS
    import stripe_payments

    cfg = TIERS[required_tier]
    st.markdown(f"""
    <div style='background: rgba(0,212,255,0.08); border: 1px solid #00d4ff;
                border-radius: 12px; padding: 1.5rem; text-align: center; margin: 1rem 0;'>
        <h3>🔒 {cfg['label']} Feature</h3>
        <p style='color: #aaa;'>Upgrade to <strong>{cfg['label']}</strong> (${cfg['price_monthly']}/mo) to unlock this.</p>
    </div>
    """, unsafe_allow_html=True)

    user = auth.get_user()
    btn_key = f"upgrade_{required_tier}_{key}" if key else f"upgrade_{required_tier}"
    if user and st.button(f"Upgrade to {cfg['label']} — ${cfg['price_monthly']}/mo",
                          type="primary", use_container_width=True, key=btn_key):
        url = stripe_payments.create_checkout_session(
            user["id"], user["email"], required_tier
        )
        if url:
            st.markdown(f'<meta http-equiv="refresh" content="0; url={url}">', unsafe_allow_html=True)


def show_user_menu():
    """Top-right user info + logout button."""
    import tiers as t
    user = auth.get_user()
    if not user:
        return
    tier = user.get("tier", "free")
    with st.sidebar:
        st.markdown("---")
        admin_badge = " 👑" if user.get("is_admin") else ""
        st.markdown(f"👤 **{user['name']}**{admin_badge}")
        st.markdown(f"{t.tier_badge(tier)}")
        if user.get("is_admin"):
            if st.button("🛠️ Admin Panel", use_container_width=True, key="sidebar_admin"):
                st.session_state["show_admin"] = not st.session_state.get("show_admin", False)
                st.rerun()
        if tier != "premium":
            next_tier = "standard" if tier == "free" else "premium"
            cfg = t.TIERS[next_tier]
            if st.button(f"⬆️ Upgrade to {cfg['label']}", use_container_width=True, key="sidebar_upgrade"):
                import stripe_payments
                url = stripe_payments.create_checkout_session(user["id"], user["email"], next_tier)
                if url:
                    st.markdown(f'<meta http-equiv="refresh" content="0; url={url}">', unsafe_allow_html=True)
        if st.button("Log Out", use_container_width=True, key="sidebar_logout"):
            auth.logout()
            st.rerun()
