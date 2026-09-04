"""
Rule Engine for RazorBrain.

Evaluates structured risk evidence based on actual transaction features.
Does NOT produce final Allow/Review/Block decisions.
Does NOT fabricate evidence or thresholds.
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


def extract_training_thresholds(X_train: pd.DataFrame) -> dict[str, float]:
    """
    Extract deterministic statistical thresholds purely from the TRAINING dataset.
    This ensures domain constraints are learned legitimately, not guessed.
    """
    thresholds = {}
    
    # Amount logic
    thresholds["amount_p99"] = float(X_train["amount"].quantile(0.99))
    thresholds["amount_deviation_p99"] = float(X_train["amount_deviation"].quantile(0.99))
    
    # Velocity logic
    thresholds["txns_last_5min_p99"] = float(X_train["txns_last_5min"].quantile(0.99))
    thresholds["txns_last_1h_p99"] = float(X_train["txns_last_1h"].quantile(0.99))
    thresholds["txns_last_24h_p99"] = float(X_train["txns_last_24h"].quantile(0.99))
    
    # Risk propagation
    thresholds["merchant_fraud_rate_p95"] = float(X_train["merchant_fraud_rate"].quantile(0.95))
    
    # Only keep reasonable bounds if they are too small
    if thresholds["merchant_fraud_rate_p95"] < 0.05:
        thresholds["merchant_fraud_rate_p95"] = 0.05
        
    return thresholds


class Rule:
    """Base class for all evidence-generating rules."""
    
    def __init__(self, rule_id: str, name: str, severity: str):
        self.rule_id = rule_id
        self.name = name
        self.severity = severity
        
    def evaluate(self, txn: pd.Series, thresholds: dict[str, float]) -> dict[str, Any]:
        """
        Evaluate the rule against a single transaction.
        Returns a dict containing evidence if triggered.
        """
        raise NotImplementedError
        
    def format_result(self, status: str, evidence: str = "", observed: dict | None = None, threshold_used: dict | None = None) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "rule_name": self.name,
            "severity": self.severity,
            "status": status,
            "evidence": evidence,
            "observed_values": observed or {},
            "thresholds": threshold_used or {}
        }


class VelocityNewDeviceRule(Rule):
    def __init__(self):
        super().__init__("velocity_new_device", "High 24h Velocity with New Device", "HIGH")
        
    def evaluate(self, txn: pd.Series, thresholds: dict[str, float]) -> dict[str, Any]:
        thresh = thresholds["txns_last_24h_p99"]
        txns = txn["txns_last_24h"]
        new_dev = txn.get("new_device_flag", pd.NA)
        
        if pd.isna(txns) or pd.isna(new_dev):
            return self.format_result("UNAVAILABLE")
            
        if txns > thresh and new_dev == 1:
            return self.format_result(
                "TRIGGERED",
                "Transaction frequency exceeds 99th percentile while using an unseen device.",
                {"txns_last_24h": txns, "new_device_flag": new_dev},
                {"txns_last_24h_p99": thresh}
            )
        return self.format_result("NOT_TRIGGERED")


class DeviationNewLocationRule(Rule):
    def __init__(self):
        super().__init__("deviation_new_location", "Large Deviation at New Location", "MEDIUM")
        
    def evaluate(self, txn: pd.Series, thresholds: dict[str, float]) -> dict[str, Any]:
        thresh = thresholds["amount_deviation_p99"]
        dev = txn["amount_deviation"]
        new_loc = txn.get("new_location_flag", pd.NA)
        
        if pd.isna(dev) or pd.isna(new_loc) or txn.get("location_is_missing") == 1:
            return self.format_result("UNAVAILABLE")
            
        if dev > thresh and new_loc == 1:
            return self.format_result(
                "TRIGGERED",
                "Transaction amount heavily deviates from customer history at an unseen location.",
                {"amount_deviation": dev, "new_location_flag": new_loc},
                {"amount_deviation_p99": thresh}
            )
        return self.format_result("NOT_TRIGGERED")


class MissingContextRule(Rule):
    def __init__(self):
        super().__init__("missing_critical_context", "Missing Critical Context (IP/Location)", "INFO")
        
    def evaluate(self, txn: pd.Series, thresholds: dict[str, float]) -> dict[str, Any]:
        ip_miss = txn.get("ip_is_missing", 0)
        loc_miss = txn.get("location_is_missing", 0)
        
        if ip_miss == 1 or loc_miss == 1:
            return self.format_result(
                "TRIGGERED",
                "Crucial identity context markers are missing from the payload.",
                {"ip_is_missing": ip_miss, "location_is_missing": loc_miss}
            )
        return self.format_result("NOT_TRIGGERED")


class RepeatedFraudRule(Rule):
    def __init__(self):
        super().__init__("repeated_fraud", "Customer Has Prior Fraud History", "HIGH")
        
    def evaluate(self, txn: pd.Series, thresholds: dict[str, float]) -> dict[str, Any]:
        fraud_count = txn["previous_fraud_count"]
        
        if pd.isna(fraud_count):
            return self.format_result("UNAVAILABLE")
            
        if fraud_count > 0:
            return self.format_result(
                "TRIGGERED",
                "Customer has a known history of fraudulent transactions.",
                {"previous_fraud_count": fraud_count}
            )
        return self.format_result("NOT_TRIGGERED")


class RiskyMerchantMatchRule(Rule):
    def __init__(self):
        super().__init__("risky_merchant_new_customer", "New Customer at High Risk Merchant", "MEDIUM")
        
    def evaluate(self, txn: pd.Series, thresholds: dict[str, float]) -> dict[str, Any]:
        thresh = thresholds["merchant_fraud_rate_p95"]
        fraud_rate = txn["merchant_fraud_rate"]
        new_cust = txn["is_new_customer"]
        
        if pd.isna(fraud_rate) or pd.isna(new_cust):
            return self.format_result("UNAVAILABLE")
            
        if fraud_rate > thresh and new_cust == 1:
            return self.format_result(
                "TRIGGERED",
                "First-time customer interaction at a merchant with historically high fraud rates.",
                {"merchant_fraud_rate": fraud_rate, "is_new_customer": new_cust},
                {"merchant_fraud_rate_p95": thresh}
            )
        return self.format_result("NOT_TRIGGERED")


class ExtremeAmountRule(Rule):
    def __init__(self):
        # Explicitly LOW severity to prevent a single weak signal from triggering BLOCK.
        super().__init__("extreme_amount_single_signal", "Extremely Large Transaction", "LOW")
        
    def evaluate(self, txn: pd.Series, thresholds: dict[str, float]) -> dict[str, Any]:
        thresh = thresholds["amount_p99"]
        amt = txn["amount"]
        
        if pd.isna(amt):
            return self.format_result("UNAVAILABLE")
            
        if amt > thresh:
            return self.format_result(
                "TRIGGERED",
                "Transaction amount exceeds 99th percentile across entire platform history.",
                {"amount": amt},
                {"amount_p99": thresh}
            )
        return self.format_result("NOT_TRIGGERED")


# Global Registry
AVAILABLE_RULES = [
    VelocityNewDeviceRule(),
    DeviationNewLocationRule(),
    MissingContextRule(),
    RepeatedFraudRule(),
    RiskyMerchantMatchRule(),
    ExtremeAmountRule()
]


def evaluate_rules(transaction_features: pd.DataFrame, thresholds: dict[str, float]) -> list[list[dict[str, Any]]]:
    """
    Evaluate all configured rules against a batch of transactions.
    Returns a list (per transaction) of lists (triggered rules only).
    """
    results = []
    
    # Iterate for each row (batch processing)
    for i in range(len(transaction_features)):
        txn = transaction_features.iloc[i]
        txn_evidence = []
        
        for rule in AVAILABLE_RULES:
            res = rule.evaluate(txn, thresholds)
            if res["status"] == "TRIGGERED":
                txn_evidence.append(res)
                
        results.append(txn_evidence)
        
    return results
