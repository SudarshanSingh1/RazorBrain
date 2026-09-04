import numpy as np
from typing import Dict, Any

from model.decision_engine import DecisionPolicy, make_decision

def score_transaction(
    features: np.ndarray,
    artifact: Dict[str, Any],
    policy: DecisionPolicy,
    evidence: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Demonstrates the strict scoring contract.
    """
    
    # 1. Base model score (raw)
    base_model = artifact["base_model_artifact"]["model_artifact"]
    raw_probs = base_model.predict_proba(features)
    raw_model_score = float(raw_probs[0, 1])
    
    # 2. Calibrated risk
    calibrator = artifact["calibrator"]
    calib_probs = calibrator.predict_proba(features)
    calibrated_risk = float(calib_probs[0, 1])
    
    # 3. Evidence fusion (Read-Only respect to model risk)
    # Evidence is provided by external rule/behavioral engines.
    
    # 4. Deterministic decision
    decision_result = make_decision(calibrated_risk, policy, evidence)
    
    return {
        "raw_model_score": raw_model_score,
        "calibrated_risk": calibrated_risk,
        "decision": decision_result["decision"],
        "decision_reason": decision_result["decision_reason"]
    }

def format_evidence_item(
    source: str, 
    code: str, 
    feature: str, 
    value: Any, 
    direction: str, 
    description: str,
    available_at_scoring: bool = True
) -> dict:
    if direction not in ["INCREASES_RISK", "DECREASES_RISK", "INFORMATIONAL"]:
        raise ValueError("Invalid direction")
        
    return {
        "source": source,
        "code": code,
        "feature": feature,
        "value": value,
        "direction": direction,
        "description": description,
        "available_at_scoring": available_at_scoring
    }
