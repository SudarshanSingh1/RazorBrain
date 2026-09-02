"""
Risk Fusion for RazorBrain.

Combines model probabilities, SHAP evidence, and rule evidence into
a transparent, structured risk assessment. 
Does NOT invent arbitrary risk scores.
Does NOT make ALLOW/REVIEW/BLOCK decisions.
Preserves evidence independence and exact probability semantics.
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd
import numpy as np

from model.baseline import predict_proba
from model.calibration import predict_calibrated_proba
from model.explanation import explain_batch
from model.rule_engine import evaluate_rules

logger = logging.getLogger(__name__)


def fuse_risk_batch(
    X: pd.DataFrame,
    model_art: dict[str, Any],
    calib_art: dict[str, Any],
    explainer_art: dict[str, Any],
    rule_thresholds: dict[str, float],
    transaction_ids: pd.Series | list[str] | None = None
) -> list[dict[str, Any]]:
    """
    Fuse evidence for a batch of transactions deterministically.
    
    1. Extracts raw and calibrated probabilities.
    2. Extracts SHAP explanations.
    3. Evaluates rule engine evidence.
    4. Aggregates into a unified, non-double-counted assessment.
    """
    
    # 1. Model Assessment
    raw_probs = predict_proba(model_art, X)
    calib_probs = predict_calibrated_proba(calib_art, X)
    
    # 2. Model Evidence (SHAP)
    shap_exps = explain_batch(explainer_art, X, max_batch_size=len(X))
    
    # 3. Rule Evidence
    rule_evs = evaluate_rules(X, rule_thresholds)
    
    # 4. Fusion
    results = []
    
    # Rank lookup for highest severity computation
    sev_rank = {"HIGH": 3, "MEDIUM": 2, "LOW": 1, "INFO": 0}
    
    for i in range(len(X)):
        row = X.iloc[i]
        tid = transaction_ids.iloc[i] if transaction_ids is not None else f"txn_{i}"
        
        # Evaluate Completeness
        ip_miss = row.get("ip_is_missing", 0) == 1
        loc_miss = row.get("location_is_missing", 0) == 1
        new_cust = row.get("is_new_customer", 0) == 1
        
        missing_count = sum([ip_miss, loc_miss, new_cust])
        if missing_count == 0:
            completeness = "FULL"
        elif missing_count <= 2:
            completeness = "PARTIAL"
        else:
            completeness = "LIMITED"
            
        # Determine contextual severity from triggered rules
        triggered = rule_evs[i]
        max_sev = "NONE"
        if triggered:
            max_sev = max(triggered, key=lambda r: sev_rank[r["severity"]])["severity"]
            
        # Detect Evidence Conflicts
        calib_p = float(calib_probs[i])
        conflict = False
        conflict_reason = None
        
        # Conflict 1: Model says very low risk, Rules say HIGH risk
        if calib_p < 0.1 and max_sev == "HIGH":
            conflict = True
            conflict_reason = "Model probability is low, but highly severe deterministic evidence triggered."
            
        # Conflict 2: Model says very high risk, but NO rules triggered
        elif calib_p > 0.8 and max_sev in ["NONE", "INFO"]:
            conflict = True
            conflict_reason = "Model probability is extremely high, but no structured rule evidence corroborates."
            
        # Compile strictly structured assessment (No fake arbitrary score)
        assessment = {
            "transaction_id": str(tid),
            "model_assessment": {
                "raw_probability": float(raw_probs[i]),
                "calibrated_probability": calib_p,
                "calibration_status": calib_art["method"].upper()
            },
            "model_evidence": shap_exps[i],
            "rule_evidence": {
                "triggered_rules": triggered,
                "highest_severity": max_sev
            },
            "evidence_completeness": completeness,
            "evidence_conflict": {
                "has_conflict": conflict,
                "reason": conflict_reason
            },
            "fusion_summary": {
                # We strictly use the statistical probability as the primary risk anchor.
                "primary_risk_probability": calib_p,
                # Context is passed alongside it, NEVER mathematically added to it.
                "contextual_severity": max_sev,
                "confidence_in_probability": "HIGH" if completeness == "FULL" else "MEDIUM" if completeness == "PARTIAL" else "LOW"
            }
        }
        
        results.append(assessment)
        
    return results
