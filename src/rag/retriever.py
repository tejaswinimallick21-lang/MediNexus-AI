"""
Knowledge Base Retriever for MediNexus AI.
"""

from typing import List, Dict, Any, Optional
from src.rag.document_loader import load_knowledge_documents
from src.rag.chunker import chunk_all_documents
from src.rag.embeddings import LocalVectorStore

_VECTOR_STORE: Optional[LocalVectorStore] = None


def get_vector_store() -> LocalVectorStore:
    """Initialize or return the singleton vector store."""
    global _VECTOR_STORE
    if _VECTOR_STORE is None or not _VECTOR_STORE.is_indexed:
        docs = load_knowledge_documents()
        chunks = chunk_all_documents(docs)
        store = LocalVectorStore()
        store.build_index(chunks)
        _VECTOR_STORE = store
    return _VECTOR_STORE


def retrieve_context(query: str, top_k: int = 3, category: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Retrieve top-k relevant knowledge chunks for a query with citation metadata.
    """
    store = get_vector_store()
    results = store.search(query, top_k=top_k * 2)

    hits = []
    for chunk, score in results:
        if category and category.lower() not in chunk["category"].lower():
            continue
        hits.append({
            "chunk_id": chunk["chunk_id"],
            "title": chunk["title"],
            "filename": chunk["filename"],
            "category": chunk["category"],
            "text": chunk["text"],
            "score": score,
        })
        if len(hits) >= top_k:
            break

    return hits
