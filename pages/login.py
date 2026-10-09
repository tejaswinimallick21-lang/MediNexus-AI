"""
Secure Login Portal for MediNexus AI.

Email + password against the seeded user store, via the same auth service the FastAPI backend
uses (backend/app/services/auth.py). Self sign-up and the password-less role switcher were
removed in the React migration; accounts come from backend/seed_users.json.
"""

import streamlit as st

from backend.app.core.users import SeedFileError
from backend.app.services.auth import authenticate
from config.roles import ROLE_PERMISSIONS


# Legacy Streamlit pages are keyed by persona; map the three platform roles onto them until Streamlit is retired.
ROLE_TO_LEGACY_PERSONA = {"admin": "Data Engineer", "hcp": "Doctor", "analyst": "Hospital Administrator"}


def start_session(user) -> None:
    """Populate the session keys the Streamlit pages read."""
    persona = ROLE_TO_LEGACY_PERSONA[user.role]
    profile = {
        "username": user.email,
        "email": user.email,
        "name": user.name,
        "role": persona,
        "auth_role": user.role,
        "department": user.department,
    }
    st.session_state["authenticated"] = True
    st.session_state["user"] = profile
    st.session_state["username"] = user.email
    st.session_state["name"] = user.name
    st.session_state["role"] = persona
    st.session_state["auth_role"] = user.role
    st.session_state["department"] = user.department
    st.session_state["current_page"] = ROLE_PERMISSIONS.get(persona, {}).get("default_page", "welcome")
    if persona == "Data Engineer":
        st.session_state["pipeline_completed"] = False


def render_login_page():
    """Render the email + password sign-in form."""
    st.markdown("""
        <div style="text-align: center; margin-bottom: 22px;">
            <div style="display: inline-block; background: #0F172A; color: #2DD4BF; padding: 4px 14px; border-radius: 20px; font-size: 0.78rem; font-weight: 700; letter-spacing: 0.5px; margin-bottom: 6px;">
                ROLE-BASED ACCESS CONTROL PORTAL
            </div>
            <h2 style="color: #0F172A; font-weight: 800; margin-bottom: 4px; font-size: 1.85rem;">MediNexus Access Portal</h2>
            <p style="color: #64748B; font-size: 0.92rem; max-width: 650px; margin: 0 auto;">
                Sign in with your work email. Your role decides which consoles you can open.
            </p>
        </div>
    """, unsafe_allow_html=True)

    _, col, _ = st.columns([1, 1.4, 1])
    with col:
        with st.form("login_form"):
            email = st.text_input("Email", placeholder="e.g. doctor@medinexus.org")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Sign In", type="primary", use_container_width=True)

        if submitted:
            if not email or not password:
                st.error("Please enter both email and password.")
                return
            try:
                user = authenticate(email, password)
            except SeedFileError as e:
                st.error(f"User store unavailable: {e}")
                return
            if user is None:
                st.error("❌ Invalid email or password.")
                return
            start_session(user)
            st.rerun()

        st.caption("Accounts come from the seeded user file (see README › Authentication).")
