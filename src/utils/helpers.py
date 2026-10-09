"""
Helper utilities and formatting functions for MediNexus AI.
"""

import uuid
from datetime import datetime
from typing import Any, Dict, Optional
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

# Healthcare Design Tokens
PALETTE = {
    "primary": "#0D9488",       # Deep Medical Teal
    "secondary": "#0284C7",     # Clinical Blue
    "accent": "#6366F1",        # Indigo
    "success": "#10B981",       # Emerald
    "warning": "#F59E0B",       # Amber
    "danger": "#EF4444",        # Crimson
    "dark": "#0F172A",          # Slate Dark
    "card_bg": "#1E293B",       # Slate 800
    "light_bg": "#F8FAFC",      # Slate 50
    "text": "#E2E8F0",          # Slate 200
    "muted": "#94A3B8",         # Slate 400
}


def generate_uuid(prefix: str = "") -> str:
    """Generate a unique ID with an optional prefix."""
    uid = str(uuid.uuid4())[:8]
    return f"{prefix}_{uid}" if prefix else uid


def format_currency(value: Optional[float]) -> str:
    """Format numeric value as USD currency."""
    if value is None or pd.isna(value):
        return "$0.00"
    return f"${value:,.2f}"


def format_percent(value: Optional[float], decimals: int = 1) -> str:
    """Format numeric float (e.g. 0.854) as percentage."""
    if value is None or pd.isna(value):
        return "0.0%"
    return f"{value * 100:.{decimals}f}%"


def format_number(value: Optional[float], decimals: int = 0) -> str:
    """Format number with thousands separators."""
    if value is None or pd.isna(value):
        return "0"
    if decimals == 0:
        return f"{int(round(value)):,}"
    return f"{value:,.{decimals}f}"


def get_risk_badge(risk_level: str) -> str:
    """Return colored HTML badge for a risk classification."""
    risk = str(risk_level).upper()
    if "HIGH" in risk or "CRITICAL" in risk:
        color = "#EF4444"
        bg = "#FEE2E2"
    elif "MODERATE" in risk or "MEDIUM" in risk:
        color = "#D97706"
        bg = "#FEF3C7"
    else:
        color = "#059669"
        bg = "#D1FAE5"
    return f'<span style="background-color: {bg}; color: {color}; font-weight: 600; padding: 3px 8px; border-radius: 4px; font-size: 0.85rem;">{risk}</span>'


def apply_healthcare_chart_theme(fig: go.Figure, title: str = "", height: int = 380) -> go.Figure:
    """Apply consistent, professional styling to Plotly figures."""
    fig.update_layout(
        title=dict(text=f"<b>{title}</b>" if title else "", font=dict(size=15, color="#1E293B")),
        template="plotly_white",
        height=height,
        margin=dict(l=40, r=30, t=50, b=40),
        font=dict(family="Inter, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif"),
        plot_bgcolor="#FFFFFF",
        paper_bgcolor="#FFFFFF",
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            font=dict(size=11),
        ),
    )
    fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor="#F1F5F9")
    fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor="#F1F5F9")
    return fig
