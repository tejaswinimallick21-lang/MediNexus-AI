"""
Authentication and Role Selector Login Page for MediNexus AI.
Provides:
1. Persona-Specific Username & Password Sign-In for all 7 enterprise personas (Data Engineer #1).
2. Traditional Manual Credentials form for custom or registered user accounts.
3. User Registration (Sign Up) with DuckDB persistence for all 7 healthcare personas.
"""

import streamlit as st
from config.settings import DEMO_USERS, DEMO_PASSWORD_DEFAULT
from config.roles import ROLE_PERMISSIONS
from src.security.auth import authenticate_user, register_user
from src.security.audit import log_audit_event


PERSONAS = [
    {
        "key": "data_engineer",
        "role": "Data Engineer",
        "username": "data_engineer",
        "icon": "⚙️",
        "title": "Data Engineer",
        "dept": "Data Platform & Engineering",
        "scope": "Medallion Lakehouse (Bronze ➔ Silver ➔ Gold), 99.6% Data Quality index, and automated ML model training.",
        "color": "#0D9488",
        "badge_bg": "#CCFBF1",
        "badge_text": "#0F766E",
    },
    {
        "key": "dr_chen",
        "role": "Doctor",
        "username": "dr_chen",
        "icon": "🩺",
        "title": "Doctor",
        "dept": "Internal Medicine & Cardiology",
        "scope": "Patient 360, 30-day readmission risk, length-of-stay predictions, and MediCare Copilot.",
        "color": "#0284C7",
        "badge_bg": "#E0F2FE",
        "badge_text": "#0369A1",
    },
    {
        "key": "admin_holloway",
        "role": "Hospital Administrator",
        "username": "admin_holloway",
        "icon": "🏢",
        "title": "Hospital Administrator",
        "dept": "Executive Operations",
        "scope": "Bed occupancy metrics, Level 1-4 Bed Surge alerts, readmission root causes, and HealthAnalyst Copilot.",
        "color": "#0F172A",
        "badge_bg": "#F1F5F9",
        "badge_text": "#334155",
    },
    {
        "key": "pharmacist_patel",
        "role": "Pharmacist",
        "username": "pharmacist_patel",
        "icon": "💊",
        "title": "Pharmacist",
        "dept": "Central Clinical Pharmacy",
        "scope": "Formulary stockout alerts, 30-day medication demand forecaster, auto-POs, and PharmaLab Copilot.",
        "color": "#D97706",
        "badge_bg": "#FEF3C7",
        "badge_text": "#B45309",
    },
    {
        "key": "lab_tech_kim",
        "role": "Laboratory Technician",
        "username": "lab_tech_kim",
        "icon": "🔬",
        "title": "Laboratory Specialist",
        "dept": "Pathology & Diagnostics",
        "scope": "Analyzer throughput, turnaround times (TAT), and critical panic value callback alerts.",
        "color": "#7C3AED",
        "badge_bg": "#EDE9FE",
        "badge_text": "#6D28D9",
    },
    {
        "key": "receptionist_davis",
        "role": "Receptionist",
        "username": "receptionist_davis",
        "icon": "📋",
        "title": "Receptionist",
        "dept": "Outpatient Scheduling",
        "scope": "Intake queues, physician appointment scheduling, and patient check-in (HIPAA compliant).",
        "color": "#059669",
        "badge_bg": "#D1FAE5",
        "badge_text": "#047857",
    },
    {
        "key": "it_admin_torvalds",
        "role": "IT Administrator",
        "username": "it_admin_torvalds",
        "icon": "🛡️",
        "title": "IT Administrator",
        "dept": "Security & Infrastructure",
        "scope": "Immutable dual audit logs, RBAC enforcement, session monitoring, and DuckDB storage telemetry.",
        "color": "#DC2626",
        "badge_bg": "#FEE2E2",
        "badge_text": "#B91C1C",
    },
]


