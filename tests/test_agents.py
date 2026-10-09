"""
Tests for AI Agents and RAG Knowledge Retrieval in MediNexus AI.
"""

import pytest
from src.agents.medicare_agent import MediCareAgent
from src.agents.healthanalyst_agent import HealthAnalystAgent
from src.agents.pharmalab_agent import PharmaLabAgent
from src.rag.document_loader import load_knowledge_documents
from src.rag.chunker import chunk_all_documents
from src.rag.retriever import retrieve_context
from src.rag.knowledge_base import generate_grounded_answer


def test_rag_document_loader_and_chunker():
    """Verify synthetic policy documents load and chunk properly."""
    docs = load_knowledge_documents()
    assert len(docs) >= 5

    chunks = chunk_all_documents(docs)
    assert len(chunks) >= len(docs)

    # Verify chunk structure
    first_chk = chunks[0]
    assert "chunk_id" in first_chk
    assert "title" in first_chk
    assert "text" in first_chk


def test_rag_retrieval_and_citations():
    """Verify semantic retrieval returns relevant documents with citations."""
    hits = retrieve_context("What is the discharge policy for high risk patients?", top_k=2)
    assert len(hits) > 0
    assert "title" in hits[0]
    assert "filename" in hits[0]
    assert hits[0]["score"] > 0.0


def test_agents_structured_output():
    """Verify agents separate response into Facts, Predictions, Recommendations."""
    agent = HealthAnalystAgent()
    resp = agent.process_query("Why did readmission increase?", username="test_admin")

    assert "facts" in resp
    assert "predictions" in resp
    assert "recommendations" in resp
    assert "evidence" in resp
    assert resp["agent"] == "HealthAnalyst Agent"
