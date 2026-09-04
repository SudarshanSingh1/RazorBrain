"""
Policy loader for the Razorpay Serving Model.
Deterministic decision engine converting calibrated risk to ALLOW/REVIEW/BLOCK.
"""
import json
import os
import math

_POLICY_PATH = "data/razorpay_serving_selected_policy.json"
_EXPECTED_TRACK = "RAZORPAY_SERVING_MODEL"
_EXPECTED_STATUS = "VALIDATION_SELECTED"


class ServingPolicyLoader:
    def __init__(self, policy_path: str = _POLICY_PATH):
        if not os.path.exists(policy_path):
            raise FileNotFoundError(f"Serving policy missing: {policy_path}")

        with open(policy_path) as f:
            policy = json.load(f)

        if policy.get("model_track") != _EXPECTED_TRACK:
            raise ValueError(f"Invalid model track: {policy.get('model_track')} (expected {_EXPECTED_TRACK})")

        if policy.get("policy_status") != _EXPECTED_STATUS:
            raise ValueError(f"Invalid policy status: {policy.get('policy_status')} (expected {_EXPECTED_STATUS})")

        t_review = policy.get("threshold_review")
        t_block = policy.get("threshold_block")

        if t_review is None or t_block is None:
            raise ValueError("Missing threshold_review or threshold_block in policy artifact")

        try:
            self.t_review = float(t_review)
            self.t_block = float(t_block)
        except (TypeError, ValueError):
            raise ValueError(f"Malformed thresholds: t_review={t_review}, t_block={t_block}")

        if not math.isfinite(self.t_review) or not math.isfinite(self.t_block):
            raise ValueError(f"Non-finite thresholds: t_review={self.t_review}, t_block={self.t_block}")

        if not (self.t_review < self.t_block):
            raise ValueError(f"Invalid threshold ordering: T_review ({self.t_review}) must be < T_block ({self.t_block})")

        self.calibrated_artifact = policy.get("calibrated_artifact")
        self.calibrated_artifact_hash = policy.get("calibrated_artifact_hash")
        self.metadata = policy

    def make_decision(self, risk: float) -> str:
        """
        Convert calibrated risk to a decision.
        Fallback to REVIEW on invalid/NaN input.
        """
        if risk is None:
            return "REVIEW"

        try:
            risk = float(risk)
            if not math.isfinite(risk):
                return "REVIEW"
        except (TypeError, ValueError):
            return "REVIEW"

        if risk < self.t_review:
            return "ALLOW"
        elif risk < self.t_block:
            return "REVIEW"
        else:
            return "BLOCK"
