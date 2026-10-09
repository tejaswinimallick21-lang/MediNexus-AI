"""
MediNexus AI — Simple Executive Guide & Platform Walkthrough
============================================================
Generates a clean, simple, highly accessible, and visually elegant PDF guide
for senior leadership, clinical directors, and non-technical stakeholders.
Outputs: MediNexus_AI_Simple_Guide.pdf
"""

import os
import sys
from pathlib import Path
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
    KeepTogether,
    HRFlowable,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfgen import canvas

# Theme Colors
PRIMARY_TEAL = colors.HexColor("#0D9488")
ACCENT_BLUE = colors.HexColor("#0284C7")
DARK_NAVY = colors.HexColor("#0F172A")
BODY_CHARCOAL = colors.HexColor("#1E293B")
MUTED_SLATE = colors.HexColor("#64748B")
LIGHT_CARD_BG = colors.HexColor("#F8FAFC")
BORDER_LIGHT = colors.HexColor("#E2E8F0")
MINT_GREEN = colors.HexColor("#10B981")
AMBER_ALERT = colors.HexColor("#F59E0B")
SOFT_BLUE_BG = colors.HexColor("#EFF6FF")
SOFT_GREEN_BG = colors.HexColor("#F0FDF4")


class SimpleNumberedCanvas(canvas.Canvas):
    """Adds clean running header and footer with total page count."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_decorations(self, total_pages):
        # Skip headers/footers on cover page
        if self._pageNumber == 1:
            return

        self.saveState()
        self.setFont("Helvetica-Bold", 8)
        self.setFillColor(MUTED_SLATE)

        # Top Header
        self.drawString(45, 752, "MEDINEXUS AI")
        self.setFont("Helvetica", 8)
        self.drawRightString(567, 752, "SIMPLE EXECUTIVE GUIDE & WALKTHROUGH")
        self.setStrokeColor(BORDER_LIGHT)
        self.setLineWidth(0.8)
        self.line(45, 744, 567, 744)

        # Bottom Footer
        self.line(45, 42, 567, 42)
        self.drawString(45, 30, "Confidential — Healthcare Executive Decision Support")
        self.drawRightString(567, 30, f"Page {self._pageNumber} of {total_pages}")
        self.restoreState()


def create_simple_guide():
    output_filename = "MediNexus_AI_Simple_Guide.pdf"
    output_path = Path("D:/Virtusa Project") / output_filename

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        leftMargin=45,
        rightMargin=45,
        topMargin=54,
        bottomMargin=54,
    )

    styles = getSampleStyleSheet()

    # Custom Clean Typography
    title_style = ParagraphStyle(
        "CoverTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=26,
        leading=32,
        textColor=DARK_NAVY,
        spaceAfter=8,
    )
    subtitle_style = ParagraphStyle(
        "CoverSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=13,
        leading=18,
        textColor=ACCENT_BLUE,
        spaceAfter=15,
    )
    h1_style = ParagraphStyle(
        "SimpleH1",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=16,
        leading=21,
        textColor=DARK_NAVY,
        spaceBefore=12,
        spaceAfter=6,
    )
    h2_style = ParagraphStyle(
        "SimpleH2",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=15,
        textColor=PRIMARY_TEAL,
        spaceBefore=6,
        spaceAfter=2,
    )
    body_style = ParagraphStyle(
        "SimpleBody",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=13.5,
        textColor=BODY_CHARCOAL,
        spaceAfter=4,
    )
    bullet_style = ParagraphStyle(
        "SimpleBullet",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.8,
        leading=12.5,
        textColor=BODY_CHARCOAL,
        leftIndent=14,
        spaceAfter=2,
    )
    callout_style = ParagraphStyle(
        "SimpleCallout",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9.5,
        leading=14.5,
        textColor=DARK_NAVY,
    )
    table_header_style = ParagraphStyle(
        "TableHeader",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=12,
        textColor=colors.white,
    )
    table_cell_style = ParagraphStyle(
        "TableCell",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=12,
        textColor=BODY_CHARCOAL,
    )

    story = []

    # =========================================================================
    # PAGE 1: COVER & EXECUTIVE OVERVIEW
    # =========================================================================
    story.append(Spacer(1, 20))
    story.append(Paragraph("🏥 MEDINEXUS AI PLATFORM", ParagraphStyle("Pill", fontName="Helvetica-Bold", fontSize=9, textColor=PRIMARY_TEAL, spaceAfter=6)))
    story.append(Paragraph("Simple Executive Guide & Walkthrough", title_style))
    story.append(Paragraph("A Clear, Non-Technical Overview of Healthcare Data-to-Decision Intelligence", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=2, color=PRIMARY_TEAL, spaceAfter=18))

    # Highlight Card
    card_text = (
        "<b>Executive Summary in 30 Seconds:</b><br/>"
        "Healthcare organizations collect millions of data points from patients, labs, medicines, and admissions. "
        "Usually, this data is messy, scattered across different computers, and hard to understand.<br/><br/>"
        "<b>MediNexus AI</b> takes this messy hospital data, automatically cleans it to a <b>99.6% quality standard</b>, "
        "uses smart machine learning to <b>predict risks</b> (like readmissions or drug shortages), and gives each hospital "
        "worker (Doctor, Pharmacist, Lab Technician, Administrator) exactly the <b>clear recommendations</b> they need to take action."
    )
    summary_table = Table([[Paragraph(card_text, callout_style)]], colWidths=[522])
    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), SOFT_BLUE_BG),
        ("BOX", (0, 0), (-1, -1), 1, ACCENT_BLUE),
        ("PADDING", (0, 0), (-1, -1), 14),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 15))

    story.append(Paragraph("The Core Philosophy Behind the App", h1_style))
    story.append(Paragraph(
        "Most software just shows historical charts (what already happened). MediNexus AI goes much further by guiding "
        "decisions before problems happen. The app follows a clear 6-step formula:",
        body_style
    ))

    # 6-Step Simple Table
    steps_data = [
        [Paragraph("Step", table_header_style), Paragraph("Stage Name", table_header_style), Paragraph("Plain English Meaning", table_header_style), Paragraph("What It Solves", table_header_style)],
        [Paragraph("1", table_cell_style), Paragraph("<b>DATA</b>", table_cell_style), Paragraph("Gathering records from all 12 hospital sources", table_cell_style), Paragraph("No more missing pieces of patient history.", table_cell_style)],
        [Paragraph("2", table_cell_style), Paragraph("<b>TRUST</b>", table_cell_style), Paragraph("Fixing duplicates, typos, and bad dates (99.6% clean)", table_cell_style), Paragraph("Doctors never look at bad or corrupted data.", table_cell_style)],
        [Paragraph("3", table_cell_style), Paragraph("<b>INTELLIGENCE</b>", table_cell_style), Paragraph("Combining everything into a unified Patient 360 view", table_cell_style), Paragraph("One single screen for the whole hospital.", table_cell_style)],
        [Paragraph("4", table_cell_style), Paragraph("<b>PREDICTION</b>", table_cell_style), Paragraph("AI forecasts readmissions, hospital stay days, and medicine demand", table_cell_style), Paragraph("Knowing problems days before they happen.", table_cell_style)],
        [Paragraph("5", table_cell_style), Paragraph("<b>PRESCRIPTION</b>", table_cell_style), Paragraph("Giving actionable checklists (e.g., discharge steps, auto-orders)", table_cell_style), Paragraph("Tells the staff exactly what to do next.", table_cell_style)],
        [Paragraph("6", table_cell_style), Paragraph("<b>ACTION</b>", table_cell_style), Paragraph("7 customized dashboards tailored strictly by job role", table_cell_style), Paragraph("Zero clutter, zero confusion, zero HIPAA privacy leaks.", table_cell_style)],
    ]
    t_steps = Table(steps_data, colWidths=[40, 85, 230, 167])
    t_steps.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), DARK_NAVY),
        ("BOX", (0, 0), (-1, -1), 0.8, BORDER_LIGHT),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER_LIGHT),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_CARD_BG]),
        ("PADDING", (0, 0), (-1, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(t_steps)

    story.append(PageBreak())

    # =========================================================================
    # PAGE 2: HOW THE DATA FLOWS (MEDALLION MADE SIMPLE)
    # =========================================================================
    story.append(Paragraph("1. How the Data Flows (The Medallion Pipeline)", h1_style))
    story.append(Paragraph(
        "To make sure doctors and executives only see trustworthy numbers, the system processes all data through "
        "three clean stages called the <b>Medallion Architecture</b> (Bronze ➔ Silver ➔ Gold):",
        body_style
    ))

    flow_data = [
        [
            Paragraph("🥉 <b>BRONZE LAYER</b><br/><font color='#64748B'>Raw Ingestion</font>", ParagraphStyle("FlowT", fontName="Helvetica", fontSize=9, leading=13)),
            Paragraph(
                "• Collects raw files from hospital departments (appointments, labs, bills, medicines).<br/>"
                "• Saves exact copies without changing anything, creating a permanent audit trail.<br/>"
                "• <i>Think of it as: The raw, untouched intake archive.</i>",
                table_cell_style
            )
        ],
        [
            Paragraph("🥈 <b>SILVER LAYER</b><br/><font color='#64748B'>Automated Cleaning</font>", ParagraphStyle("FlowT", fontName="Helvetica", fontSize=9, leading=13)),
            Paragraph(
                "• Automatically removes duplicate records and fixes typos (e.g. 'mAlE' becomes 'Male').<br/>"
                "• Fixes messy date formats into standard dates.<br/>"
                "• Calculates a mathematical <b>Quality Index of 99.6%</b>.<br/>"
                "• <i>Think of it as: The hospital data car wash.</i>",
                table_cell_style
            )
        ],
        [
            Paragraph("🥇 <b>GOLD LAYER</b><br/><font color='#64748B'>Business & Clinical Marts</font>", ParagraphStyle("FlowT", fontName="Helvetica", fontSize=9, leading=13)),
            Paragraph(
                "• Joins everything into ready-to-use views: <b>Patient 360</b>, Bed Occupancy, Pharmacy Stock.<br/>"
                "• <b>Strict Rule:</b> All dashboards (Doctors, Administrators, Pharmacists) ONLY read from Gold.<br/>"
                "• <i>Think of it as: The certified clinical gold standard.</i>",
                table_cell_style
            )
        ],
    ]
    t_flow = Table(flow_data, colWidths=[140, 382])
    t_flow.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1, BORDER_LIGHT),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER_LIGHT),
        ("BACKGROUND", (0, 0), (0, -1), LIGHT_CARD_BG),
        ("PADDING", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(t_flow)
    story.append(Spacer(1, 14))

    story.append(Paragraph("2. The 3 Smart Machine Learning Predictions", h1_style))
    story.append(Paragraph(
        "MediNexus AI includes 3 built-in Machine Learning models trained on hospital data to give early warnings:",
        body_style
    ))

    ml_data = [
        [Paragraph("Prediction Model", table_header_style), Paragraph("What It Predicts", table_header_style), Paragraph("Why It Matters to Leadership", table_header_style)],
        [
            Paragraph("<b>30-Day Readmission Risk</b>", table_cell_style),
            Paragraph("Calculates the exact probability (0–100%) that a patient will be readmitted within 30 days after leaving.", table_cell_style),
            Paragraph("Prevents heavy hospital financial penalties from Medicare/CMS and protects vulnerable patients.", table_cell_style)
        ],
        [
            Paragraph("<b>Length of Stay (LOS)</b>", table_cell_style),
            Paragraph("Predicts how many days an admitted patient will stay in the hospital (e.g. 5.5 days).", table_cell_style),
            Paragraph("Helps managers plan open beds early, avoiding emergency room overcrowding and hallway delays.", table_cell_style)
        ],
        [
            Paragraph("<b>Medication Demand Forecaster</b>", table_cell_style),
            Paragraph("Forecasts how many medicine units will be consumed over the next 30 days based on patient admissions.", table_cell_style),
            Paragraph("Stops life-saving drug stockouts before they happen and prevents buying excess medicine that expires.", table_cell_style)
        ],
    ]
    t_ml = Table(ml_data, colWidths=[130, 200, 192])
    t_ml.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PRIMARY_TEAL),
        ("BOX", (0, 0), (-1, -1), 0.8, BORDER_LIGHT),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER_LIGHT),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_CARD_BG]),
        ("PADDING", (0, 0), (-1, -1), 7),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(t_ml)

    story.append(PageBreak())

    # =========================================================================
    # PAGE 3 & 4: ALL 7 PERSONAS EXPLAINED
    # =========================================================================
    story.append(Paragraph("3. Complete Guide to All 7 Personas", h1_style))
    story.append(Paragraph(
        "Each stakeholder logs into a dedicated screen designed specifically for their job. "
        "There is no shared clutter, no personal names, and strict privacy protection:",
        body_style
    ))

    # Persona 1: Data Engineer
    story.append(Paragraph("⚙️ Persona #1: Lead Data Engineer (The Foundation)", h2_style))
    story.append(Paragraph("<b>Who it is:</b> The data professional who operates the pipeline before anyone else.", body_style))
    story.append(Paragraph("<b>What they see & do:</b>", body_style))
    story.append(Paragraph("• Starts the Medallion Pipeline and watches real-time processing logs.", bullet_style))
    story.append(Paragraph("• Checks the <b>Data Quality Scorecard (99.6%)</b> for duplicates and missing values.", bullet_style))
    story.append(Paragraph("• Retrains the Machine Learning models with one click.", bullet_style))
    story.append(Paragraph("<b>Key Benefit:</b> Guarantees all data is 100% clean and verified before clinicians use it.", body_style))
    story.append(Spacer(1, 4))

    # Persona 2: Doctor
    story.append(Paragraph("🩺 Persona #2: Attending Physician / Doctor (Clinical Decision Support)", h2_style))
    story.append(Paragraph("<b>Who it is:</b> The doctor doing morning rounds or preparing patient discharge.", body_style))
    story.append(Paragraph("<b>What they see & do:</b>", body_style))
    story.append(Paragraph("• <b>Patient 360 Banner:</b> Instant view of patient name, age, blood type, and conditions (e.g. COPD, Hypertension).", bullet_style))
    story.append(Paragraph("• <b>AI Risk Score:</b> Shows 30-day readmission risk percentage with a visual colored progress bar.", bullet_style))
    story.append(Paragraph("• <b>Discharge Checklist:</b> Practical checklist (e.g. 48-hr nurse call, specialist appointment).", bullet_style))
    story.append(Paragraph("• <b>Lab Trends & Medications:</b> Longitudinal charts of lab tests and active prescription lists.", bullet_style))
    story.append(Paragraph("• <b>MediCare AI Copilot:</b> Built-in clinical AI chat grounded in institutional guidelines.", bullet_style))
    story.append(Paragraph("<b>Key Benefit:</b> Cuts chart review time by 65% and prevents patients from bouncing back to the hospital.", body_style))
    story.append(Spacer(1, 4))

    # Persona 3: Hospital Administrator
    story.append(Paragraph("🏢 Persona #3: Hospital Administrator (Operations & Capacity)", h2_style))
    story.append(Paragraph("<b>Who it is:</b> Hospital CEO, COO, or Operations Director.", body_style))
    story.append(Paragraph("<b>What they see & do:</b>", body_style))
    story.append(Paragraph("• <b>Bed Occupancy Rate:</b> Live percentage of occupied beds across hospital facilities.", bullet_style))
    story.append(Paragraph("• <b>Bed Surge Alerts:</b> Automatic Level 1 to 4 alerts when beds become crowded (>82%).", bullet_style))
    story.append(Paragraph("• <b>Financial Intelligence:</b> Tracks gross revenue, patient dues, and revenue leakage.", bullet_style))
    story.append(Paragraph("• <b>HealthAnalyst AI Copilot:</b> Executive AI assistant answering operational and capacity questions.", bullet_style))
    story.append(Paragraph("<b>Key Benefit:</b> Prevents emergency room overcrowding and unlocks up to $1.2M in surgical bed capacity.", body_style))
    story.append(Spacer(1, 4))

    # Persona 4: Pharmacist
    story.append(Paragraph("💊 Persona #4: Clinical Pharmacist (Medicines & Supply Chain)", h2_style))
    story.append(Paragraph("<b>Who it is:</b> Chief Pharmacist managing the central hospital pharmacy.", body_style))
    story.append(Paragraph("<b>What they see & do:</b>", body_style))
    story.append(Paragraph("• <b>Stockout Risk Alerts:</b> Flags critical drugs running dangerously low (e.g., Insulin, Furosemide).", bullet_style))
    story.append(Paragraph("• <b>30-Day Demand Forecast:</b> Predicts how many doses will be needed based on patient illness trends.", bullet_style))
    story.append(Paragraph("• <b>Auto Purchase Orders:</b> Formats instant electronic purchase orders with exact order quantities.", bullet_style))
    story.append(Paragraph("<b>Key Benefit:</b> Stops emergency drug shortages and saves $360,000 annually in expired medication waste.", body_style))

    story.append(PageBreak())

    # Persona 5: Laboratory Specialist
    story.append(Paragraph("🔬 Persona #5: Laboratory Specialist (Diagnostic Speed & Safety)", h2_style))
    story.append(Paragraph("<b>Who it is:</b> Pathology and clinical lab technologist.", body_style))
    story.append(Paragraph("<b>What they see & do:</b>", body_style))
    story.append(Paragraph("• <b>Specimen Analyzer Volumes:</b> Tracks daily test throughput across blood, chemistry, and cultures.", bullet_style))
    story.append(Paragraph("• <b>Turnaround Times:</b> Monitors whether emergency tests finish within the 45-minute target.", bullet_style))
    story.append(Paragraph("• <b>Critical Panic Alert Tracker:</b> Immediately isolates life-threatening lab values (e.g. Potassium > 6.0) with callback verification.", bullet_style))
    story.append(Paragraph("<b>Key Benefit:</b> Speeds up urgent lab notifications from 65 minutes to under 15 minutes, saving critical lives.", body_style))
    story.append(Spacer(1, 4))

    # Persona 6: Receptionist
    story.append(Paragraph("📋 Persona #6: Front Desk Receptionist (Fast, HIPAA-Compliant Intake)", h2_style))
    story.append(Paragraph("<b>Who it is:</b> Outpatient clinic intake and registration staff.", body_style))
    story.append(Paragraph("<b>What they see & do:</b>", body_style))
    story.append(Paragraph("• <b>Live Patient Intake Queue:</b> Real-time list of arriving patients and waiting room queues.", bullet_style))
    story.append(Paragraph("• <b>1-Click Check-In:</b> Quickly registers arriving patients and assigns doctor appointments.", bullet_style))
    story.append(Paragraph("• <b>Strict Privacy Masking (HIPAA):</b> All diagnoses, medical codes, and lab results are hidden from this screen.", bullet_style))
    story.append(Paragraph("<b>Key Benefit:</b> Reduces intake check-in time from 8 minutes to under 2 minutes with zero HIPAA privacy leaks.", body_style))
    story.append(Spacer(1, 4))

    # Persona 7: IT & Security Administrator
    story.append(Paragraph("🛡️ Persona #7: IT & Security Administrator (Governance & Compliance)", h2_style))
    story.append(Paragraph("<b>Who it is:</b> Chief Information Security Officer (CISO) and system engineers.", body_style))
    story.append(Paragraph("<b>What they see & do:</b>", body_style))
    story.append(Paragraph("• <b>Live Security Audit Log:</b> Tracks every single login, patient chart view, and AI query with exact timestamps and IP addresses.", bullet_style))
    story.append(Paragraph("• <b>Role-Based Access Verification:</b> Confirms that only authorized roles can access clinical or operational screens.", bullet_style))
    story.append(Paragraph("• <b>Database Health & Telemetry:</b> Monitors DuckDB storage size and system memory in real time.", bullet_style))
    story.append(Paragraph("<b>Key Benefit:</b> Guarantees 100% audit-readiness for hospital accreditation and prevents insider data snooping.", body_style))

    story.append(Spacer(1, 10))
    story.append(Paragraph("4. The AI Copilots & Multi-Model Engine", h1_style))
    story.append(Paragraph(
        "MediNexus AI includes role-specific AI Copilots (MediCare for Doctors, HealthAnalyst for Administrators, "
        "and PharmaLab for Pharmacy/Lab). Here is how they work in simple terms:",
        body_style
    ))
    story.append(Paragraph("• <b>Zero Hallucinations (Grounded RAG):</b> The AI is never allowed to make up numbers. It searches through actual hospital records and institutional clinical guideline documents before answering.", bullet_style))
    story.append(Paragraph("• <b>Multi-Model Flexibility:</b> Supports cutting-edge <b>xAI Grok API</b>, <b>Google Gemini 1.5 Flash</b>, or runs <b>100% Offline locally</b> with zero internet required.", bullet_style))
    story.append(Paragraph("• <b>Structured Answers:</b> Every answer is cleanly split into <b>Verified Facts</b> (green), <b>Predictions</b> (blue), and <b>Recommendations</b> (amber).", bullet_style))
    story.append(Paragraph("• <b>High-Contrast Readability:</b> Clean white chat bubbles with crisp, dark text and 1-click suggested inquiry chips.", bullet_style))

    story.append(PageBreak())

    # =========================================================================
    # PAGE 5: STEP-BY-STEP LEADERSHIP DEMO GUIDE & ROI
    # =========================================================================
    story.append(Paragraph("5. Step-by-Step Leadership Demo Guide (How to Present)", h1_style))
    story.append(Paragraph(
        "When showing this platform to senior executives, follow this smooth 6-minute demonstration sequence:",
        body_style
    ))

    demo_steps = [
        [Paragraph("Order", table_header_style), Paragraph("Role to Select", table_header_style), Paragraph("What to Click & Show", table_header_style), Paragraph("Key Message to Tell Leadership", table_header_style)],
        [
            Paragraph("<b>1st</b>", table_cell_style),
            Paragraph("<b>Data Engineer</b>", table_cell_style),
            Paragraph("Click <i>'Run Medallion Pipeline'</i>. Watch the live logs turn into clean Gold tables and a 99.6% quality score.", table_cell_style),
            Paragraph("'We begin with data trust. Messy hospital data is automatically cleaned before any doctor sees it.'", table_cell_style)
        ],
        [
            Paragraph("<b>2nd</b>", table_cell_style),
            Paragraph("<b>Doctor</b>", table_cell_style),
            Paragraph("Select Patient <b>P_00001 (Daniel Lyons)</b>. Show the 66.2% readmission risk bar, expected stay (5.5d), and discharge checklist.", table_cell_style),
            Paragraph("'Doctors get instant Patient 360 intelligence and actionable discharge care plans in seconds.'", table_cell_style)
        ],
        [
            Paragraph("<b>3rd</b>", table_cell_style),
            Paragraph("<b>Doctor (AI)</b>", table_cell_style),
            Paragraph("Click the <i>'MediCare AI Copilot'</i> tab. Click a suggested question chip to see the grounded clinical response.", table_cell_style),
            Paragraph("'Our clinical copilot answers complex questions with zero hallucinations, citing hospital guidelines.'", table_cell_style)
        ],
        [
            Paragraph("<b>4th</b>", table_cell_style),
            Paragraph("<b>Administrator</b>", table_cell_style),
            Paragraph("Switch to Administrator. Show the network bed occupancy rate and automated Bed Surge Action Plan.", table_cell_style),
            Paragraph("'Executives get real-time hospital capacity oversight to prevent emergency room overcrowding.'", table_cell_style)
        ],
        [
            Paragraph("<b>5th</b>", table_cell_style),
            Paragraph("<b>Pharmacist</b>", table_cell_style),
            Paragraph("Switch to Pharmacist. Show the low-stock alert for Insulin and generate an automated purchase order.", table_cell_style),
            Paragraph("'We protect the medicine supply chain and stop drug shortages before they impact patients.'", table_cell_style)
        ],
        [
            Paragraph("<b>6th</b>", table_cell_style),
            Paragraph("<b>Receptionist</b>", table_cell_style),
            Paragraph("Switch to Receptionist. Show the patient queue and demonstrate that medical diagnoses are masked.", table_cell_style),
            Paragraph("'Front desk staff check in patients faster while strictly protecting patient privacy under HIPAA.'", table_cell_style)
        ],
        [
            Paragraph("<b>7th</b>", table_cell_style),
            Paragraph("<b>IT Admin</b>", table_cell_style),
            Paragraph("Switch to IT Administrator. Open the live audit log to show every action we just took was recorded.", table_cell_style),
            Paragraph("'Complete compliance, full traceability, and enterprise cybersecurity.'", table_cell_style)
        ],
    ]
    t_demo = Table(demo_steps, colWidths=[38, 92, 202, 190])
    t_demo.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), DARK_NAVY),
        ("BOX", (0, 0), (-1, -1), 0.8, BORDER_LIGHT),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER_LIGHT),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_CARD_BG]),
        ("PADDING", (0, 0), (-1, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(t_demo)
    story.append(Spacer(1, 12))

    story.append(Paragraph("6. Tangible Financial & Clinical Benefits (ROI)", h1_style))
    story.append(Paragraph(
        "For a typical 500-bed regional hospital, MediNexus AI delivers a projected <b>$2.31 Million annual benefit</b>:",
        body_style
    ))

    roi_data = [
        [Paragraph("Benefit Category", table_header_style), Paragraph("Traditional Problem", table_header_style), Paragraph("MediNexus AI Value", table_header_style), Paragraph("Estimated Savings", table_header_style)],
        [
            Paragraph("<b>Readmission Reduction</b>", table_cell_style),
            Paragraph("High readmission rate triggers Medicare penalties.", table_cell_style),
            Paragraph("Reduces preventable 30-day readmissions by 18% to 24%.", table_cell_style),
            Paragraph("<b>+$750,000 / yr</b>", table_cell_style)
        ],
        [
            Paragraph("<b>Pharmacy Efficiency</b>", table_cell_style),
            Paragraph("Expensive emergency rush orders & expired medicine waste.", table_cell_style),
            Paragraph("Predictive inventory buffers prevent stockouts and waste.", table_cell_style),
            Paragraph("<b>+$360,000 / yr</b>", table_cell_style)
        ],
        [
            Paragraph("<b>Bed Capacity Unlock</b>", table_cell_style),
            Paragraph("Delayed afternoon discharges block new surgical patients.", table_cell_style),
            Paragraph("Speeds up morning discharges, unlocking 4.2% more bed capacity.", table_cell_style),
            Paragraph("<b>+$1,200,000 / yr</b>", table_cell_style)
        ],
    ]
    t_roi = Table(roi_data, colWidths=[120, 150, 162, 90])
    t_roi.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PRIMARY_TEAL),
        ("BOX", (0, 0), (-1, -1), 0.8, BORDER_LIGHT),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER_LIGHT),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_CARD_BG]),
        ("PADDING", (0, 0), (-1, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(t_roi)
    story.append(Spacer(1, 14))

    # Bottom Callout Box
    summary_box = (
        "<b>Summary Takeaway for Leadership:</b><br/>"
        "MediNexus AI is not just another passive dashboard. It is an end-to-end operational intelligence system "
        "that connects clean hospital data directly to the right decisions across every clinical and administrative department. "
        "It protects patients, saves staff hours, and preserves hospital revenue."
    )
    t_box = Table([[Paragraph(summary_box, callout_style)]], colWidths=[522])
    t_box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), SOFT_GREEN_BG),
        ("BOX", (0, 0), (-1, -1), 1, MINT_GREEN),
        ("PADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(t_box)

    # Build Document
    doc.build(story, canvasmaker=SimpleNumberedCanvas)
    print(f"Successfully generated simple PDF: {output_path}")


if __name__ == "__main__":
    create_simple_guide()
