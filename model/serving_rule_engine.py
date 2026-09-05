"""
Deterministic Serving Rule Engine for RazorBrain.

Evaluates operational business and risk rules against the 15-feature contract
features. Does not fabricate data or alter the ML model probability.
Enforces deterministic priority and conflict resolution.
"""

from __future__ import annotations

import json
import logging
import math
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

SEVERITY_ORDER: Dict[str, int] = {
    "INFO": 0,
    "APPROVE": 0,
    "REVIEW": 1,
    "STEP_UP": 2,
    "DECLINE": 3,
}


class RuleResult:
    """Structured result of evaluating a single rule."""

    def __init__(
        self,
        rule_id: str,
        triggered: bool,
        severity: str,
        priority: int,
        reason_code: str,
        description: str,
        observed_values: Dict[str, Any],
        policy_version: str,
    ):
        self.rule_id = rule_id
        self.triggered = triggered
        self.severity = severity
        self.priority = priority
        self.reason_code = reason_code
        self.description = description
        self.observed_values = observed_values
        self.policy_version = policy_version

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "triggered": self.triggered,
            "severity": self.severity,
            "priority": self.priority,
            "reason_code": self.reason_code,
            "description": self.description,
            "observed_values": self.observed_values,
            "policy_version": self.policy_version,
        }


class ServingRuleEngine:
    """Evaluates configurable rules loaded from a versioned JSON policy."""

    def __init__(
        self,
        policy_path: str = "data/razorpay_serving_rule_policy_v1.json",
    ):
        self.policy_path = policy_path
        self.policy_version = "1.0"
        self.enabled = True
        self.rules_config: List[Dict[str, Any]] = []
        self._load_policy()

    def _load_policy(self) -> None:
        if not os.path.exists(self.policy_path):
            raise FileNotFoundError(f"Rule policy file not found: {self.policy_path}")

        try:
            with open(self.policy_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            raise ValueError(f"Malformed rule policy JSON in {self.policy_path}: {e}")

        self.policy_version = str(data.get("policy_version", "1.0"))
        self.enabled = bool(data.get("enabled", True))
        self.rules_config = data.get("rules", [])

        # Validate rule definitions
        seen_ids = set()
        for r in self.rules_config:
            rid = r.get("rule_id")
            if not rid:
                raise ValueError("Rule definition missing rule_id")
            if rid in seen_ids:
                raise ValueError(f"Duplicate rule_id found in policy: {rid}")
            seen_ids.add(rid)

            sev = r.get("severity")
            if sev not in SEVERITY_ORDER:
                raise ValueError(f"Invalid severity '{sev}' in rule '{rid}'")

    def evaluate(self, features: Dict[str, Any]) -> List[RuleResult]:
        """
        Evaluates all enabled rules against features and returns triggered rules
        sorted deterministically by:
        1. Severity (DECLINE > STEP_UP > REVIEW > INFO)
        2. Priority (higher integer first)
        3. rule_id (alphabetical tie-breaker)
        """
        if not self.enabled:
            return []

        triggered_results: List[RuleResult] = []

        # Safe extraction of features with standard defaults
        amount = self._safe_float(features.get("amount"), default=0.0)
        is_new_cust = int(features.get("is_new_customer", 0) or 0)
        prev_count = int(features.get("previous_transaction_count", 0) or 0)
        avg_amt = self._safe_float(features.get("avg_customer_amount"), default=0.0)
        amount_ratio = self._safe_float(features.get("amount_ratio"), default=1.0)
        txns_1h = int(features.get("txns_last_1h", 0) or 0)
        txns_24h = int(features.get("txns_last_24h", 0) or 0)
        card_network = str(features.get("card_network", "") or "").strip().lower()

        for rule in self.rules_config:
            if not rule.get("enabled", True):
                continue

            rule_id = rule["rule_id"]
            severity = rule["severity"]
            priority = int(rule.get("priority", 0))
            reason_code = rule.get("reason_code", rule_id)
            description = rule.get("description", "")
            triggered = False
            observed: Dict[str, Any] = {}

            try:
                if rule_id == "HIGH_VALUE_TRANSACTION":
                    thresh = float(rule.get("threshold", 500000.0))
                    # Only trigger if amount exceeds threshold but does not reach extreme high threshold (if defined)
                    extreme_thresh = 2500000.0
                    if amount > thresh and amount <= extreme_thresh:
                        triggered = True
                        observed = {"amount": amount, "threshold": thresh}

                elif rule_id == "EXTREME_HIGH_VALUE_TRANSACTION":
                    thresh = float(rule.get("threshold", 2500000.0))
                    if amount > thresh:
                        triggered = True
                        observed = {"amount": amount, "threshold": thresh}

                elif rule_id == "COLD_START_HIGH_AMOUNT":
                    thresh = float(rule.get("threshold", 50000.0))
                    if is_new_cust == 1 and amount >= thresh:
                        triggered = True
                        observed = {
                            "amount": amount,
                            "is_new_customer": is_new_cust,
                            "threshold": thresh,
                        }

                elif rule_id == "HIGH_VELOCITY_1H":
                    thresh = int(rule.get("threshold", 5))
                    if txns_1h >= thresh:
                        triggered = True
                        observed = {"txns_last_1h": txns_1h, "threshold": thresh}

                elif rule_id == "ELEVATED_VELOCITY_24H":
                    thresh = int(rule.get("threshold", 20))
                    if txns_24h >= thresh:
                        triggered = True
                        observed = {"txns_last_24h": txns_24h, "threshold": thresh}

                elif rule_id == "SIGNIFICANT_AMOUNT_DEVIATION":
                    thresh = float(rule.get("threshold", 10.0))
                    # Only applies to established customers with a baseline history
                    if is_new_cust == 0 and prev_count > 0 and avg_amt > 0:
                        if amount_ratio >= thresh:
                            triggered = True
                            observed = {
                                "amount_ratio": round(amount_ratio, 2),
                                "amount": amount,
                                "avg_customer_amount": avg_amt,
                                "threshold": thresh,
                            }

                elif rule_id == "RESTRICTED_CARD_NETWORK":
                    restricted = [n.lower() for n in rule.get("restricted_networks", ["test", "restricted"])]
                    if card_network in restricted:
                        triggered = True
                        observed = {"card_network": card_network, "restricted_list": restricted}

            except Exception as e:
                logger.error(f"Error evaluating rule {rule_id}: {e}", exc_info=True)
                continue

            if triggered:
                triggered_results.append(
                    RuleResult(
                        rule_id=rule_id,
                        triggered=True,
                        severity=severity,
                        priority=priority,
                        reason_code=reason_code,
                        description=description,
                        observed_values=observed,
                        policy_version=self.policy_version,
                    )
                )

        # Deterministic sorting:
        # 1. Severity descending (SEVERITY_ORDER value)
        # 2. Priority descending
        # 3. rule_id ascending (lexicographical tie-breaker)
        triggered_results.sort(
            key=lambda r: (-SEVERITY_ORDER.get(r.severity, 0), -r.priority, r.rule_id)
        )

        return triggered_results

    @staticmethod
    def _safe_float(val: Any, default: float = 0.0) -> float:
        if val is None:
            return default
        try:
            f = float(val)
            return f if math.isfinite(f) else default
        except (ValueError, TypeError):
            return default
