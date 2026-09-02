"""
Tests for AI Explanation Layer.
Ensures explanations are read-only, securely fallback, and strictly grounded.
"""

import pytest
from model.explanation_engine import (
    ExplanationEngine, 
    DeterministicFallbackProvider,
    LocalLLMProvider,
    ExplanationProvider,
    ProviderUnavailableError,
    ExplanationValidationError
)

@pytest.fixture
def sample_decision():
    return {
        "transaction_id": "txn_123",
        "decision": "REVIEW",
        "primary_risk_probability": 0.15,
        "confidence_in_probability": "HIGH",
        "decision_reason": "Risk falls within review region.",
        "evidence_summary": {
            "rule_evidence": {
                "triggered_rules": [
                    {"rule_id": "velocity_new_device", "severity": "HIGH"}
                ]
            }
        },
        "model_evidence": {
            "top_positive_contributors": [
                {"feature": "txns_last_24h", "shap_contribution": 0.5}
            ]
        }
    }


def test_deterministic_fallback(sample_decision):
    engine = ExplanationEngine()
    result = engine.explain(sample_decision)
    
    assert result["decision"] == "REVIEW"
    assert result["provider"] == "deterministic_fallback"
    assert result["grounded"] is True
    assert "0.1500" in result["explanation"]
    assert "velocity_new_device" in result["explanation"]


def test_local_llm_unavailable_fallback(sample_decision):
    # LLM without endpoint fails fast
    engine = ExplanationEngine(primary_provider=LocalLLMProvider(endpoint_url=None))
    result = engine.explain(sample_decision)
    
    assert result["provider"] == "deterministic_fallback"


class MaliciousProvider(ExplanationProvider):
    def explain(self, decision_result):
        # Attempts to override the decision!
        return {
            "transaction_id": "txn_123",
            "decision": "BLOCK",  # Changed from REVIEW!
            "explanation": "I decided to block this.",
            "key_factors": [],
            "evidence_references": [],
            "limitations": [],
            "provider": "malicious_llm",
            "grounded": False
        }


def test_decision_preservation_validation(sample_decision):
    engine = ExplanationEngine(primary_provider=MaliciousProvider())
    result = engine.explain(sample_decision)
    
    # Engine must catch the modified decision, reject it, and return the fallback
    assert result["decision"] == "REVIEW"
    assert result["provider"] == "deterministic_fallback"


class HallucinatingProvider(ExplanationProvider):
    def explain(self, decision_result):
        # Attempts to invent rules
        return {
            "transaction_id": "txn_123",
            "decision": "REVIEW",
            "explanation": "Blocked due to fake_rule.",
            "key_factors": [],
            "evidence_references": ["fake_rule_that_does_not_exist"],
            "limitations": [],
            "provider": "hallucinating_llm",
            "grounded": True
        }


def test_rule_hallucination_validation(sample_decision):
    engine = ExplanationEngine(primary_provider=HallucinatingProvider())
    result = engine.explain(sample_decision)
    
    # Validation should catch 'fake_rule_that_does_not_exist' and fallback
    assert result["provider"] == "deterministic_fallback"


def test_missing_evidence(sample_decision):
    del sample_decision["evidence_summary"]
    del sample_decision["model_evidence"]
    sample_decision["primary_risk_probability"] = None
    
    engine = ExplanationEngine()
    result = engine.explain(sample_decision)
    
    assert "unavailable" in result["explanation"]
    assert result["provider"] == "deterministic_fallback"
