"""
Auth UI — login, signup, and OAuth buttons rendered in Streamlit.
"""

import streamlit as st
import auth

# SVG icons for OAuth buttons
_GOOGLE_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48" width="20" height="20">'
    '<path fill="#EA4335" d="M24 9.5c3.14 0 5.95 1.08 8.17 2.85l6.09-6.09C34.46 3.07 29.5 1 24 1'
    ' 14.82 1 7.07 6.49 3.64 14.27l7.08 5.5C12.43 13.63 17.75 9.5 24 9.5z"/>'
    '<path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v8.51h12.94'
    'c-.58 2.96-2.26 5.48-4.78 7.18l7.33 5.69c4.29-3.97 6.49-9.82 6.49-16.83z"/>'
    '<path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59'
    'l-7.08-5.5C1.23 17.17 0 20.44 0 24c0 3.56 1.23 6.83 3.28 9.41l7.25-4.82z"/>'
    '<path fill="#34A853" d="M24 47c6.48 0 11.93-2.13 15.89-5.81l-7.33-5.69'
    'c-2.1 1.41-4.78 2.25-8.56 2.25-6.25 0-11.57-4.13-13.47-9.76l-7.25 4.82'
    'C7.07 41.51 14.82 47 24 47z"/>'
    '<path fill="none" d="M0 0h48v48H0z"/>'
    '</svg>'
)

_APPLE_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 814 1000" width="17" height="20">'
    '<path fill="#fff" d="M788.1 340.9c-5.8 4.5-108.2 62.2-108.2 190.5 0 148.4 130.3 200.9 '
    '134.2 202.2-.6 3.2-20.7 71.9-68.7 141.9-42.8 61.6-87.5 123.1-155.5 123.1s-85.5-39.5-164-39.5'
    'c-76 0-103.7 40.8-165.9 40.8s-105-57.8-155.5-127.4C46 405.8 15.7 250.6 15.7 202.8'
    'c0-86.1 56.4-131.5 110.7-131.5 42.2 0 75.9 28.3 101.7 28.3 24.4 0 62.6-30.2 111-30.2'
    'c28.2 0 125.7 2.6 186.9 106.3zm-248-169c-18.7-23.2-39.5-60.5-39.5-97.8 0-5.2.6-10.5 1.3-14.4'
    ' 36.4 1.9 78.3 26.6 103.1 55.5 20.5 24.4 39.5 61.6 39.5 98.9 0 5.8-.6 11.6-1.3 16.5'
    '-3.2.6-6.5.6-9.7.6-32.9 0-71.2-23.2-93.4-59.3z"/>'
    '</svg>'
)


def show_auth_page():
    """Show login or signup form depending on session state."""
    mode = st.session_state.get("auth_mode", "login")

    # Handle OAuth callback if present
    auth.handle_oauth_callback()

    _inject_css()

    # Responsive wrapper — CSS makes this full-width on mobile
    st.markdown("<div class='auth-outer'>", unsafe_allow_html=True)
    col = st.columns([1, 2, 1])[1]
    with col:
        st.markdown("<div class='auth-card'>", unsafe_allow_html=True)

        if mode == "login":
            _show_login()
        elif mode == "forgot_password":
            _show_forgot_password()
        else:
            _show_signup()

        st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)


def _show_login():
    if st.button("← Back", key="back_login"):
        st.session_state.pop("auth_mode", None)
        st.rerun()

    st.markdown("### 🔑 Log In")

    # OAuth buttons
    _oauth_buttons(suffix="login")
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

    if st.button("Forgot password?", key="forgot_pw"):
        st.session_state["auth_mode"] = "forgot_password"
        st.rerun()

    st.markdown("<div class='guest-link'>", unsafe_allow_html=True)
    if st.button("Skip for now — browse free props →", key="guest_login"):
        st.session_state["auth_mode"] = None
        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("Don't have an account? **Sign up free →**", use_container_width=True):
        st.session_state["auth_mode"] = "signup"
        st.rerun()


