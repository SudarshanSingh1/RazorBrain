"""
SHAP-based model explainability for RazorBrain fraud models.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd
import shap
from sklearn.linear_model import LogisticRegression

logger = logging.getLogger(__name__)


def create_explainer(model_artifact: dict[str, Any], X_background: pd.DataFrame) -> dict[str, Any]:
    """
    Initialize the appropriate SHAP explainer based on the model type.
    """
    model = model_artifact["model"]
    feature_names = model_artifact["feature_names"]
    
    if list(X_background.columns) != feature_names:
        raise ValueError("Background features do not match expected training features.")
        
    scaler = model_artifact.get("scaler")
    
    # Scale background dataset if a scaler exists
    X_bg_proc = scaler.transform(X_background) if scaler else X_background
    
    # Logistic Regression natively supported by LinearExplainer
    if isinstance(model, LogisticRegression):
        # LinearExplainer works in log-odds space natively
        explainer = shap.LinearExplainer(model, X_bg_proc)
        explainer_type = "LinearExplainer"
    else:
        # Fallback to TreeExplainer for XGBoost (if needed)
        try:
            import xgboost as xgb
            if isinstance(model, xgb.XGBClassifier):
                explainer = shap.TreeExplainer(model)
                explainer_type = "TreeExplainer"
            else:
                raise ValueError(f"Unsupported model type: {type(model)}")
        except ImportError:
            raise ValueError(f"Unsupported model type: {type(model)}")
            
    return {
        "explainer": explainer,
        "explainer_type": explainer_type,
        "feature_names": feature_names,
        "scaler": scaler,
        "model_artifact": model_artifact
    }


def explain_batch(
    explainer_artifact: dict[str, Any], 
    X: pd.DataFrame, 
    max_batch_size: int = 1000
) -> list[dict[str, Any]]:
    """
    Generate SHAP explanations for a batch of transactions.
    Enforces a batch limit for memory and compute scalability.
    """
    if len(X) > max_batch_size:
        raise ValueError(f"Batch size {len(X)} exceeds maximum limit {max_batch_size}.")
        
    feature_names = explainer_artifact["feature_names"]
    if list(X.columns) != feature_names:
        raise ValueError("Input features do not match expected training features.")
        
    scaler = explainer_artifact["scaler"]
    explainer = explainer_artifact["explainer"]
    
    X_proc = scaler.transform(X) if scaler else X
    
    shap_values = explainer.shap_values(X_proc)
    
    # SHAP LinearExplainer and some TreeExplainers return lists for multi-class/binary
    # In Binary classification, we usually want index 1 (positive class).
    # Some older SHAP versions return array directly for LinearExplainer, some return list.
    if isinstance(shap_values, list):
        shap_values_pos = shap_values[1] if len(shap_values) > 1 else shap_values[0]
    else:
        shap_values_pos = shap_values
    
    # Base expected value
    expected_value = explainer.expected_value
    if isinstance(expected_value, (list, np.ndarray)):
        expected_value = expected_value[1] if len(expected_value) > 1 else expected_value[0]
        
    explanations = []
    
    # We iterate over rows and create structured JSON-like objects
    for i in range(len(X)):
        row_shap = shap_values_pos[i]
        row_actuals = X.iloc[i].to_dict()
        
        contributions = []
        for feature, s_val in zip(feature_names, row_shap):
            contributions.append({
                "feature": feature,
                "actual_value": float(row_actuals[feature]),
                "shap_contribution": float(s_val),
                "direction": "positive" if s_val > 0 else "negative" if s_val < 0 else "neutral"
            })
            
        # Sort contributions deterministically by absolute SHAP value (highest first)
        contributions.sort(key=lambda x: abs(x["shap_contribution"]), reverse=True)
        
        explanations.append({
            "base_value": float(expected_value),
            "space": "log-odds" if explainer_artifact["explainer_type"] == "LinearExplainer" else "margin",
            "top_positive_contributors": [c for c in contributions if c["direction"] == "positive"][:3],
            "top_negative_contributors": [c for c in contributions if c["direction"] == "negative"][:3],
            "all_contributions": contributions
        })
        
    return explanations


def explain_transaction(explainer_artifact: dict[str, Any], transaction_features: pd.DataFrame) -> dict[str, Any]:
    """
    Generate SHAP explanation for a single transaction.
    """
    if len(transaction_features) != 1:
        raise ValueError("explain_transaction expects exactly 1 row.")
        
    result = explain_batch(explainer_artifact, transaction_features, max_batch_size=1)
    return result[0]
