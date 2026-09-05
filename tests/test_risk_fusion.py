"""
Test suite for the Hybrid Risk Fusion layer.
Tests monotonic intervention escalation, conflict detection, and evidence separation.
"""

import pytest
from model.serving_rule_engine import RuleResult
from model.serving_risk_fusion import HybridRiskFusionEngine, HybridRiskAssessment


@pytest.fixture
def fusion_engine():
    return HybridRiskFusionEngine(fusion_version="1.0")


def make_dummy_rule(rule_id: str, severity: str, priority: int = 100) -> RuleResult:
    return RuleResult(
        rule_id=rule_id,
        triggered=True,
        severity=severity,
        priority=priority,
        reason_code=rule_id,
        description=f"Rule {rule_id} triggered",
        observed_values={"test": True},
        policy_version="1.0",
    )


def test_fusion_ml_approve_with_no_rules(fusion_engine):
    assessment = fusion_engine.fuse(
        fraud_probability=0.05,
        model_risk_level="LOW",
        base_decision="APPROVE",
        triggered_rules=[],
    )
    assert assessment.recommended_minimum_decision == "APPROVE"
    assert assessment.highest_rule_severity == "NONE"
    assert assessment.has_conflict is False
    assert assessment.fraud_probability == 0.05


def test_fusion_ml_approve_escalated_by_review_rule(fusion_engine):
    rules = [make_dummy_rule("HIGH_VALUE_TRANSACTION", "REVIEW")]
    assessment = fusion_engine.fuse(
        fraud_probability=0.08,
        model_risk_level="LOW",
        base_decision="APPROVE",
        triggered_rules=rules,
    )
    assert assessment.recommended_minimum_decision == "REVIEW"
    assert assessment.highest_rule_severity == "REVIEW"


def test_fusion_ml_review_escalated_by_step_up_rule(fusion_engine):
    rules = [make_dummy_rule("HIGH_VELOCITY_1H", "STEP_UP")]
    assessment = fusion_engine.fuse(
        fraud_probability=0.14,
        model_risk_level="MEDIUM",
        base_decision="REVIEW",
        triggered_rules=rules,
    )
    assert assessment.recommended_minimum_decision == "STEP_UP"


def test_fusion_cannot_downgrade_higher_base_decision(fusion_engine):
    # Base decision is STEP_UP, but rule recommends REVIEW -> must stay STEP_UP
    rules = [make_dummy_rule("HIGH_VALUE_TRANSACTION", "REVIEW")]
    assessment = fusion_engine.fuse(
        fraud_probability=0.18,
        model_risk_level="MEDIUM",
        base_decision="STEP_UP",
        triggered_rules=rules,
    )
    assert assessment.recommended_minimum_decision == "STEP_UP"


def test_fusion_ml_decline_remains_decline(fusion_engine):
    rules = [make_dummy_rule("ELEVATED_VELOCITY_24H", "REVIEW")]
    assessment = fusion_engine.fuse(
        fraud_probability=0.28,
        model_risk_level="HIGH",
        base_decision="DECLINE",
        triggered_rules=rules,
    )
    assert assessment.recommended_minimum_decision == "DECLINE"


def test_fusion_conflict_detection_low_prob_high_rule(fusion_engine):
    rules = [make_dummy_rule("HIGH_VELOCITY_1H", "STEP_UP")]
    assessment = fusion_engine.fuse(
        fraud_probability=0.03,
        model_risk_level="LOW",
        base_decision="APPROVE",
        triggered_rules=rules,
    )
    assert assessment.has_conflict is True
    assert "low probability" in assessment.conflict_reason.lower()


def test_fusion_conflict_detection_high_prob_no_rules(fusion_engine):
    assessment = fusion_engine.fuse(
        fraud_probability=0.35,
        model_risk_level="HIGH",
        base_decision="DECLINE",
        triggered_rules=[],
    )
    assert assessment.has_conflict is True
    assert "no deterministic operational rules" in assessment.conflict_reason.lower()


def test_fusion_to_dict_serialization(fusion_engine):
    rules = [make_dummy_rule("RESTRICTED_CARD_NETWORK", "DECLINE")]
    assessment = fusion_engine.fuse(
        fraud_probability=0.10,
        model_risk_level="LOW",
        base_decision="APPROVE",
        triggered_rules=rules,
    )
    d = assessment.to_dict()
    assert d["recommended_minimum_decision"] == "DECLINE"
    assert d["triggered_rules_count"] == 1
    assert isinstance(d["triggered_rules"], list)
    assert d["triggered_rules"][0]["rule_id"] == "RESTRICTED_CARD_NETWORK"