def _show_signup():
    if st.button("← Back", key="back_signup"):
        st.session_state.pop("auth_mode", None)
        st.rerun()

    st.markdown("### 🚀 Create Account")

    _oauth_buttons(suffix="signup")
    st.markdown("<div class='divider'><span>or</span></div>", unsafe_allow_html=True)

    with st.form("signup_form"):
        name = st.text_input("Full Name", placeholder="John Smith")
        email = st.text_input("Email", placeholder="you@example.com")
        password = st.text_input("Password", type="password",
                                 placeholder="Min 8 characters",
                                 help="At least 8 characters")
        confirm = st.text_input("Confirm Password", type="password", placeholder="••••••••")
        age_ok = st.checkbox("I am 21 years of age or older", key="signup_age_attest")
        submitted = st.form_submit_button("Create Free Account", use_container_width=True, type="primary")
        if submitted:
            if not age_ok:
                st.error("You must be 21 or older to use this service.")
            elif not all([name, email, password, confirm]):
                st.error("Please fill in all fields.")
            elif len(password) < 8:
                st.error("Password must be at least 8 characters.")
            elif password != confirm:
                st.error("Passwords don't match.")
            else:
                with st.spinner("Creating account..."):
                    ok, err = auth.signup(email, password, name)
                if ok:
                    # Auto-login immediately after signup
                    with st.spinner("Logging you in..."):
                        login_ok, login_err = auth.login(email, password)
                    if login_ok:
                        st.session_state.pop("auth_mode", None)
                        # If user came from a paid tier CTA, redirect to Stripe checkout
                        pending_tier = st.session_state.pop("pending_tier", None)
                        if pending_tier and pending_tier != "free":
                            import stripe_payments
                            user = auth.get_user()
                            if user:
                                url = stripe_payments.create_checkout_session(
                                    user["id"], user["email"], pending_tier
                                )
                                if url:
                                    import streamlit.components.v1 as _c
                                    _c.html(f'<script>window.top.location.href = "{url}";</script>', height=0)
                                    return
                        st.rerun()
                    else:
                        st.success("✅ Account created! Please check your email then log in.")
                        st.session_state["auth_mode"] = "login"
                        st.rerun()
                else:
                    st.error(err)

    st.markdown("<div class='guest-link'>", unsafe_allow_html=True)
    if st.button("Skip for now — browse free props →", key="guest_signup"):
        st.session_state["auth_mode"] = None
        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("Already have an account? **Log in →**", use_container_width=True):
        st.session_state["auth_mode"] = "login"
        st.rerun()


