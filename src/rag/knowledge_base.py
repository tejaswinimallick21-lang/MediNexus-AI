"""
Grounded Knowledge Synthesis Engine for MediNexus AI RAG.
Synthesizes retrieved healthcare policy and clinical guideline passages into cited answers.
"""

from typing import Dict, Any, Optional, List
import os
import time
import requests

from config.settings import (
    GEMINI_API_KEY,
    ENABLE_GEMINI,
    GROK_API_KEY,
    ENABLE_GROK,
    GROK_MODEL,
    ACTIVE_LLM_PROVIDER,
)
from src.rag.retriever import retrieve_context


def generate_grounded_answer(query: str, category: Optional[str] = None, min_confidence: float = 0.12) -> Dict[str, Any]:
    """
    Retrieve relevant knowledge chunks and synthesize a grounded response with source citations.
    Supports Grok (xAI), Gemini (Google), and deterministic local fallback.
    Enforces a clinical safety confidence threshold (min_confidence) to safely reject out-of-scope queries.
    Records high-precision latency telemetry (retrieval_ms, generation_ms, total_ms).
    """
    t_start = time.perf_counter()
    hits = retrieve_context(query, top_k=3, category=category)
    t_ret = time.perf_counter()

    if not hits or hits[0]["score"] < min_confidence:
        t_end = time.perf_counter()
        return {
            "query": query,
            "answer": (
                "No authoritative institutional healthcare policies or clinical guidelines were found in the "
                "MediNexus knowledge base for this query with sufficient clinical confidence. To protect patient "
                "safety and prevent clinical hallucinations, MediNexus AI safely refuses to answer unsupported queries."
            ),
            "citations": [],
            "grounded": False,
            "out_of_scope": True,
            "safe_refusal": True,
            "engine": "Clinical Safety Guardrail",
            "latency_metrics": {
                "retrieval_ms": round((t_ret - t_start) * 1000, 2),
                "generation_ms": round((t_end - t_ret) * 1000, 2),
                "total_ms": round((t_end - t_start) * 1000, 2),
            },
            "top_relevance_score": hits[0]["score"] if hits else 0.0,
        }

    # Format context passages
    context_text = "\n\n---\n\n".join(
        [f"Source: [{h['title']} ({h['filename']})]\n{h['text']}" for h in hits]
    )

    citations = [
        {"title": h["title"], "filename": h["filename"], "category": h["category"], "relevance": h["score"]}
        for h in hits
    ]

    rag_prompt = (
        f"You are a clinical decision-support knowledge assistant. "
        f"Answer the user query strictly using the provided institutional healthcare policy documents. "
        f"Cite the source document title. "
        f"If the answer cannot be determined from the text, state that clearly.\n\n"
        f"DOCUMENTS:\n{context_text}\n\n"
        f"USER QUERY: {query}"
    )

    # 1. Try xAI Grok API if configured
    if ENABLE_GROK:
        try:
            headers = {
                "Authorization": f"Bearer {GROK_API_KEY}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": GROK_MODEL,
                "messages": [
                    {"role": "system", "content": "You are a clinical decision-support knowledge assistant."},
                    {"role": "user", "content": rag_prompt},
                ],
                "temperature": 0.2,
            }
            resp = requests.post("https://api.x.ai/v1/chat/completions", json=payload, headers=headers, timeout=12)
            if resp.status_code == 200:
                data = resp.json()
                text = data["choices"][0]["message"]["content"]
                t_end = time.perf_counter()
                return {
                    "query": query,
                    "answer": text,
                    "citations": citations,
                    "grounded": True,
                    "engine": f"Grok ({GROK_MODEL}) Grounded RAG",
                    "latency_metrics": {
                        "retrieval_ms": round((t_ret - t_start) * 1000, 2),
                        "generation_ms": round((t_end - t_ret) * 1000, 2),
                        "total_ms": round((t_end - t_start) * 1000, 2),
                    },
                    "top_relevance_score": hits[0]["score"] if hits else 0.0,
                }
        except Exception:
            pass  # Fall through to Gemini or local fallback

    # 2. Try Gemini API if key is available
    if ENABLE_GEMINI:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
            payload = {
                "contents": [{"parts": [{"text": rag_prompt}]}]
            }
            resp = requests.post(url, json=payload, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"]
                t_end = time.perf_counter()
                return {
                    "query": query,
                    "answer": text,
                    "citations": citations,
                    "grounded": True,
                    "engine": "Gemini-1.5-Flash (Grounded RAG)",
                    "latency_metrics": {
                        "retrieval_ms": round((t_ret - t_start) * 1000, 2),
                        "generation_ms": round((t_end - t_ret) * 1000, 2),
                        "total_ms": round((t_end - t_start) * 1000, 2),
                    },
                    "top_relevance_score": hits[0]["score"] if hits else 0.0,
                }
        except Exception:
            pass  # Fall through to deterministic local synthesis

    # Deterministic local knowledge synthesis
    top_hit = hits[0]
    local_synthesis = (
        f"According to institutional documentation in **{top_hit['title']}** (*{top_hit['filename']}*):\n\n"
        f"> {top_hit['text'][:350]}...\n\n"
        f"**Key Operational Takeaways:**\n"
        f"- Reference Guideline ID: `{top_hit['filename']}`\n"
        f"- Target Department: `{top_hit['category']}`\n"
        f"- Relevance Match Score: `{top_hit['score'] * 100:.1f}%`"
    )

    t_end = time.perf_counter()
    return {
        "query": query,
        "answer": local_synthesis,
        "citations": citations,
        "grounded": True,
        "engine": "MediNexus Local Grounded Retriever",
        "latency_metrics": {
            "retrieval_ms": round((t_ret - t_start) * 1000, 2),
            "generation_ms": round((t_end - t_ret) * 1000, 2),
            "total_ms": round((t_end - t_start) * 1000, 2),
        },
        "top_relevance_score": hits[0]["score"] if hits else 0.0,
    }
