"""
Hybrid Risk Fusion Layer for RazorBrain Serving Pipeline.

Combines the calibrated ML fraud probability and deterministic rule engine signals
into a structured intervention assessment.
Strictly adheres to the core principle:
- Model answers: "How risky does the model estimate this transaction to be?"
- Rules answer: "Are there deterministic operational or policy risk signals?"
- Fusion answers: "What is the minimum recommended intervention across both?"

DOES NOT modify or fabricate fraud_probability.
DOES NOT present fused intervention as a probability.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from model.serving_rule_engine import RuleResult, SEVERITY_ORDER

logger = logging.getLogger(__name__)

DECISION_TO_SEVERITY: Dict[str, int] = {
    "APPROVE": 0,
    "REVIEW": 1,
    "STEP_UP": 2,
    "DECLINE": 3,
}

SEVERITY_TO_DECISION: Dict[int, str] = {
    0: "APPROVE",
    1: "REVIEW",
    2: "STEP_UP",
    3: "DECLINE",
}


class HybridRiskAssessment:
    """Structured result of combining ML model assessment with rule signals."""

    def __init__(
        self,
        fraud_probability: float,
        model_risk_level: str,
        base_decision: str,
        triggered_rules: List[RuleResult],
        recommended_minimum_decision: str,
        highest_rule_severity: str,
        has_conflict: bool,
        conflict_reason: Optional[str],
        fusion_version: str = "1.0",
    ):
        self.fraud_probability = fraud_probability
        self.model_risk_level = model_risk_level
        self.base_decision = base_decision
        self.triggered_rules = triggered_rules
        self.recommended_minimum_decision = recommended_minimum_decision
        self.highest_rule_severity = highest_rule_severity
        self.has_conflict = has_conflict
        self.conflict_reason = conflict_reason
        self.fusion_version = fusion_version

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fusion_version": self.fusion_version,
            "fraud_probability": self.fraud_probability,
            "model_risk_level": self.model_risk_level,
            "base_decision": self.base_decision,
            "highest_rule_severity": self.highest_rule_severity,
            "recommended_minimum_decision": self.recommended_minimum_decision,
            "conflict_status": {
                "has_conflict": self.has_conflict,
                "reason": self.conflict_reason,
            },
            "triggered_rules_count": len(self.triggered_rules),
            "triggered_rules": [r.to_dict() for r in self.triggered_rules],
        }


class HybridRiskFusionEngine:
    """Combines ML base decision with deterministic rule recommendations."""

    def __init__(self, fusion_version: str = "1.0"):
        self.fusion_version = fusion_version

    def fuse(
        self,
        fraud_probability: float,
        model_risk_level: str,
        base_decision: str,
        triggered_rules: List[RuleResult],
    ) -> HybridRiskAssessment:
        """
        Calculates the minimum required intervention by fusing the ML base decision
        with the highest severity rule signal. Enforces monotonic safety: rules can only
        escalate intervention, never downgrade it.
        """
        # 1. Determine highest rule severity recommendation
        highest_rule_sev = "NONE"
        highest_rule_rank = 0
        if triggered_rules:
            # triggered_rules are already sorted with highest severity first
            top_rule = triggered_rules[0]
            highest_rule_sev = top_rule.severity
            highest_rule_rank = SEVERITY_ORDER.get(highest_rule_sev, 0)

        # 2. Base model rank
        base_rank = DECISION_TO_SEVERITY.get(base_decision, 0)

        # 3. Monotonic fusion: take max(base_rank, highest_rule_rank)
        fused_rank = max(base_rank, highest_rule_rank)
        recommended_decision = SEVERITY_TO_DECISION.get(fused_rank, "REVIEW")

        # 4. Conflict detection
        has_conflict = False
        conflict_reason = None

        if fraud_probability < 0.10 and highest_rule_rank >= DECISION_TO_SEVERITY["STEP_UP"]:
            has_conflict = True
            conflict_reason = (
                f"Model estimated low probability ({fraud_probability:.4f}), "
                f"but deterministic rule triggered {highest_rule_sev} intervention."
            )
        elif fraud_probability >= 0.25 and not triggered_rules:
            has_conflict = True
            conflict_reason = (
                f"Model estimated high probability ({fraud_probability:.4f}), "
                f"but no deterministic operational rules were triggered."
            )

        return HybridRiskAssessment(
            fraud_probability=fraud_probability,
            model_risk_level=model_risk_level,
            base_decision=base_decision,
            triggered_rules=triggered_rules,
            recommended_minimum_decision=recommended_decision,
            highest_rule_severity=highest_rule_sev,
            has_conflict=has_conflict,
            conflict_reason=conflict_reason,
            fusion_version=self.fusion_version,
        )
