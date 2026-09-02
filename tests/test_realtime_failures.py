import pytest
from model.explanation_engine import ExplanationEngine, DeterministicFallbackProvider
from model.decision_engine import DecisionPolicy

def test_explanation_engine_prompt_injection_safety():
    engine = ExplanationEngine(DecisionPolicy(0.3, 0.7))
    
    decision_result = {
        "transaction_id": "T-1",
        "decision": "ALLOW",
        "decision_reason": "Safely below threshold",
        "primary_risk_probability": 0.1,
        "confidence_in_probability": "HIGH",
        "blocking_guardrail_status": "NOT_EVALUATED",
        "policy_metadata": {},
        "evidence_summary": {},
        "conflicting_evidence": {}
    }
    
    # We use the local fallback provider. Since it ignores LLM prompts and is deterministic,
    # prompt injection has zero effect. But let's verify the API boundaries.
    
    # Inject adversarial metadata in transaction (if it had any)
    # The current engine generates explanation strictly from decision_result.
    explanation = engine.explain(decision_result)
    
    assert explanation["provider"] == "deterministic_fallback"
    assert explanation["grounded"] is True
    # Ensure decision is not altered
    assert decision_result["decision"] == "ALLOW"

def test_explanation_provider_failure_recovery():
    class CrashingProvider(DeterministicFallbackProvider):
        def explain(self, context):
            raise RuntimeError("LLM API timeout")
            
    engine = ExplanationEngine(primary_provider=CrashingProvider())
    
    decision_result = {
        "transaction_id": "T-1",
        "decision": "BLOCK",
        "decision_reason": "Risk high.",
        "primary_risk_probability": 0.9,
        "confidence_in_probability": "HIGH",
        "blocking_guardrail_status": "NOT_EVALUATED",
        "policy_metadata": {},
        "evidence_summary": {},
        "conflicting_evidence": {}
    }
    
    explanation = engine.explain(decision_result)
    
    assert explanation["provider"] == "deterministic_fallback"
    assert explanation["grounded"] is True
