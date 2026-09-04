import pytest
import numpy as np
from model.model_artifact import load_model_artifact
from model.decision_engine import load_policy
from model.scoring_contract import score_transaction, format_evidence_item

@pytest.fixture(scope="module")
def artifacts():
    return load_model_artifact("data/model_c_calibrated.joblib")

@pytest.fixture(scope="module")
def policy():
    return load_policy("data/validation_selected_policy.json")

def test_raw_score_and_calibrated_risk_are_separate(artifacts, policy):
    # Dummy features (438 is dimension of Model C)
    X = np.zeros((1, 438))
    res = score_transaction(X, artifacts, policy, {})
    assert "raw_model_score" in res
    assert "calibrated_risk" in res
    # They should generally be different
    assert res["raw_model_score"] != res["calibrated_risk"]

def test_calibrated_risk_in_bounds(artifacts, policy):
    X = np.zeros((1, 438))
    res = score_transaction(X, artifacts, policy, {})
    assert 0.0 <= res["calibrated_risk"] <= 1.0

def test_evidence_format():
    ev = format_evidence_item(
        source="BEHAVIOR",
        code="TXN_VELOCITY",
        feature="txns_last_24h",
        value=50,
        direction="INCREASES_RISK",
        description="Abnormally high transaction count"
    )
    assert ev["source"] == "BEHAVIOR"
    
def test_unavailable_history_representation():
    ev = format_evidence_item(
        source="DATA_QUALITY",
        code="MISSING_HISTORY",
        feature="txns_last_24h",
        value=None,
        direction="INFORMATIONAL",
        description="History unavailable at scoring time",
        available_at_scoring=False
    )
    assert ev["available_at_scoring"] is False

def test_evidence_cannot_mutate_model_risk(artifacts, policy):
    X = np.zeros((1, 438))
    evidence = {
        "rule_evidence": [
            format_evidence_item("RULE", "FEAT", "X", 1, "INCREASES_RISK", "DESC")
        ]
    }
    res_with = score_transaction(X, artifacts, policy, evidence)
    res_without = score_transaction(X, artifacts, policy, {})
    
    assert res_with["calibrated_risk"] == res_without["calibrated_risk"]

def test_decision_reason_is_deterministic(artifacts, policy):
    X = np.zeros((1, 438))
    res1 = score_transaction(X, artifacts, policy, {})
    res2 = score_transaction(X, artifacts, policy, {})
    assert res1["decision_reason"] == res2["decision_reason"]

def test_no_future_labels_enter_scoring(artifacts, policy):
    X = np.zeros((1, 438))
    res = score_transaction(X, artifacts, policy, {})
    reason = str(res["decision_reason"]).lower()
    assert "is_fraud" not in reason
    assert "fraud_label" not in reason

def test_model_does_not_retrain():
    # Model is preloaded, predict_proba is called, fit() on FrozenEstimator just returns self without training
    artifacts = load_model_artifact("data/model_c_calibrated.joblib")
    calibrator = artifacts["calibrator"]
    assert calibrator.estimator.fit(np.zeros((1, 438)), np.zeros(1)) is calibrator.estimator

def test_mutually_exclusive_decisions(artifacts, policy):
    X = np.zeros((1, 438))
    res = score_transaction(X, artifacts, policy, {})
    assert res["decision"] in ["ALLOW", "REVIEW", "BLOCK"]
