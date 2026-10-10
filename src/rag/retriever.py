"""
Knowledge Base Retriever for MediNexus AI: hybrid (BM25 + embeddings) search over the policy library.
"""

from typing import Any, Dict, List, Optional

from src.rag.hybrid import get_index


def retrieve_context(query: str, top_k: int = 3, category: Optional[str] = None, mode: str = "hybrid") -> List[Dict[str, Any]]:
    """Top-k relevant sections with citation metadata; an empty list means nothing relevant was found."""
    hits = get_index().search(query, k=top_k * 3 if category else top_k, mode=mode)
    out = []
    for h in hits:
        d = h.as_dict()
        if category and category.lower() not in d["category"].lower():
            continue
        out.append(d)
        if len(out) >= top_k:
            break
    return out


def get_vector_store():  # kept for callers of the old API
    return get_index()
