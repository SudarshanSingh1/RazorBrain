"""
Decision Engine v2 with Integrated Hybrid Risk Fusion for RazorBrain.

Evaluates calibrated ML fraud probability, executes deterministic rule evaluation,
and fuses the signals into a unified business intervention decision.
Guarantees monotonic safety: rules and overrides can only escalate intervention severity.
"""

from __future__ import annotations

import json
import logging
import math
import os
from typing import Any, Dict, List, Optional, Tuple

from model.serving_rule_engine import ServingRuleEngine
from model.serving_risk_fusion import HybridRiskFusionEngine, HybridRiskAssessment

logger = logging.getLogger(__name__)

DECISION_SEVERITY: Dict[str, int] = {
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


class DecisionPolicyV2:
    """Configurable 4-tier decision boundaries and hard overrides."""

    def __init__(self, policy_path: str = "data/razorpay_serving_decision_policy_v2.json", config_dict: Optional[Dict[str, Any]] = None):
        if config_dict:
            policy = config_dict
        else:
            if not os.path.exists(policy_path):
                raise FileNotFoundError(f"Decision policy missing: {policy_path}")

            with open(policy_path, "r", encoding="utf-8") as f:
                policy = json.load(f)

        self.metadata = policy
        self.version = policy.get("policy_version", "2.0")

        t = policy.get("thresholds", {})
        self.t_approve = float(t.get("approve_max", 0.1213))
        self.t_review = float(t.get("review_max", 0.1600))
        self.t_step_up = float(t.get("step_up_max", 0.2053))

        if not (0.0 <= self.t_approve < self.t_review <= self.t_step_up <= 1.0):
            raise ValueError("Thresholds must satisfy 0 <= approve < review <= step_up <= 1")

        self.hard_overrides = policy.get("hard_overrides", [])


class DecisionEngineV2:
    """
    Unified Decision Engine executing:
    1. Base ML model decision
    2. Versioned Rule Engine
    3. Hybrid Risk Fusion
    4. Monotonic Safety Guardrail
    """

    def __init__(
        self,
        policy: DecisionPolicyV2,
        rule_engine: Optional[ServingRuleEngine] = None,
        fusion_engine: Optional[HybridRiskFusionEngine] = None,
    ):
        self.policy = policy
        self.rule_engine = rule_engine or ServingRuleEngine()
        self.fusion_engine = fusion_engine or HybridRiskFusionEngine()

    def evaluate(
        self,
        probability: float,
        features: Dict[str, Any],
    ) -> Tuple[str, str, List[Dict[str, Any]]]:
        """
        Backward-compatible evaluation returning (final_decision, decision_reason, decision_trace).
        """
        final_decision, final_reason, trace, _ = self.evaluate_hybrid(probability, features)
        return final_decision, final_reason, trace

    def evaluate_hybrid(
        self,
        probability: float,
        features: Dict[str, Any],
        model_risk_level: Optional[str] = None,
    ) -> Tuple[str, str, List[Dict[str, Any]], HybridRiskAssessment]:
        """
        Evaluates the transaction through ML boundaries, Rule Engine, and Hybrid Risk Fusion.
        Returns:
        (final_decision, final_reason, decision_trace, hybrid_assessment)
        """
        trace: List[Dict[str, Any]] = []

        # ── 1. Base ML Decision ────────────────────────────────────────────────
        base_decision = "DECLINE"
        base_reason = "MODEL_PROBABILITY_ELEVATED"

        if probability is None or not math.isfinite(probability) or math.isnan(probability):
            logger.warning("Invalid probability provided to Decision Engine. Failing safely to DECLINE.")
            base_decision = "DECLINE"
            base_reason = "INVALID_PROBABILITY"
            probability = 1.0
        elif probability < self.policy.t_approve:
            base_decision = "APPROVE"
            base_reason = "PROBABILITY_WITHIN_APPROVE_LIMIT"
        elif probability < self.policy.t_review:
            base_decision = "REVIEW"
            base_reason = "PROBABILITY_WITHIN_REVIEW_LIMIT"
        elif probability < self.policy.t_step_up:
            base_decision = "STEP_UP"
            base_reason = "PROBABILITY_WITHIN_STEP_UP_LIMIT"
        else:
            base_decision = "DECLINE"
            base_reason = "PROBABILITY_EXCEEDS_STEP_UP_LIMIT"

        trace.append({
            "stage": "BASE_ML_MODEL",
            "decision": base_decision,
            "reason": base_reason,
            "probability": str(probability),
        })

        if model_risk_level is None:
            if probability < self.policy.t_approve:
                model_risk_level = "LOW"
            elif probability < self.policy.t_step_up:
                model_risk_level = "MEDIUM"
            else:
                model_risk_level = "HIGH"

        # ── 2. Hard Overrides (Preserved for policy compatibility) ─────────────
        override_decision = base_decision
        override_reason = base_reason

        for override in self.policy.hard_overrides:
            condition = override["condition"]
            force_decision = override["force_decision"]
            reason_code = override["reason_code"]

            triggered = self._evaluate_condition(condition, features)
            if triggered:
                trace_entry = {
                    "stage": "HARD_OVERRIDE",
                    "rule": condition,
                    "proposed_decision": force_decision,
                    "reason": reason_code,
                }
                if DECISION_SEVERITY.get(force_decision, 0) > DECISION_SEVERITY.get(override_decision, 0):
                    override_decision = force_decision
                    override_reason = reason_code
                    trace_entry["applied"] = "YES - Increased severity"
                else:
                    trace_entry["applied"] = "NO - Cannot downgrade severity"
                trace.append(trace_entry)

        # ── 3. Serving Rule Engine Evaluation ──────────────────────────────────
        try:
            triggered_rules = self.rule_engine.evaluate(features)
        except Exception as e:
            logger.error(f"Rule Engine evaluation failure: {e}", exc_info=True)
            triggered_rules = []

        trace.append({
            "stage": "RULE_ENGINE",
            "policy_version": self.rule_engine.policy_version,
            "evaluated_rules_count": len(self.rule_engine.rules_config),
            "triggered_rules_count": len(triggered_rules),
            "triggered_rules": [r.to_dict() for r in triggered_rules],
        })

        # ── 4. Hybrid Risk Fusion ──────────────────────────────────────────────
        hybrid_assessment = self.fusion_engine.fuse(
            fraud_probability=probability,
            model_risk_level=model_risk_level,
            base_decision=base_decision,
            triggered_rules=triggered_rules,
        )

        trace.append({
            "stage": "HYBRID_FUSION",
            "fusion_version": hybrid_assessment.fusion_version,
            "recommended_minimum_decision": hybrid_assessment.recommended_minimum_decision,
            "highest_rule_severity": hybrid_assessment.highest_rule_severity,
            "has_conflict": hybrid_assessment.has_conflict,
            "conflict_reason": hybrid_assessment.conflict_reason,
        })

        # ── 5. Final Monotonic Synthesis ───────────────────────────────────────
        # Compare base decision, hard override recommendation, and hybrid fusion recommendation
        ranks = [
            (DECISION_SEVERITY.get(base_decision, 0), base_decision, base_reason),
            (DECISION_SEVERITY.get(override_decision, 0), override_decision, override_reason),
            (
                DECISION_SEVERITY.get(hybrid_assessment.recommended_minimum_decision, 0),
                hybrid_assessment.recommended_minimum_decision,
                triggered_rules[0].reason_code if triggered_rules else base_reason,
            ),
        ]

        # Highest severity wins; in tie, preference given to highest override/rule reason
        max_rank = max(r[0] for r in ranks)
        final_decision = SEVERITY_TO_DECISION.get(max_rank, "REVIEW")

        # Pick the most specific reason matching the final decision severity
        final_reason = base_reason
        for r_rank, r_dec, r_reas in reversed(ranks):
            if r_rank == max_rank:
                final_reason = r_reas
                break

        trace.append({
            "stage": "FINAL_DECISION",
            "decision": final_decision,
            "reason": final_reason,
            "escalated_from_base": max_rank > DECISION_SEVERITY.get(base_decision, 0),
        })

        return final_decision, final_reason, trace, hybrid_assessment

    def _evaluate_condition(self, condition: str, features: Dict[str, Any]) -> bool:
        """Safely evaluates hard override condition string."""
        try:
            local_vars = features.copy()
            allowed_names = {
                "__builtins__": None,
                "True": True,
                "False": False,
                "str": str,
                "int": int,
                "float": float,
                "len": len,
            }
            result = eval(condition, allowed_names, local_vars)
            return bool(result)
        except Exception as e:
            logger.warning(f"Error evaluating condition '{condition}': {e}")
            return False
