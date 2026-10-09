"""
Base AI Agent Architecture for MediNexus AI.
Enforces tool-grounded reasoning, structured output separation (Facts, Predictions, Recommendations),
and integration with Gemini API or deterministic offline analytical synthesis.
"""

from typing import Dict, Any, List, Optional, Callable
import os
import requests
import json

from config.settings import (
    GEMINI_API_KEY,
    ENABLE_GEMINI,
    GROK_API_KEY,
    ENABLE_GROK,
    GROK_MODEL,
    ACTIVE_LLM_PROVIDER,
)
from src.security.audit import log_audit_event


class BaseHealthcareAgent:
    """
    Base class for MediNexus role-specific AI Agents.
    """

    def __init__(self, agent_name: str, role: str, system_prompt: str):
        self.agent_name = agent_name
        self.role = role
        self.system_prompt = system_prompt
        self.tools: Dict[str, Callable] = {}

    def register_tool(self, name: str, func: Callable):
        """Register an analytical, ML, or database tool."""
        self.tools[name] = func

    def call_grok(self, prompt: str) -> Optional[str]:
        """Invoke xAI Grok REST API if configured."""
        if not ENABLE_GROK:
            return None
        try:
            headers = {
                "Authorization": f"Bearer {GROK_API_KEY}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": GROK_MODEL,
                "messages": [
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.2,
            }
            resp = requests.post("https://api.x.ai/v1/chat/completions", json=payload, headers=headers, timeout=12)
            if resp.status_code == 200:
                data = resp.json()
                return data["choices"][0]["message"]["content"]
        except Exception:
            return None
        return None

    def call_gemini(self, prompt: str) -> Optional[str]:
        """Invoke Gemini REST API if configured."""
        if not ENABLE_GEMINI:
            return None
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
            payload = {
                "contents": [
                    {
                        "parts": [
                            {"text": f"{self.system_prompt}\n\n{prompt}"}
                        ]
                    }
                ]
            }
            resp = requests.post(url, json=payload, timeout=12)
            if resp.status_code == 200:
                data = resp.json()
                return data["candidates"][0]["content"]["parts"][0]["text"]
        except Exception:
            return None
        return None

    def call_llm(self, prompt: str) -> Optional[str]:
        """Invoke active LLM provider (Grok if configured, else Gemini, else None)."""
        if ENABLE_GROK:
            ans = self.call_grok(prompt)
            if ans:
                return ans
        if ENABLE_GEMINI:
            ans = self.call_gemini(prompt)
            if ans:
                return ans
        return None

    def format_structured_response(
        self,
        facts: List[str],
        predictions: List[str],
        recommendations: List[str],
        evidence: List[str],
        raw_context: Dict[str, Any] = None,
        notes: str = "",
    ) -> Dict[str, Any]:
        """
        Structure agent responses into distinct, auditable sections:
        FACTS, PREDICTIONS, RECOMMENDATIONS, EVIDENCE.
        """
        return {
            "agent": self.agent_name,
            "role": self.role,
            "facts": facts,
            "predictions": predictions,
            "recommendations": recommendations,
            "evidence": evidence,
            "notes": notes,
            "raw_context": raw_context or {},
        }
