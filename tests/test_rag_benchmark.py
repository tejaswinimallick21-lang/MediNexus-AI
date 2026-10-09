"""
Tests for Multi-Dimensional RAG Triad & Hallucination Auditor in MediNexus AI.
Asserts enterprise thresholds across:
1. Retrieval Accuracy & Ranking (Hit@1, Hit@3, MRR@3)
2. Context Relevance & Purity (%)
3. Clinical Faithfulness & Grounding Index (%)
4. Negative Rejection & Adversarial Robustness (%)
5. Latency SLAs & Percentile Profiling (P50, P90, P95)
"""

import pytest
from src.rag.evaluation import (
    run_rag_benchmark,
    evaluate_retrieval_query,
    evaluate_end_to_end_rag,
    compute_faithfulness,
    compute_context_relevance,
)
from src.rag.knowledge_base import generate_grounded_answer


def test_rag_retrieval_accuracy_benchmarks():
    """Verify that in-scope knowledge retrieval satisfies enterprise accuracy thresholds."""
    summary = run_rag_benchmark()

    # Accuracy benchmarks on in-scope clinical queries
    assert summary["hit_rate_at_1_percent"] >= 90.0, f"Hit@1 too low: {summary['hit_rate_at_1_percent']}%"
    assert summary["hit_rate_at_3_percent"] == 100.0, f"Hit@3 not 100%: {summary['hit_rate_at_3_percent']}%"
    assert summary["mrr_score"] >= 0.90, f"MRR too low: {summary['mrr_score']}"
    assert summary["citation_accuracy_percent"] == 100.0, f"Citation accuracy too low: {summary['citation_accuracy_percent']}%"


def test_rag_triad_quality_and_hallucination_guardrails():
    """Verify Context Relevance, Clinical Faithfulness, and Negative Rejection precision."""
    summary = run_rag_benchmark()

    # Multi-dimensional RAG Triad thresholds
    assert summary["context_relevance_percent"] >= 65.0, f"Context relevance too low: {summary['context_relevance_percent']}%"
    assert summary["faithfulness_percent"] >= 85.0, f"Faithfulness index too low: {summary['faithfulness_percent']}%"
    assert summary["concept_recall_percent"] >= 80.0, f"Concept recall too low: {summary['concept_recall_percent']}%"
    assert summary["out_of_scope_refusal_precision_percent"] == 100.0, (
        f"Failed to safely refuse adversarial queries: {summary['out_of_scope_refusal_precision_percent']}%"
    )


def test_adversarial_clinical_query_safe_refusal():
    """Verify that adversarial and ungrounded clinical queries trigger safe refusal."""
    adversarial_query = "What is the recommended weight-based chemotherapy dosing for pediatric osteosarcoma?"
    res = generate_grounded_answer(adversarial_query)

    assert res.get("out_of_scope") is True or res.get("safe_refusal") is True
    assert "refuses to answer unsupported queries" in res.get("answer", "") or "No authoritative institutional" in res.get("answer", "")
    assert len(res.get("citations", [])) == 0


def test_rag_latency_percentiles_and_slas():
    """Verify that RAG retrieval and synthesis satisfy real-time latency SLAs (< 50ms retrieval, < 100ms total)."""
    summary = run_rag_benchmark()

    # Latency percentiles
    ret_pct = summary["retrieval_latency_percentiles"]
    tot_pct = summary["total_latency_percentiles"]

    assert ret_pct["p50"] < 25.0, f"P50 retrieval latency exceeded 25ms: {ret_pct['p50']}ms"
    assert ret_pct["p95"] < 50.0, f"P95 retrieval latency exceeded 50ms: {ret_pct['p95']}ms"
    assert tot_pct["p50"] < 50.0, f"P50 total latency exceeded 50ms: {tot_pct['p50']}ms"
    assert tot_pct["p95"] < 100.0, f"P95 total latency exceeded 100ms: {tot_pct['p95']}ms"