def login_with_credentials(username_input: str, password_input: str, persona_label: str = ""):
    """Helper to authenticate credentials, log audit entry, and dispatch to default view."""
    if not username_input or not password_input:
        st.error("Please enter both username and password.")
        return False

    user_profile = authenticate_user(username_input.strip(), password_input)
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
            action="LOGIN_PERSONA_CREDENTIALS",
            resource="SYSTEM_AUTH",
            status="SUCCESS",
            details=f"Authenticated as {user_profile['role']} via credentials.",
        )

        role_meta = ROLE_PERMISSIONS.get(user_profile["role"], {})
        st.session_state["current_page"] = role_meta.get("default_page", "welcome")
        if user_profile.get("role") == "Data Engineer":
            st.session_state["pipeline_completed"] = False
        st.success(f"✓ Authenticated successfully as {user_profile['role']}!")
        st.rerun()
        return True
    else:
        log_audit_event(
            username=username_input.strip(),
            role="Unknown",
            action="LOGIN_FAILED",
            resource="SYSTEM_AUTH",
            status="FAILED",
            details=f"Failed credential sign-in attempt for {persona_label or username_input}.",
        )
        st.error("❌ Invalid credentials. Please verify your username and password.")
        return False


def render_login_page():
    """Render high-contrast, multi-tab login portal with persona username/password sign-in."""
    st.markdown("""
        <div style="text-align: center; margin-bottom: 22px;">
            <div style="display: inline-block; background: #0F172A; color: #2DD4BF; padding: 4px 14px; border-radius: 20px; font-size: 0.78rem; font-weight: 700; letter-spacing: 0.5px; margin-bottom: 6px;">
                ROLE-BASED ACCESS CONTROL PORTAL
            </div>
            <h2 style="color: #0F172A; font-weight: 800; margin-bottom: 4px; font-size: 1.85rem;">MediNexus Access Portal</h2>
            <p style="color: #64748B; font-size: 0.92rem; max-width: 650px; margin: 0 auto;">
                Sign in with individual username & password credentials for each persona, use custom credentials, or create a new user account.
            </p>
        </div>
    """, unsafe_allow_html=True)

    tab_persona_auth, tab_manual, tab_signup = st.tabs([
        "🔑 Persona Sign In (Username & Password)",
        "🔐 Custom Credentials",
        "📝 Create Account (Sign Up)",
    ])

    # =========================================================================
    # TAB 1: PERSONA SIGN IN WITH USERNAME & PASSWORD (FOR EACH PERSONA)
    # =========================================================================
    with tab_persona_auth:
        st.markdown(f"""
            <div style="background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; padding: 12px 16px; margin-bottom: 16px; display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <span style="font-weight: 700; color: #0F172A; font-size: 0.92rem;">👤 Enterprise Persona Authentication</span>
                    <span style="color: #64748B; font-size: 0.82rem; margin-left: 8px;">— Every persona has pre-configured username and password credentials ready to sign in or customize.</span>
                </div>
                <span style="background: #E2E8F0; color: #334155; font-size: 0.72rem; font-weight: 700; padding: 3px 8px; border-radius: 4px;">Default Password: {DEMO_PASSWORD_DEFAULT}</span>
            </div>
        """, unsafe_allow_html=True)

        display_mode = st.radio(
            "Persona View Mode:",
            options=["🗂️ All Persona Cards (Side-by-Side)", "🎯 Single Persona Selector"],
            horizontal=True,
            index=0,
            key="persona_view_mode_toggle",
        )

        st.markdown("<br style='line-height: 4px;'>", unsafe_allow_html=True)

        # ---------------------------------------------------------------------
        # View 1: All Persona Cards Grid
        # ---------------------------------------------------------------------
        if display_mode == "🗂️ All Persona Cards (Side-by-Side)":
            # 1. Featured Persona #1: DATA ENGINEER
            p_de = PERSONAS[0]
            st.markdown(f"""
                <div style="background: #F0FDFA; border: 1.5px solid #0D9488; border-radius: 8px; padding: 14px 18px; margin-bottom: 14px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                        <div style="font-weight: 800; color: #0F766E; font-size: 1.05rem;">
                            <span style="margin-right: 6px;">{p_de['icon']}</span>{p_de['title']}
                            <span style="background: #0D9488; color: #FFFFFF; font-size: 0.68rem; font-weight: 700; padding: 2px 8px; border-radius: 12px; margin-left: 8px;">#1 PRIMARY PERSONA</span>
                        </div>
                        <span style="background: {p_de['badge_bg']}; color: {p_de['badge_text']}; padding: 3px 10px; border-radius: 4px; font-size: 0.75rem; font-weight: 700;">
                            {p_de['dept']}
                        </span>
                    </div>
                    <div style="color: #334155; font-size: 0.84rem; line-height: 1.4; margin-bottom: 6px;">
                        {p_de['scope']}
                    </div>
                </div>
            """, unsafe_allow_html=True)

            with st.form(f"form_auth_{p_de['key']}"):
                col_u, col_p, col_b = st.columns([2, 2, 2])
                with col_u:
                    de_u = st.text_input("Username", value=p_de["username"], key=f"input_u_{p_de['key']}")
                with col_p:
                    de_p = st.text_input("Password", value=DEMO_PASSWORD_DEFAULT, type="password", key=f"input_p_{p_de['key']}")
                with col_b:
                    st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
                    de_sub = st.form_submit_button(f"🔐 Sign In as {p_de['title']}", type="primary", use_container_width=True)

                if de_sub:
                    login_with_credentials(de_u, de_p, persona_label=p_de["title"])

            st.markdown("<hr style='margin: 16px 0 16px 0; border: none; border-top: 1px solid #E2E8F0;'>", unsafe_allow_html=True)

            # 2. Other 6 Personas in 2 Clean Columns
            col_left, col_right = st.columns(2)
            other_personas = PERSONAS[1:]
            for idx, p in enumerate(other_personas):
                target_col = col_left if idx % 2 == 0 else col_right
                with target_col:
                    st.markdown(f"""
                        <div style="background: #FFFFFF; border: 1px solid #E2E8F0; border-left: 4px solid {p['color']};
                                    border-radius: 8px 8px 0 0; padding: 12px 14px; margin-bottom: 0; box-shadow: 0 1px 2px rgba(0,0,0,0.02);">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 3px;">
                                <div style="font-weight: 700; color: #0F172A; font-size: 0.95rem;">
                                    <span style="margin-right: 6px;">{p['icon']}</span>{p['title']}
                                </div>
                                <span style="background: {p['badge_bg']}; color: {p['badge_text']}; padding: 2px 8px; border-radius: 4px; font-size: 0.70rem; font-weight: 600;">
                                    {p['dept']}
                                </span>
                            </div>
                            <div style="color: #64748B; font-size: 0.80rem; line-height: 1.35;">
                                {p['scope']}
                            </div>
                        </div>
                    """, unsafe_allow_html=True)

                    with st.form(f"form_auth_{p['key']}"):
                        f_u_col, f_p_col = st.columns(2)
                        with f_u_col:
                            user_in = st.text_input("Username", value=p["username"], key=f"input_u_{p['key']}")
                        with f_p_col:
                            pass_in = st.text_input("Password", value=DEMO_PASSWORD_DEFAULT, type="password", key=f"input_p_{p['key']}")

                        sub_btn = st.form_submit_button(f"🔐 Sign In as {p['title']}", use_container_width=True)
                        if sub_btn:
                            login_with_credentials(user_in, pass_in, persona_label=p["title"])

                    st.markdown("<br style='line-height: 6px;'>", unsafe_allow_html=True)

        # ---------------------------------------------------------------------
        # View 2: Focused Single Persona Selector
        # ---------------------------------------------------------------------
        else:
            col_f_left, col_f_center, col_f_right = st.columns([1, 2.5, 1])
            with col_f_center:
                persona_map = {f"{p['icon']} {p['title']} — {p['dept']}": p for p in PERSONAS}
                chosen_label = st.selectbox(
                    "Choose Persona to Sign In:",
                    options=list(persona_map.keys()),
                    index=0,
                )
                chosen_p = persona_map[chosen_label]

                st.markdown(f"""
                    <div style="background: #FFFFFF; border: 1.5px solid {chosen_p['color']}; border-radius: 8px; padding: 16px 18px; margin: 12px 0 16px 0;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                            <span style="font-weight: 800; color: #0F172A; font-size: 1.1rem;">
                                {chosen_p['icon']} {chosen_p['title']}
                            </span>
                            <span style="background: {chosen_p['badge_bg']}; color: {chosen_p['badge_text']}; padding: 3px 10px; border-radius: 4px; font-size: 0.75rem; font-weight: 700;">
                                {chosen_p['dept']}
                            </span>
                        </div>
                        <p style="color: #475569; font-size: 0.85rem; line-height: 1.45; margin: 0 0 8px 0;">
                            {chosen_p['scope']}
                        </p>
                        <div style="background: #F8FAFC; border: 1px dashed #CBD5E1; border-radius: 6px; padding: 6px 10px; font-size: 0.75rem; color: #64748B;">
                            Credential profile: <code>{chosen_p['username']}</code> | Password: <code>{DEMO_PASSWORD_DEFAULT}</code>
                        </div>
                    </div>
                """, unsafe_allow_html=True)

                with st.form(f"form_single_auth_{chosen_p['key']}"):
                    u_val = st.text_input("Username", value=chosen_p["username"], key=f"single_u_{chosen_p['key']}")
                    p_val = st.text_input("Password", value=DEMO_PASSWORD_DEFAULT, type="password", key=f"single_p_{chosen_p['key']}")
                    sub_single = st.form_submit_button(f"🔐 Sign In as {chosen_p['title']}", type="primary", use_container_width=True)

                    if sub_single:
                        login_with_credentials(u_val, p_val, persona_label=chosen_p["title"])

        # Quick credentials reference table
        with st.expander("📋 View Complete Persona Credentials Matrix"):
            st.markdown(f"""
            | Persona / Role | Department | Username | Password | Default Page |
            | :--- | :--- | :--- | :--- | :--- |
            | **⚙️ Data Engineer** *(#1)* | Data Platform & Engineering | `data_engineer` | `{DEMO_PASSWORD_DEFAULT}` | Data Engineer Dashboard |
            | **🩺 Doctor** | Internal Medicine & Cardiology | `dr_chen` | `{DEMO_PASSWORD_DEFAULT}` | Doctor Dashboard |
            | **🏢 Hospital Administrator** | Executive Operations | `admin_holloway` | `{DEMO_PASSWORD_DEFAULT}` | Hospital Admin Dashboard |
            | **💊 Pharmacist** | Central Clinical Pharmacy | `pharmacist_patel` | `{DEMO_PASSWORD_DEFAULT}` | Pharmacist Dashboard |
            | **🔬 Laboratory Specialist** | Pathology & Diagnostics | `lab_tech_kim` | `{DEMO_PASSWORD_DEFAULT}` | Laboratory Dashboard |
            | **📋 Receptionist** | Outpatient Scheduling | `receptionist_davis` | `{DEMO_PASSWORD_DEFAULT}` | Receptionist Dashboard |
            | **🛡️ IT Administrator** | Security & Infrastructure | `it_admin_torvalds` | `{DEMO_PASSWORD_DEFAULT}` | IT Admin Dashboard |
            """)

    # =========================================================================
    # TAB 2: CUSTOM / MANUAL CREDENTIALS LOGIN
    # =========================================================================
    with tab_manual:
        col_m_left, col_m_center, col_m_right = st.columns([1, 2, 1])
        with col_m_center:
            st.markdown("""
                <div style="background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; padding: 12px 16px; margin-bottom: 14px;">
                    <div style="font-weight: 700; color: #0F172A; font-size: 0.95rem; margin-bottom: 2px;">🔐 Custom Credentials Authentication</div>
                    <div style="color: #64748B; font-size: 0.82rem;">Sign in with any custom username and password, including newly registered user accounts.</div>
                </div>
            """, unsafe_allow_html=True)

            persona_options = {
                "Prefill role credentials...": None,
                "⚙️ Data Engineer": "data_engineer",
                "🩺 Doctor": "dr_chen",
                "🏢 Hospital Administrator": "admin_holloway",
                "💊 Pharmacist": "pharmacist_patel",
                "🔬 Laboratory Specialist": "lab_tech_kim",
                "📋 Receptionist": "receptionist_davis",
                "🛡️ IT Administrator": "it_admin_torvalds",
            }
            selected_prefill = st.selectbox("Optional: Prefill Persona", options=list(persona_options.keys()), index=0)
            prefill_user = persona_options.get(selected_prefill)

            default_u = prefill_user if prefill_user else ""
            default_p = DEMO_PASSWORD_DEFAULT if prefill_user else ""

            with st.form("manual_custom_login_form"):
                username_input = st.text_input("Username", value=default_u, placeholder="Enter username (e.g. data_engineer or registered username)")
                password_input = st.text_input("Password", value=default_p, type="password", placeholder="Enter password")
                submit = st.form_submit_button("Sign In with Credentials", type="primary", use_container_width=True)

                if submit:
                    login_with_credentials(username_input, password_input, persona_label=selected_prefill or username_input)

    # =========================================================================
    # TAB 3: USER REGISTRATION / SIGN UP (ALL 7 PERSONAS)
    # =========================================================================
    with tab_signup:
        col_s_left, col_s_center, col_s_right = st.columns([1, 2, 1])
        with col_s_center:
            st.markdown("""
                <div style="background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; padding: 14px 18px; margin-bottom: 16px;">
                    <h4 style="margin: 0 0 6px 0; color: #0F172A; font-weight: 700; font-size: 1.05rem;">
                        Register New Healthcare User Account
                    </h4>
                    <p style="margin: 0; color: #64748B; font-size: 0.85rem; line-height: 1.4;">
                        Select any of the 7 enterprise roles to generate authorized credentials and persist your profile into DuckDB.
                    </p>
                </div>
            """, unsafe_allow_html=True)

            role_departments = {
                "Data Engineer": ("⚙️ Data Engineer", "Data Platform & Engineering"),
                "Doctor": ("🩺 Doctor", "Internal Medicine & Cardiology"),
                "Hospital Administrator": ("🏢 Hospital Administrator", "Executive Operations"),
                "Pharmacist": ("💊 Pharmacist", "Central Clinical Pharmacy"),
                "Laboratory Specialist": ("🔬 Laboratory Specialist", "Pathology & Diagnostics"),
                "Receptionist": ("📋 Receptionist", "Outpatient Scheduling"),
                "IT Administrator": ("🛡️ IT Administrator", "Security & Infrastructure"),
            }

            with st.form("signup_registration_form"):
                role_choice_labels = [v[0] for v in role_departments.values()]
                selected_role_label = st.selectbox(
                    "Select Persona / Role",
                    options=role_choice_labels,
                    index=0,
                    help="Choose which role to create an account for.",
                )

                chosen_role = [k for k, v in role_departments.items() if v[0] == selected_role_label][0]
                default_dept = role_departments[chosen_role][1]

                reg_col1, reg_col2 = st.columns(2)
                with reg_col1:
                    reg_name = st.text_input("Full Name", placeholder="e.g. Alex Morgan")
                with reg_col2:
                    reg_username = st.text_input("Username", placeholder="e.g. alex_m (letters/numbers/_)")

                reg_col3, reg_col4 = st.columns(2)
                with reg_col3:
                    reg_email = st.text_input("Email Address", placeholder="e.g. alex.m@hospital.org")
                with reg_col4:
                    reg_dept = st.text_input("Department", value=default_dept)

                reg_col5, reg_col6 = st.columns(2)
                with reg_col5:
                    reg_pwd = st.text_input("Password", type="password", placeholder="At least 6 characters")
                with reg_col6:
                    reg_pwd_confirm = st.text_input("Confirm Password", type="password", placeholder="Re-enter password")

                reg_submit = st.form_submit_button("📝 Create Account & Sign In", type="primary", use_container_width=True)

                if reg_submit:
                    if not reg_name or not reg_username or not reg_email or not reg_pwd:
                        st.error("Please fill in all required fields.")
                    elif reg_pwd != reg_pwd_confirm:
                        st.error("Passwords do not match. Please ensure both passwords match.")
                    else:
                        success, message = register_user(
                            username=reg_username,
                            name=reg_name,
                            email=reg_email,
                            role=chosen_role,
                            department=reg_dept,
                            password=reg_pwd,
                        )
                        if success:
                            log_audit_event(
                                username=reg_username.strip().lower(),
                                role=chosen_role,
                                action="USER_SIGNUP",
                                resource="SYSTEM_AUTH",
                                status="SUCCESS",
                                details=f"New user registered: {reg_name} as {chosen_role}",
                            )
                            # Authenticate immediately
                            user_profile = authenticate_user(reg_username, reg_pwd)
                            if user_profile:
                                st.session_state["authenticated"] = True
                                st.session_state["user"] = user_profile
                                st.session_state["username"] = user_profile["username"]
                                st.session_state["name"] = user_profile["name"]
                                st.session_state["role"] = user_profile["role"]
                                st.session_state["department"] = user_profile["department"]

                                role_meta = ROLE_PERMISSIONS.get(user_profile["role"], {})
                                st.session_state["current_page"] = role_meta.get("default_page", "welcome")
                                if chosen_role == "Data Engineer":
                                    st.session_state["pipeline_completed"] = False
                                st.success(f"{message} Logging in...")
                                st.rerun()
                        else:
                            st.error(message)


if __name__ == "__main__":
    render_login_page()