def _oauth_buttons(suffix: str = ""):
    """Render branded Google and Apple OAuth buttons."""
    c1, c2 = st.columns(2)

    with c1:
        google_key = f"oauth_google_{suffix}"
        st.markdown(
            f'<div class="oauth-wrap" id="wrap_{google_key}">'
            f'  {_GOOGLE_SVG}'
            f'  <span>Continue with Google</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
        if st.button("Continue with Google", key=google_key,
                     use_container_width=True, type="secondary"):
            try:
                url = auth.get_google_oauth_url()
                st.session_state["_oauth_redirect"] = url
                st.rerun()
            except Exception as e:
                st.error(f"Google login unavailable: {e}")

    with c2:
        apple_key = f"oauth_apple_{suffix}"
        st.markdown(
            f'<div class="oauth-wrap apple-wrap" id="wrap_{apple_key}">'
            f'  {_APPLE_SVG}'
            f'  <span>Continue with Apple</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
        if st.button("Continue with Apple", key=apple_key,
                     use_container_width=True, type="secondary"):
            try:
                url = auth.get_apple_oauth_url()
                st.session_state["_oauth_redirect"] = url
                st.rerun()
            except Exception as e:
                st.error(f"Apple login unavailable: {e}")

    # Execute redirect after rerun (outside button block so it fires reliably)
    redirect_url = st.session_state.pop("_oauth_redirect", None)
    if redirect_url:
        import streamlit.components.v1 as _components
        _components.html(
            f'<script>window.top.location.href = "{redirect_url}";</script>',
            height=0,
        )


def _inject_css():
    st.markdown("""
    <style>
    /* ── Responsive auth card ── */
    .auth-outer { width: 100%; }
    .auth-card {
        background: rgba(255,255,255,0.04);
        border: 1px solid rgba(255,255,255,0.1);
        border-radius: 16px;
        padding: 2rem;
        margin-top: 2rem;
    }
    @media (max-width: 600px) {
        /* Override Streamlit column layout on small screens */
        .auth-outer ~ div [data-testid="column"]:first-child,
        .auth-outer ~ div [data-testid="column"]:last-child {
            display: none !important;
        }
        .auth-card {
            width: 95% !important;
            margin-left: auto;
            margin-right: auto;
            padding: 1.25rem;
        }
    }

    /* ── OR divider ── */
    .divider {
        display: flex; align-items: center; gap: 1rem;
        margin: 1rem 0; color: #666; font-size: 0.85rem;
    }
    .divider::before, .divider::after {
        content: ''; flex: 1; height: 1px; background: rgba(255,255,255,0.1);
    }

    /* ── Guest link ── */
    .guest-link {
        text-align: center;
        margin-top: 0.75rem;
    }
    .guest-link button {
        background: none !important;
        border: none !important;
        color: #888 !important;
        font-size: 0.8rem !important;
        text-decoration: underline;
        cursor: pointer;
        padding: 0 !important;
        box-shadow: none !important;
    }
    .guest-link button:hover { color: #bbb !important; }

    /* ── OAuth label rows (icon + text shown above the real st.button) ── */
    .oauth-wrap {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 8px;
        background: #fff;
        color: #1f1f1f;
        border: 1px solid #dadce0;
        border-radius: 8px 8px 0 0;
        padding: 8px 12px 6px;
        font-size: 0.88rem;
        font-weight: 500;
        pointer-events: none;
        margin-bottom: -1px;
        box-sizing: border-box;
    }
    .apple-wrap {
        background: #111;
        color: #fff;
        border-color: #333;
    }
    /* Stitch the real Streamlit button flush below the label row */
    .oauth-wrap + div button,
    .oauth-wrap + div [data-testid="stBaseButton-secondary"] {
        border-radius: 0 0 8px 8px !important;
        border-top: none !important;
        margin-top: 0 !important;
        font-size: 0 !important;        /* hide duplicate text */
        padding-top: 0 !important;
        padding-bottom: 0 !important;
        height: 4px !important;         /* thin invisible click strip */
        opacity: 0.01 !important;
        min-height: unset !important;
    }
    </style>
    """, unsafe_allow_html=True)


def _show_forgot_password():
    if st.button("← Back", key="back_forgot"):
        st.session_state["auth_mode"] = "login"
        st.rerun()

    st.markdown("### 🔐 Reset Password")
    st.markdown("Enter your email and we'll send you a password reset link.")

    with st.form("forgot_pw_form"):
        email = st.text_input("Email", placeholder="you@example.com")
        submitted = st.form_submit_button("Send Reset Link", use_container_width=True, type="primary")
        if submitted:
            if not email:
                st.error("Please enter your email address.")
            else:
                try:
                    client = auth.get_client()
                    client.auth.reset_password_email(
                        email,
                        options={"redirect_to": __import__("os").environ.get("OAUTH_REDIRECT_URL", "http://localhost:8501")},
                    )
                    st.success("✅ Reset link sent! Check your inbox.")
                except Exception as e:
                    st.error(f"Could not send reset email: {e}")


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
            import streamlit.components.v1 as _c
            _c.html(f'<script>window.top.location.href = "{url}";</script>', height=0)


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

        # ── Subscription status indicator ──
        profile = st.session_state.get("profile", {})
        profile_tier = profile.get("tier", tier)
        if profile_tier == "past_due":
            st.warning("⚠️ Payment failed — update billing to keep access")
        elif profile_tier in ("standard", "premium", "syndicate"):
            st.markdown("✅ **Active**")

        # ── Manage Billing link ──
        _stripe_key = __import__("os").environ.get("STRIPE_SECRET_KEY", "")
        if _stripe_key and profile_tier in ("standard", "premium", "syndicate", "past_due"):
            try:
                import stripe as _stripe
                _stripe.api_key = _stripe_key
                _portal = _stripe.billing_portal.Session.create(
                    customer=profile.get("stripe_customer_id", ""),
                    return_url=__import__("os").environ.get("APP_URL", "http://localhost:8501"),
                )
                st.markdown(
                    f"[🔗 Manage Billing]({_portal.url})",
                    unsafe_allow_html=False,
                )
            except Exception:
                st.markdown(
                    "[🔗 Manage Billing](mailto:support@sportsbettingplus.com)",
                    unsafe_allow_html=False,
                )
        elif profile_tier in ("standard", "premium", "syndicate", "past_due"):
            st.markdown(
                "[🔗 Manage Billing](mailto:support@sportsbettingplus.com)",
                unsafe_allow_html=False,
            )

        if user.get("is_admin"):
            if st.button("🛠️ Admin Panel", use_container_width=True, key="sidebar_admin"):
                st.session_state["show_admin"] = not st.session_state.get("show_admin", False)
                st.rerun()
        _ladder = {"free": "standard", "standard": "premium", "premium": "syndicate"}
        next_tier = _ladder.get(tier)
        import stripe_payments as _sp
        # Hide the Syndicate upsell until its Stripe price is configured
        if next_tier == "syndicate" and not _sp.PRICE_IDS.get("syndicate"):
            next_tier = None
        if next_tier:
            cfg = t.TIERS[next_tier]
            if st.button(f"⬆️ Upgrade to {cfg['label']}", use_container_width=True, key="sidebar_upgrade"):
                import stripe_payments
                url = stripe_payments.create_checkout_session(user["id"], user["email"], next_tier)
                if url:
                    import streamlit.components.v1 as _c
                    _c.html(f'<script>window.top.location.href = "{url}";</script>', height=0)
        if st.button("Log Out", use_container_width=True, key="sidebar_logout"):
            auth.logout()
            st.rerun()
