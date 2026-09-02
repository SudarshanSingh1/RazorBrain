"""
Decision Engine for RazorBrain.

Translates Phase 09 Risk Fusion assessments into operational 
ALLOW, REVIEW, or BLOCK decisions. Enforces strict safety guardrails
preventing weak signals or single correlated features from triggering blocks.
"""

from __future__ import annotations

import logging
from typing import Any
import math

logger = logging.getLogger(__name__)


class DecisionPolicy:
    """Configurable thresholds for operational decisions."""
    def __init__(self, allow_threshold: float, block_threshold: float):
        if not (0.0 <= allow_threshold <= block_threshold <= 1.0):
            raise ValueError("Thresholds must satisfy 0 <= allow <= block <= 1")
        self.allow_threshold = allow_threshold
        self.block_threshold = block_threshold


def _has_independent_blocking_evidence(rule_evidence: dict[str, Any]) -> bool:
    """
    Guardrail: BLOCK requires independent, non-correlated severe evidence.
    
    The `repeated_fraud` rule heavily correlates with model history features
    (e.g., `previous_fraud_count`). Triggering it is not 'independent' evidence.
    To safely block, there must be a MEDIUM or HIGH severity rule triggered
    that is NOT `repeated_fraud`.
    """
    triggered = rule_evidence.get("triggered_rules", [])
    for rule in triggered:
        sev = rule.get("severity")
        r_id = rule.get("rule_id")
        
        if sev in ["MEDIUM", "HIGH"] and r_id != "repeated_fraud":
            return True
            
    return False


def make_decision(fusion_result: dict[str, Any], policy: DecisionPolicy) -> dict[str, Any]:
    """
    Evaluate the fusion result against the decision policy and safety guardrails.
    Returns a structured decision result.
    """
    tid = fusion_result.get("transaction_id", "UNKNOWN")
    
    # 1. Extract Probability with extreme safety
    summary = fusion_result.get("fusion_summary", {})
    prob = summary.get("primary_risk_probability")
    
    # Base response template
    result = {
        "transaction_id": tid,
        "decision": "REVIEW",
        "decision_reason": "Default safety fallback.",
        "primary_risk_probability": prob,
        "confidence_in_probability": summary.get("confidence_in_probability", "UNKNOWN"),
        "blocking_guardrail_status": "NOT_EVALUATED",
        "policy_metadata": {
            "allow_threshold": policy.allow_threshold,
            "block_threshold": policy.block_threshold
        },
        "evidence_summary": summary,
        "conflicting_evidence": fusion_result.get("evidence_conflict", {})
    }
    
    # 2. Validate Probability
    if prob is None or not isinstance(prob, (float, int)) or math.isnan(prob) or not (0.0 <= prob <= 1.0):
        result["decision"] = "REVIEW"
        result["decision_reason"] = "Invalid or unavailable probability input. Failsafe to REVIEW."
        return result
        
    conf = summary.get("confidence_in_probability")
    
    # 3. Decision Logic
    if prob < policy.allow_threshold:
        # ALLOW PATH
        conflict = fusion_result.get("evidence_conflict", {}).get("has_conflict", False)
        
        if conflict:
            # Phase 09 flags conflicts when probability is low but contextual severity is HIGH.
            # However, because `repeated_fraud` triggers on 99% of validations, we must
            # prevent this single weak signal from escalating everything to REVIEW.
            if _has_independent_blocking_evidence(fusion_result.get("rule_evidence", {})):
                result["decision"] = "REVIEW"
                result["decision_reason"] = "Model risk is below ALLOW threshold, but severe independent evidence conflict detected. Escalate to REVIEW."
            else:
                result["decision"] = "ALLOW"
                result["decision_reason"] = f"Validated model risk ({prob:.4f}) is safely below the ALLOW threshold ({policy.allow_threshold:.4f}). Conflict overridden due to lack of independent corroborating evidence."
        else:
            result["decision"] = "ALLOW"
            result["decision_reason"] = f"Validated model risk ({prob:.4f}) is safely below the ALLOW threshold ({policy.allow_threshold:.4f})."
            
    elif prob >= policy.block_threshold:
        # BLOCK PATH requires passing Guardrails
        if conf not in ["HIGH", "MEDIUM"]:
            result["decision"] = "REVIEW"
            result["decision_reason"] = "Model risk exceeds BLOCK threshold, but confidence is too low (missing data). Escalate to REVIEW."
            result["blocking_guardrail_status"] = "FAILED_LOW_CONFIDENCE"
            
        elif not _has_independent_blocking_evidence(fusion_result.get("rule_evidence", {})):
            result["decision"] = "REVIEW"
            result["decision_reason"] = "Model risk exceeds BLOCK threshold, but lacks independent corroborating evidence (e.g. only relies on repeated_fraud). Escalate to REVIEW."
            result["blocking_guardrail_status"] = "FAILED_LACK_OF_INDEPENDENT_EVIDENCE"
            
        else:
            result["decision"] = "BLOCK"
            result["decision_reason"] = f"Validated model risk ({prob:.4f}) exceeds BLOCK threshold ({policy.block_threshold:.4f}) AND independent corroborating evidence guardrail passed."
            result["blocking_guardrail_status"] = "PASSED"
            
    else:
        # REVIEW PATH (Middle Band)
        result["decision"] = "REVIEW"
        result["decision_reason"] = f"Model risk ({prob:.4f}) falls within the REVIEW operating region [{policy.allow_threshold:.4f}, {policy.block_threshold:.4f}]."
        
    return result
