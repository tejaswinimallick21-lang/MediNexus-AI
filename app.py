"""
MediNexus AI — Role-Based Healthcare Data-to-Decision Intelligence Platform
Main Streamlit Application Controller and RBAC Router.
"""

import warnings
warnings.filterwarnings("ignore")

import streamlit as st
import sys
from pathlib import Path

# Ensure root directory in sys.path
BASE_PATH = Path(__file__).resolve().parent
if str(BASE_PATH) not in sys.path:
    sys.path.insert(0, str(BASE_PATH))

from config.settings import APP_NAME, APP_TAGLINE, APP_VERSION, DEMO_USERS, ACTIVE_LLM_PROVIDER
from config.roles import ROLE_PERMISSIONS
from src.security.rbac import check_page_access, get_allowed_pages
from src.security.audit import log_audit_event
from src.utils.database import query_df, table_exists

# Import page renderers
from pages.welcome import render_welcome_page
from pages.login import render_login_page
from pages.data_engineer import render_data_engineer_page
from pages.doctor import render_doctor_page
from pages.pharmacist import render_pharmacist_page
from pages.laboratory import render_laboratory_page
from pages.receptionist import render_receptionist_page
from pages.administrator import render_administrator_page
from pages.it_admin import render_it_admin_page

# 1. Page Configuration
st.set_page_config(
    page_title=f"{APP_NAME} — Healthcare Intelligence",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 2. Healthcare Design System Theme CSS
st.markdown("""
    <style>
    /* Clean healthcare typography & styling */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }
    .main {
        background-color: #F8FAFC;
    }
    /* Sleek metric cards */
    div[data-testid="stMetric"] {
        background-color: #FFFFFF;
        border: 1px solid #E2E8F0;
        padding: 16px 20px;
        border-radius: 10px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    }
    div[data-testid="stMetricLabel"] {
        color: #64748B;
        font-size: 0.85rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    div[data-testid="stMetricValue"] {
        color: #0F172A;
        font-weight: 800;
        font-size: 1.65rem;
    }
    /* Buttons */
    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #0D9488 0%, #0F766E 100%);
        border: none;
        border-radius: 6px;
        font-weight: 600;
        padding: 0.55rem 1.25rem;
        box-shadow: 0 2px 4px rgba(13, 148, 136, 0.2);
    }
    /* Hide Streamlit default auto-generated multi-page navigation to avoid duplicate/broken links */
    [data-testid="stSidebarNav"],
    div[data-testid="stSidebarNavSeparator"],
    ul[data-testid="stSidebarNavItems"],
    section[data-testid="stSidebar"] ul:first-child {
        display: none !important;
    }
    /* Sidebar styling - High Contrast & Crisp Readability */
    section[data-testid="stSidebar"] {
        background-color: #0F172A !important;
        border-right: 1px solid #334155 !important;
    }
    section[data-testid="stSidebar"] p,
    section[data-testid="stSidebar"] span,
    section[data-testid="stSidebar"] div,
    section[data-testid="stSidebar"] label {
        color: #F1F5F9 !important;
    }
    section[data-testid="stSidebar"] h1,
    section[data-testid="stSidebar"] h2,
    section[data-testid="stSidebar"] h3,
    section[data-testid="stSidebar"] h4 {
        color: #FFFFFF !important;
        font-weight: 700 !important;
    }
    /* High-contrast sidebar navigation buttons */
    section[data-testid="stSidebar"] button {
        background-color: #1E293B !important;
        color: #FFFFFF !important;
        border: 1px solid #475569 !important;
        font-weight: 600 !important;
        font-size: 0.92rem !important;
    }
    section[data-testid="stSidebar"] button:hover {
        background-color: #0D9488 !important;
        color: #FFFFFF !important;
        border-color: #14B8A6 !important;
    }
    section[data-testid="stSidebar"] button[kind="primary"] {
        background: linear-gradient(135deg, #0D9488 0%, #0F766E 100%) !important;
        color: #FFFFFF !important;
        border: 1px solid #14B8A6 !important;
        font-weight: 700 !important;
    }
    /* Tab headers */
    button[data-baseweb="tab"] {
        font-weight: 600;
        color: #475569;
    }
    button[aria-selected="true"] {
        color: #0D9488 !important;
        border-bottom-color: #0D9488 !important;
    }
    /* Chat message container & high-contrast font styling */
    div[data-testid="stChatMessage"] {
        background-color: #FFFFFF !important;
        border: 1px solid #E2E8F0 !important;
        border-radius: 10px !important;
        padding: 14px 18px !important;
        box-shadow: 0 1px 3px rgba(0,0,0,0.03) !important;
        margin-bottom: 12px !important;
    }
    div[data-testid="stChatMessage"] p,
    div[data-testid="stChatMessage"] span,
    div[data-testid="stChatMessage"] div,
    div[data-testid="stChatMessage"] li,
    div[data-testid="stChatMessage"] label {
        color: #0F172A !important;
        font-size: 0.92rem !important;
        line-height: 1.6 !important;
    }
    div[data-testid="stChatMessage"] b,
    div[data-testid="stChatMessage"] strong {
        color: #0F172A !important;
        font-weight: 700 !important;
    }
    /* Chat input styling */
    div[data-testid="stChatInput"] {
        border-color: #CBD5E1 !important;
    }
    div[data-testid="stChatInput"] textarea {
        color: #0F172A !important;
        background-color: #FFFFFF !important;
    }
    </style>
""", unsafe_allow_html=True)

# 3. Session State Initialization
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False
if "user" not in st.session_state:
    st.session_state["user"] = None
if "role" not in st.session_state:
    st.session_state["role"] = None
if "current_page" not in st.session_state:
    st.session_state["current_page"] = "welcome"


def switch_user_persona(username_key):
    """Helper to switch persona and route to their default page."""
    user_profile = DEMO_USERS.get(username_key)
    if user_profile:
        st.session_state["authenticated"] = True
        st.session_state["user"] = user_profile
        st.session_state["username"] = user_profile["username"]
        st.session_state["name"] = user_profile["name"]
        st.session_state["role"] = user_profile["role"]
        st.session_state["department"] = user_profile["department"]

        log_audit_event(
            username=user_profile["username"],
            role=user_profile["role"],
            action="ROLE_SWITCH",
            resource="SYSTEM_AUTH",
            status="SUCCESS",
            details=f"Switched role to {user_profile['role']}",
        )

        role_meta = ROLE_PERMISSIONS.get(user_profile["role"], {})
        st.session_state["current_page"] = role_meta.get("default_page", "welcome")
        if username_key == "data_engineer" or user_profile.get("role") == "Data Engineer":
            st.session_state["pipeline_completed"] = False
        st.rerun()


# 4. Sidebar Branding & Navigation
with st.sidebar:
    st.markdown("""
        <div style="padding: 10px 0 16px 0; border-bottom: 1px solid #334155;">
            <div style="display: flex; align-items: center; gap: 10px;">
                <span style="font-size: 1.8rem;">🏥</span>
                <div>
                    <h2 style="margin: 0; color: #FFFFFF !important; font-size: 1.35rem; font-weight: 800; letter-spacing: -0.5px;">MediNexus AI</h2>
                    <span style="color: #2DD4BF !important; font-size: 0.72rem; font-weight: 700; letter-spacing: 0.5px;">HEALTHCARE DECISION PLATFORM</span>
                </div>
            </div>
        </div>
    """, unsafe_allow_html=True)

    # User Profile / Authentication State
    if st.session_state["authenticated"]:
        user = st.session_state["user"]
        role = st.session_state["role"]

        st.markdown(f"""
            <div style="background: #1E293B; border-radius: 8px; padding: 12px 14px; margin: 12px 0; border: 1px solid #334155;">
                <div style="color: #38BDF8 !important; font-size: 0.72rem; text-transform: uppercase; font-weight: 800; letter-spacing: 0.5px;">ACTIVE ROLE</div>
                <div style="color: #FFFFFF !important; font-weight: 800; font-size: 1.05rem; margin-top: 2px;">{role}</div>
                <div style="color: #94A3B8 !important; font-size: 0.76rem; margin-top: 2px;">{user.get('department', '')}</div>
            </div>
        """, unsafe_allow_html=True)

        st.markdown("<p style='color: #38BDF8 !important; font-size: 0.8rem; font-weight: 800; margin-top: 14px; letter-spacing: 0.8px;'>AUTHORIZED CONSOLES</p>", unsafe_allow_html=True)

        allowed_pages = get_allowed_pages(role)

        page_display_names = {
            "data_engineer": "⚙️ Data Engineering",
            "doctor": "🩺 Doctor Dashboard",
            "administrator": "🏢 Executive Dashboard",
            "pharmacist": "💊 Pharmacy Dashboard",
            "laboratory": "🔬 Laboratory Dashboard",
            "receptionist": "📋 Receptionist Dashboard",
            "it_admin": "🛡️ IT & Security Admin",
            "welcome": "🏠 Platform Overview",
        }

        preferred_order = ["data_engineer", "doctor", "administrator", "pharmacist", "laboratory", "receptionist", "it_admin", "welcome"]
        ordered_pages = [p for p in preferred_order if p in allowed_pages] + [p for p in allowed_pages if p not in preferred_order]

        for p_key in ordered_pages:
            if p_key in page_display_names:
                btn_type = "primary" if st.session_state["current_page"] == p_key else "secondary"
                if st.button(page_display_names[p_key], key=f"nav_{p_key}", use_container_width=True):
                    st.session_state["current_page"] = p_key
                    st.rerun()

        # Quick Switch Persona in Sidebar (Data Engineer FIRST, NO personal names)
        st.markdown("---")
        st.markdown("<p style='color: #38BDF8 !important; font-size: 0.78rem; font-weight: 800; margin-bottom: 4px; letter-spacing: 0.8px;'>🔄 SWITCH DEMO ROLE</p>", unsafe_allow_html=True)
        role_map = {
            "⚙️ Data Engineer": "data_engineer",
            "🩺 Doctor": "dr_chen",
            "🏢 Hospital Administrator": "admin_holloway",
            "💊 Pharmacist": "pharmacist_patel",
            "🔬 Laboratory Specialist": "lab_tech_kim",
            "📋 Receptionist": "receptionist_davis",
            "🛡️ IT Administrator": "it_admin_torvalds",
        }
        options_list = ["(Select to switch role...)"] + list(role_map.keys())
        sw_role = st.selectbox("Role Switcher:", options=options_list, index=0, label_visibility="collapsed")
        if sw_role in role_map:
            switch_user_persona(role_map[sw_role])

        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🚪 Sign Out", use_container_width=True):
            log_audit_event(
                username=st.session_state.get("username", "user"),
                role=role,
                action="LOGOUT",
                resource="SYSTEM_AUTH",
                status="SUCCESS",
                details="Signed out gracefully.",
            )
            st.session_state["authenticated"] = False
            st.session_state["user"] = None
            st.session_state["role"] = None
            st.session_state["current_page"] = "welcome"
            st.rerun()

    else:
        st.markdown("""
            <div style="background: #1E293B; border-radius: 8px; padding: 12px; margin: 12px 0; border: 1px solid #475569;">
                <div style="color: #38BDF8 !important; font-size: 0.75rem; text-transform: uppercase; font-weight: 800; letter-spacing: 0.5px;">GUEST SESSION</div>
                <div style="color: #FFFFFF !important; font-size: 0.86rem; line-height: 1.4; margin-top: 4px;">
                    Select a <b>Role</b> below to explore intelligence consoles.
                </div>
            </div>
        """, unsafe_allow_html=True)

        if st.button("🔑 Sign In with Credentials", type="primary", use_container_width=True):
            st.session_state["current_page"] = "login"
            st.rerun()

        if st.button("🏠 Platform Welcome", use_container_width=True):
            st.session_state["current_page"] = "welcome"
            st.rerun()

    # System Status Indicator
    st.markdown("<br>", unsafe_allow_html=True)
    gold_ready = table_exists("gold_patient_360")
    ml_ready = table_exists("model_registry")

    st.markdown(f"""
        <div style="background: #1E293B; border-radius: 8px; padding: 12px; font-size: 0.8rem; border: 1px solid #475569; color: #FFFFFF !important;">
            <div style="font-weight: 800; color: #38BDF8 !important; margin-bottom: 6px; letter-spacing: 0.5px;">PLATFORM READINESS</div>
            <div style="color: #FFFFFF !important;">Lakehouse Gold: <b style="color: {'#4ADE80' if gold_ready else '#F87171'} !important;">{'Ready ✓' if gold_ready else 'Uninitialized'}</b></div>
            <div style="color: #FFFFFF !important;">ML Registry: <b style="color: {'#4ADE80' if ml_ready else '#F87171'} !important;">{'Active ✓' if ml_ready else 'Untrained'}</b></div>
            <div style="color: #FFFFFF !important;">AI Engine: <b style="color: #38BDF8 !important;">{ACTIVE_LLM_PROVIDER}</b></div>
            <div style="margin-top: 5px; font-size: 0.72rem; color: #94A3B8 !important;">Version: {APP_VERSION}</div>
        </div>
    """, unsafe_allow_html=True)


# 5. Strict RBAC Enforcement & Page Dispatcher
target_page = st.session_state.get("current_page", "welcome")
user_role = st.session_state.get("role")

# Check RBAC permission for requested page
if target_page not in ["welcome", "login"]:
    if not st.session_state.get("authenticated"):
        render_login_page()
    elif not check_page_access(user_role, target_page):
        st.error(f"⛔ ACCESS DENIED: Role '{user_role}' is not authorized to access '{target_page}'. This event has been recorded in the security audit trail.")
        log_audit_event(
            username=st.session_state.get("username", "user"),
            role=user_role,
            action="ACCESS_DENIED",
            resource=f"PAGE_{target_page.upper()}",
            status="BLOCKED",
            details=f"Unauthorized page access attempt to {target_page}",
        )
        if st.button("Return to Allowed Dashboard", type="primary"):
            role_meta = ROLE_PERMISSIONS.get(user_role, {})
            st.session_state["current_page"] = role_meta.get("default_page", "welcome")
            st.rerun()
    else:
        # Authorized page dispatch
        if target_page == "data_engineer":
            render_data_engineer_page()
        elif target_page == "doctor":
            render_doctor_page()
        elif target_page == "pharmacist":
            render_pharmacist_page()
        elif target_page == "laboratory":
            render_laboratory_page()
        elif target_page == "receptionist":
            render_receptionist_page()
        elif target_page == "administrator":
            render_administrator_page()
        elif target_page == "it_admin":
            render_it_admin_page()
        else:
            render_welcome_page()
else:
    if target_page == "login":
        render_login_page()
    else:
        render_welcome_page()
