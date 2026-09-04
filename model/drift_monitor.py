import numpy as np
import pandas as pd
from typing import Dict, Any, List

def safe_log(x: float, eps: float = 1e-6) -> float:
    return np.log(max(x, eps))

def calculate_psi(expected_props: np.ndarray, actual_props: np.ndarray, eps: float = 1e-4) -> float:
    """Calculate Population Stability Index given two arrays of proportions."""
    exp = np.maximum(expected_props, eps)
    act = np.maximum(actual_props, eps)
    # Normalize to ensure they sum to 1
    exp = exp / exp.sum()
    act = act / act.sum()
    return float(np.sum((act - exp) * np.log(act / exp)))

def build_reference_distribution(X_train: pd.DataFrame, y_pred_proba: np.ndarray, decisions: List[str]) -> Dict[str, Any]:
    """
    Build the reference distribution artifact from the training population.
    This artifact is immutable and used for all future drift monitoring.
    """
    ref = {
        "numeric_bins": {},
        "categorical_props": {},
        "prediction_bins": [],
        "prediction_props": [],
        "decision_props": {"ALLOW": 0.0, "REVIEW": 0.0, "BLOCK": 0.0},
        "observation_count": len(X_train)
    }

    # Bins for numeric features (use fixed quantiles, e.g., 10 bins)
    # Distinguish numeric vs categorical heuristically: if > 10 unique values, numeric.
    for col in X_train.columns:
        if X_train[col].nunique() > 10:
            # Numeric
            try:
                bins = np.unique(np.percentile(X_train[col].dropna(), np.linspace(0, 100, 11)))
                if len(bins) < 2:
                    bins = np.array([-np.inf, np.inf])
            except Exception:
                bins = np.array([-np.inf, np.inf])
                
            bins[0] = -np.inf
            bins[-1] = np.inf
            
            counts, _ = np.histogram(X_train[col].dropna(), bins=bins)
            props = counts / max(1, counts.sum())
            ref["numeric_bins"][col] = {
                "bins": bins.tolist(),
                "props": props.tolist()
            }
        else:
            # Categorical
            val_counts = X_train[col].value_counts(normalize=True).to_dict()
            ref["categorical_props"][col] = {str(k): float(v) for k, v in val_counts.items()}

    # Prediction drift bins (10 equal width bins from 0 to 1)
    pred_bins = np.linspace(0, 1, 11)
    pred_bins[0] = -np.inf
    pred_bins[-1] = np.inf
    counts, _ = np.histogram(y_pred_proba, bins=pred_bins)
    pred_props = counts / max(1, counts.sum())
    ref["prediction_bins"] = pred_bins.tolist()
    ref["prediction_props"] = pred_props.tolist()

    # Decision drift
    n = len(decisions)
    if n > 0:
        ref["decision_props"]["ALLOW"] = decisions.count("ALLOW") / n
        ref["decision_props"]["REVIEW"] = decisions.count("REVIEW") / n
        ref["decision_props"]["BLOCK"] = decisions.count("BLOCK") / n

    return ref

def compute_drift_status(psi: float) -> str:
    if psi < 0.10:
        return "LOW"
    elif psi < 0.25:
        return "MODERATE"
    return "HIGH"

def evaluate_drift(current_df: pd.DataFrame, 
                   current_proba: np.ndarray, 
                   current_decisions: List[str], 
                   ref: Dict[str, Any], 
                   min_samples: int = 50) -> Dict[str, Any]:
    
    n_curr = len(current_df)
    if n_curr < min_samples:
        return {"status": "NOT_MEASURED", "reason": f"Insufficient observations ({n_curr} < {min_samples})"}

    feature_results = []
    
    # 1. Feature Drift
    for col in current_df.columns:
        if col in ref["numeric_bins"]:
            bins = ref["numeric_bins"][col]["bins"]
            ref_props = np.array(ref["numeric_bins"][col]["props"])
            counts, _ = np.histogram(current_df[col].dropna(), bins=bins)
            curr_props = counts / max(1, counts.sum())
            psi = calculate_psi(ref_props, curr_props)
            feature_results.append({"feature": col, "psi": round(psi, 4), "status": compute_drift_status(psi)})
            
        elif col in ref["categorical_props"]:
            ref_dict = ref["categorical_props"][col]
            curr_dict = current_df[col].value_counts(normalize=True).to_dict()
            
            # Align keys
            all_keys = set(ref_dict.keys()).union(set(str(k) for k in curr_dict.keys()))
            ref_props = []
            curr_props = []
            for k in sorted(all_keys):
                ref_props.append(ref_dict.get(k, 0.0))
                curr_props.append(curr_dict.get(type(list(curr_dict.keys())[0])(k) if curr_dict else k, curr_dict.get(k, 0.0)))
                
            psi = calculate_psi(np.array(ref_props), np.array(curr_props))
            feature_results.append({"feature": col, "psi": round(psi, 4), "status": compute_drift_status(psi)})

    # 2. Prediction Drift
    pred_n = len(current_proba)
    if pred_n > 0:
        pred_bins = ref["prediction_bins"]
        ref_pred_props = np.array(ref["prediction_props"])
        counts, _ = np.histogram(current_proba, bins=pred_bins)
        curr_pred_props = counts / max(1, counts.sum())
        pred_psi = calculate_psi(ref_pred_props, curr_pred_props)
        pred_status = compute_drift_status(pred_psi)
        prediction_drift = {"psi": round(pred_psi, 4), "status": pred_status, "observations": pred_n}
    else:
        prediction_drift = {"status": "NOT_MEASURED", "reason": "No probabilities"}

    # 3. Decision Drift
    dec_n = len(current_decisions)
    if dec_n > 0:
        curr_allow = current_decisions.count("ALLOW") / dec_n
        curr_review = current_decisions.count("REVIEW") / dec_n
        curr_block = current_decisions.count("BLOCK") / dec_n
        
        decision_drift = {
            "ALLOW": {
                "reference": round(ref["decision_props"]["ALLOW"], 4),
                "current": round(curr_allow, 4),
                "change": round(curr_allow - ref["decision_props"]["ALLOW"], 4)
            },
            "REVIEW": {
                "reference": round(ref["decision_props"]["REVIEW"], 4),
                "current": round(curr_review, 4),
                "change": round(curr_review - ref["decision_props"]["REVIEW"], 4)
            },
            "BLOCK": {
                "reference": round(ref["decision_props"]["BLOCK"], 4),
                "current": round(curr_block, 4),
                "change": round(curr_block - ref["decision_props"]["BLOCK"], 4)
            }
        }
    else:
        decision_drift = {"status": "NOT_MEASURED", "reason": "No decisions"}

    # 4. Overall Status
    # High if any high, Moderate if no high but any moderate, else NO MATERIAL SIGNAL
    statuses = [f["status"] for f in feature_results]
    if prediction_drift.get("status") in ["LOW", "MODERATE", "HIGH"]:
        statuses.append(prediction_drift["status"])
        
    if "HIGH" in statuses:
        overall = "HIGH DRIFT SIGNAL"
    elif "MODERATE" in statuses:
        overall = "MODERATE DRIFT SIGNAL"
    else:
        overall = "NO MATERIAL SIGNAL"

    return {
        "status": "MEASURED",
        "overall_status": overall,
        "reference_observations": ref["observation_count"],
        "current_observations": n_curr,
        "features": feature_results,
        "prediction_drift": prediction_drift,
        "decision_drift": decision_drift
    }
