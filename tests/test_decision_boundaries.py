import pytest
from model.decision_engine import DecisionPolicy, make_decision

@pytest.fixture
def policy():
    return DecisionPolicy(allow_threshold=0.3, block_threshold=0.7)

def test_probability_boundaries(policy):
    evidence = {"triggered_rules": [{"rule_id": "velocity_new_device", "severity": "HIGH"}]}
    
    # Just below allow -> ALLOW
    res1 = make_decision({"fusion_summary": {"primary_risk_probability": 0.29, "confidence_in_probability": "HIGH"}, "rule_evidence": evidence}, policy)
    assert res1["decision"] == "ALLOW"
    
    # Exactly at allow -> REVIEW
    res2 = make_decision({"fusion_summary": {"primary_risk_probability": 0.30, "confidence_in_probability": "HIGH"}, "rule_evidence": evidence}, policy)
    assert res2["decision"] == "REVIEW"
    
    # Just above allow -> REVIEW
    res3 = make_decision({"fusion_summary": {"primary_risk_probability": 0.31, "confidence_in_probability": "HIGH"}, "rule_evidence": evidence}, policy)
    assert res3["decision"] == "REVIEW"
    
    # Just below block -> REVIEW
    res4 = make_decision({"fusion_summary": {"primary_risk_probability": 0.69, "confidence_in_probability": "HIGH"}, "rule_evidence": evidence}, policy)
    assert res4["decision"] == "REVIEW"
    
    # Exactly at block -> BLOCK
    res5 = make_decision({"fusion_summary": {"primary_risk_probability": 0.70, "confidence_in_probability": "HIGH"}, "rule_evidence": evidence}, policy)
    assert res5["decision"] == "BLOCK"

    # Just above block -> BLOCK
    res6 = make_decision({"fusion_summary": {"primary_risk_probability": 0.71, "confidence_in_probability": "HIGH"}, "rule_evidence": evidence}, policy)
    assert res6["decision"] == "BLOCK"

def test_single_signal_safety(policy):
    fusion = {
        "fusion_summary": {"primary_risk_probability": 0.10, "confidence_in_probability": "HIGH"},
        "evidence_conflict": {"has_conflict": True},
        "rule_evidence": {
            "triggered_rules": [
                {"rule_id": "velocity_new_device", "severity": "HIGH"}
            ]
        }
    }
    res = make_decision(fusion, policy)
    # Conflict + Independent blocking evidence -> Escalate to REVIEW
    assert res["decision"] == "REVIEW"

def test_blocking_rule_overrides_allow(policy):
    fusion = {
        "fusion_summary": {"primary_risk_probability": 0.10, "confidence_in_probability": "HIGH"},
        "evidence_conflict": {"has_conflict": True},
        "rule_evidence": {
            "triggered_rules": [
                {"rule_id": "velocity_new_device", "severity": "HIGH"}
            ]
        }
    }
    res = make_decision(fusion, policy)
    # It cannot escalate an ALLOW straight to BLOCK. It goes to REVIEW.
    assert res["decision"] == "REVIEW"

def test_missing_confidence_demotes_block(policy):
    fusion = {
        "fusion_summary": {"primary_risk_probability": 0.85, "confidence_in_probability": "LOW"},
    }
    res = make_decision(fusion, policy)
    assert res["decision"] == "REVIEW"
    assert "escalate to review" in res["decision_reason"].lower()

