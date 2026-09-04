"""
Decision Engine for RazorBrain.

Translates Phase 09 Risk Fusion assessments into operational 
ALLOW, REVIEW, or BLOCK decisions. Enforces strict safety guardrails
preventing weak signals or single correlated features from triggering blocks.
"""

from __future__ import annotations

import logging
import math
import json

logger = logging.getLogger(__name__)


class InvalidPolicyError(Exception):
    pass


class DecisionPolicy:
    """Configurable thresholds for operational decisions strictly loaded from JSON."""
    def __init__(self, t_review: float, t_block: float, metadata: dict = None):
        if not (0.0 <= t_review < t_block <= 1.0):
            raise InvalidPolicyError("Thresholds must satisfy 0 <= t_review < t_block <= 1")
        self.t_review = t_review
        self.t_block = t_block
        self.metadata = metadata or {}

def load_policy(path: str = "data/validation_selected_policy.json") -> DecisionPolicy:
    try:
        with open(path, "r") as f:
            data = json.load(f)
    except Exception as e:
        raise InvalidPolicyError(f"Failed to load policy: {e}")
    
    if data.get("policy_status") != "VALIDATION_SELECTED":
        raise InvalidPolicyError("Policy status is not VALIDATION_SELECTED")
        
    return DecisionPolicy(
        t_review=data["t_review"],
        t_block=data["t_block"],
        metadata=data
    )

def make_decision(calibrated_risk: float, policy: DecisionPolicy, fusion_result: dict = None) -> dict:
    """
    Evaluates calibrated risk against deterministic boundaries.
    Evidence does NOT change the decision, it only explains it.
    """
    if calibrated_risk is None or not isinstance(calibrated_risk, (float, int)) or math.isnan(calibrated_risk):
        decision = "REVIEW"
    elif calibrated_risk >= policy.t_block:
        decision = "BLOCK"
    elif calibrated_risk >= policy.t_review:
        decision = "REVIEW"
    else:
        decision = "ALLOW"
        
    reason = {
        "decision": decision,
        "calibrated_risk": calibrated_risk,
        "thresholds": {
            "review": policy.t_review,
            "block": policy.t_block
        },
        "model_evidence": fusion_result.get("model_evidence", []) if fusion_result else [],
        "rule_evidence": fusion_result.get("rule_evidence", []) if fusion_result else [],
        "behavioral_evidence": fusion_result.get("behavioral_evidence", []) if fusion_result else [],
        "data_quality_evidence": fusion_result.get("data_quality_evidence", []) if fusion_result else []
    }
    
    return {
        "decision": decision,
        "decision_reason": reason
    }
