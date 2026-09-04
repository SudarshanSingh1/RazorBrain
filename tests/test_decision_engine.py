import pytest
import math
from model.decision_engine import DecisionPolicy, load_policy, make_decision, InvalidPolicyError
from model.model_artifact import load_model_artifact, ModelUnavailableError, InvalidModelArtifactError

def test_calibrated_artifact_loads_successfully():
    artifact = load_model_artifact("data/model_c_calibrated.joblib")
    assert "base_model_artifact" in artifact
    assert "calibrator" in artifact

def test_missing_calibrated_artifact_fails():
    with pytest.raises(ModelUnavailableError):
        load_model_artifact("data/nonexistent.joblib")

def test_policy_loads_correctly():
    policy = load_policy("data/validation_selected_policy.json")
    assert policy.t_review == pytest.approx(0.1258, abs=1e-3)
    assert policy.t_block == pytest.approx(0.3125, abs=1e-3)
    assert policy.metadata["policy_status"] == "VALIDATION_SELECTED"

def test_invalid_policy_fails(tmp_path):
    p = tmp_path / "invalid.json"
    p.write_text('{"t_review": 0.5, "t_block": 0.3, "policy_status": "VALIDATION_SELECTED"}')
    with pytest.raises(InvalidPolicyError):
        load_policy(str(p))

def test_invalid_policy_status_fails(tmp_path):
    p = tmp_path / "invalid.json"
    p.write_text('{"t_review": 0.2, "t_block": 0.3, "policy_status": "DRAFT"}')
    with pytest.raises(InvalidPolicyError):
        load_policy(str(p))

def test_decision_boundaries():
    policy = DecisionPolicy(t_review=0.2, t_block=0.8)
    
    # Below review
    assert make_decision(0.0, policy)["decision"] == "ALLOW"
    assert make_decision(0.1999, policy)["decision"] == "ALLOW"
    
    # Exactly review
    assert make_decision(0.2, policy)["decision"] == "REVIEW"
    
    # Between
    assert make_decision(0.5, policy)["decision"] == "REVIEW"
    
    # Exactly block
    assert make_decision(0.8, policy)["decision"] == "BLOCK"
    
    # Above block
    assert make_decision(1.0, policy)["decision"] == "BLOCK"

def test_invalid_probability_defaults_to_review():
    policy = DecisionPolicy(t_review=0.2, t_block=0.8)
    assert make_decision(None, policy)["decision"] == "REVIEW"
    assert make_decision(float("nan"), policy)["decision"] == "REVIEW"

def test_decision_reason_contains_evidence():
    policy = DecisionPolicy(t_review=0.2, t_block=0.8)
    
    fusion_result = {
        "model_evidence": [{"source": "MODEL", "code": "FEAT1", "feature": "amount", "value": 100, "direction": "INCREASES_RISK", "description": "High amount", "available_at_scoring": True}],
        "behavioral_evidence": []
    }
    
    res = make_decision(0.5, policy, fusion_result)
    assert res["decision"] == "REVIEW"
    assert res["decision_reason"]["model_evidence"][0]["code"] == "FEAT1"
