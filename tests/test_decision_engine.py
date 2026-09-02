"""
Tests for Decision Engine module.
"""

import pytest
import math
from model.decision_engine import DecisionPolicy, make_decision


@pytest.fixture
def policy():
    return DecisionPolicy(allow_threshold=0.05, block_threshold=0.80)


@pytest.fixture
def base_fusion():
    return {
        "transaction_id": "test_txn",
        "fusion_summary": {
            "primary_risk_probability": 0.02,
            "contextual_severity": "NONE",
            "confidence_in_probability": "HIGH"
        },
        "rule_evidence": {
            "triggered_rules": [],
            "highest_severity": "NONE"
        },
        "evidence_conflict": {
            "has_conflict": False,
            "reason": None
        }
    }


def test_ordinary_low_risk(policy, base_fusion):
    base_fusion["fusion_summary"]["primary_risk_probability"] = 0.02
    res = make_decision(base_fusion, policy)
    assert res["decision"] == "ALLOW"


def test_borderline_probability(policy, base_fusion):
    base_fusion["fusion_summary"]["primary_risk_probability"] = 0.50
    res = make_decision(base_fusion, policy)
    assert res["decision"] == "REVIEW"


def test_high_prob_with_no_independent_evidence(policy, base_fusion):
    # Guardrail test
    base_fusion["fusion_summary"]["primary_risk_probability"] = 0.90
    base_fusion["rule_evidence"]["triggered_rules"] = [
        {"rule_id": "repeated_fraud", "severity": "HIGH"}
    ]
    res = make_decision(base_fusion, policy)
    assert res["decision"] == "REVIEW"
    assert res["blocking_guardrail_status"] == "FAILED_LACK_OF_INDEPENDENT_EVIDENCE"


def test_high_prob_with_independent_evidence(policy, base_fusion):
    # Safe block test
    base_fusion["fusion_summary"]["primary_risk_probability"] = 0.90
    base_fusion["rule_evidence"]["triggered_rules"] = [
        {"rule_id": "repeated_fraud", "severity": "HIGH"},
        {"rule_id": "velocity_new_device", "severity": "HIGH"}
    ]
    res = make_decision(base_fusion, policy)
    assert res["decision"] == "BLOCK"
    assert res["blocking_guardrail_status"] == "PASSED"


def test_high_prob_low_confidence(policy, base_fusion):
    base_fusion["fusion_summary"]["primary_risk_probability"] = 0.90
    base_fusion["fusion_summary"]["confidence_in_probability"] = "LOW"
    base_fusion["rule_evidence"]["triggered_rules"] = [
        {"rule_id": "velocity_new_device", "severity": "HIGH"}
    ]
    res = make_decision(base_fusion, policy)
    assert res["decision"] == "REVIEW"
    assert res["blocking_guardrail_status"] == "FAILED_LOW_CONFIDENCE"


def test_missing_probability(policy, base_fusion):
    base_fusion["fusion_summary"]["primary_risk_probability"] = None
    res = make_decision(base_fusion, policy)
    assert res["decision"] == "REVIEW"
    assert "Invalid or unavailable probability" in res["decision_reason"]


def test_invalid_probability_nan(policy, base_fusion):
    base_fusion["fusion_summary"]["primary_risk_probability"] = float("nan")
    res = make_decision(base_fusion, policy)
    assert res["decision"] == "REVIEW"


def test_invalid_probability_bounds(policy, base_fusion):
    base_fusion["fusion_summary"]["primary_risk_probability"] = 1.05
    res = make_decision(base_fusion, policy)
    assert res["decision"] == "REVIEW"


def test_low_prob_with_conflict(policy, base_fusion):
    base_fusion["fusion_summary"]["primary_risk_probability"] = 0.02
    base_fusion["evidence_conflict"] = {"has_conflict": True, "reason": "Conflict"}
    base_fusion["rule_evidence"]["triggered_rules"] = [
        {"rule_id": "velocity_new_device", "severity": "HIGH"}
    ]
    res = make_decision(base_fusion, policy)
    assert res["decision"] == "REVIEW"
    assert "conflict detected" in res["decision_reason"]


def test_extreme_amount_only(policy, base_fusion):
    base_fusion["fusion_summary"]["primary_risk_probability"] = 0.90
    base_fusion["rule_evidence"]["triggered_rules"] = [
        {"rule_id": "extreme_amount_single_signal", "severity": "LOW"}
    ]
    res = make_decision(base_fusion, policy)
    assert res["decision"] == "REVIEW"  # Lacks independent MEDIUM/HIGH evidence


def test_low_prob_with_overridden_conflict(policy, base_fusion):
    base_fusion["fusion_summary"]["primary_risk_probability"] = 0.02
    base_fusion["evidence_conflict"] = {"has_conflict": True, "reason": "Conflict"}
    base_fusion["rule_evidence"]["triggered_rules"] = [
        {"rule_id": "repeated_fraud", "severity": "HIGH"}
    ]
    res = make_decision(base_fusion, policy)
    assert res["decision"] == "ALLOW"
    assert "Conflict overridden" in res["decision_reason"]


def test_policy_validation():
    with pytest.raises(ValueError):
        DecisionPolicy(allow_threshold=0.80, block_threshold=0.20)
