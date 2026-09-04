"""
Final Held-Out ML Evaluation Module for RazorBrain.

This module performs a reproducible, un-contaminated evaluation of the
authoritative RazorBrain risk pipeline on the protected held-out TEST set.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import (
    confusion_matrix, precision_score, recall_score, f1_score,
    precision_recall_curve, auc, roc_auc_score, accuracy_score
)

from data.generator import generate_transactions
from model.dataset_split import split_chronological
from model.feature_engineering import (
    compute_historical_features, fit_transform_features,
    transform_features, get_feature_matrix, get_target
)
from model.baseline import train_baseline
from model.calibration import fit_calibration, evaluate_calibration, predict_calibrated_proba
from model.explanation import create_explainer
from model.rule_engine import extract_training_thresholds
from model.decision_engine import DecisionPolicy, make_decision
from model.risk_fusion import fuse_risk_batch

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# Output artifact path
EVAL_ARTIFACT_PATH = Path("evaluation_artifact.json")


def run_evaluation():
    t_start = time.time()
    
    # 1. Dataset Generation
    t_gen_start = time.time()
    logger.info("Generating reproducible dataset (N=100000, seed=42)...")
    raw_df = generate_transactions(n=100000, seed=42)
    t_gen_end = time.time()
    
    # 2. Historical Feature Engineering
    t_feat_start = time.time()
    logger.info("Computing strictly time-aware historical features...")
    df_hist = compute_historical_features(raw_df)
    t_feat_end = time.time()
    
    # 3. Data Split
    logger.info("Splitting dataset chronologically...")
    train_df, val_df, test_df = split_chronological(df_hist)
    
    # Data stats
    dataset_stats = {
        "total_rows": len(raw_df),
        "train_rows": len(train_df),
        "val_rows": len(val_df),
        "test_rows": len(test_df),
        "train_fraud": int(train_df["is_fraud"].sum()),
        "train_legit": int(len(train_df) - train_df["is_fraud"].sum()),
        "val_fraud": int(val_df["is_fraud"].sum()),
        "val_legit": int(len(val_df) - val_df["is_fraud"].sum()),
        "test_fraud": int(test_df["is_fraud"].sum()),
        "test_legit": int(len(test_df) - test_df["is_fraud"].sum()),
        "train_prev": float(train_df["is_fraud"].mean()),
        "val_prev": float(val_df["is_fraud"].mean()),
        "test_prev": float(test_df["is_fraud"].mean()),
        "train_date_range": [str(train_df["timestamp"].min()), str(train_df["timestamp"].max())],
        "val_date_range": [str(val_df["timestamp"].min()), str(val_df["timestamp"].max())],
        "test_date_range": [str(test_df["timestamp"].min()), str(test_df["timestamp"].max())],
    }
    
    # Leakage Checks
    logger.info("Performing leakage audit...")
    leakage_audit = {}
    leakage_audit["chronological_order"] = bool(train_df["timestamp"].max() <= val_df["timestamp"].min() and val_df["timestamp"].max() <= test_df["timestamp"].min())
    leakage_audit["no_nans_in_test_labels"] = bool(not test_df["is_fraud"].isna().any())
    leakage_audit["both_classes_in_test"] = bool(test_df["is_fraud"].nunique() == 2)
    
    # 4. Feature Transformations
    logger.info("Fitting feature transformations on TRAIN only...")
    train_feat, encoder_state = fit_transform_features(train_df)
    
    logger.info("Applying feature transformations to TEST...")
    test_feat = transform_features(test_df, encoder_state)
    
    X_train = get_feature_matrix(train_feat)
    y_train = get_target(train_feat)
    
    X_test = get_feature_matrix(test_feat)
    y_test = get_target(test_feat)
    
    leakage_audit["no_target_in_features"] = bool("is_fraud" not in X_train.columns)
    leakage_audit["test_feature_order_matches_train"] = bool(list(X_train.columns) == list(X_test.columns))
    
    # 5. Model Fitting
    t_model_start = time.time()
    logger.info("Training authoritative baseline model (XGBoost)...")
    model_artifact = train_baseline(X_train, y_train, random_state=42)
    t_model_end = time.time()
    
    # 6. Calibration
    t_calib_start = time.time()
    logger.info("Fitting calibration (Isotonic) on TRAIN...")
    calib_artifact = fit_calibration(model_artifact, X_train, y_train, method="none")
    t_calib_end = time.time()
    
    # 7. Artifacts
    logger.info("Extracting artifacts...")
    explainer_artifact = create_explainer(model_artifact, X_train)
    rule_thresholds = extract_training_thresholds(X_train)
    
    # 8. Evaluation on TEST set
    t_pred_start = time.time()
    logger.info("Evaluating on TEST set...")
    from model.baseline import predict_proba
    y_prob_raw_test = predict_proba(model_artifact, X_test)
    y_prob_calib_test = predict_calibrated_proba(calib_artifact, X_test)
    
    fusion_results = fuse_risk_batch(
        X=X_test,
        model_art=model_artifact,
        calib_art=calib_artifact,
        explainer_art=explainer_artifact,
        rule_thresholds=rule_thresholds,
        transaction_ids=test_df["transaction_id"]
    )
    
    policy = DecisionPolicy(allow_threshold=0.10, block_threshold=0.40)
    decisions = []
    for res in fusion_results:
        decisions.append(make_decision(res, policy))
        
    t_pred_end = time.time()
    
    t_metric_start = time.time()
    logger.info("Calculating metrics...")
    
    # ML Metrics
    # Predict binary at existing block threshold for confusion matrix? 
    # Or just standard 0.5? 
    # Prompt: "final classification at the EXISTING validation-selected threshold" -> 0.40
    y_pred_test = (y_prob_calib_test >= 0.40).astype(int)
    
    tn, fp, fn, tp = confusion_matrix(y_test, y_pred_test).ravel()
    
    precision = precision_score(y_test, y_pred_test, zero_division=0)
    recall = recall_score(y_test, y_pred_test, zero_division=0)
    f1 = f1_score(y_test, y_pred_test, zero_division=0)
    roc_auc = roc_auc_score(y_test, y_prob_calib_test)
    
    precision_curve, recall_curve, _ = precision_recall_curve(y_test, y_prob_calib_test)
    pr_auc = auc(recall_curve, precision_curve)
    
    acc = accuracy_score(y_test, y_pred_test)
    specificity = tn / (tn + fp) if (tn + fp) > 0 else 0.0
    fpr = fp / (tn + fp) if (tn + fp) > 0 else 0.0
    fnr = fn / (tp + fn) if (tp + fn) > 0 else 0.0
    
    leakage_audit["confusion_matrix_reconciles"] = bool(tn + fp + fn + tp == len(y_test))
    
    metrics_clf = {
        "tp": int(tp),
        "tn": int(tn),
        "fp": int(fp),
        "fn": int(fn),
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
        "pr_auc": float(pr_auc),
        "roc_auc": float(roc_auc),
        "accuracy": float(acc),
        "specificity": float(specificity),
        "fpr": float(fpr),
        "fnr": float(fnr),
        "predicted_positive_rate": float(y_pred_test.mean())
    }
    
    # Calibration
    calib_metrics = evaluate_calibration(y_test, y_prob_raw_test, y_prob_calib_test, n_bins=10)
    
    # Decision Engine / Threshold Policy Evaluation
    dec_df = pd.DataFrame([{"decision": d["decision"], "is_fraud": y} for d, y in zip(decisions, y_test)])
    
    legit_df = dec_df[dec_df["is_fraud"] == 0]
    fraud_df = dec_df[dec_df["is_fraud"] == 1]
    
    legit_counts = legit_df["decision"].value_counts().to_dict()
    fraud_counts = fraud_df["decision"].value_counts().to_dict()
    
    decision_metrics = {
        "legit_allow": legit_counts.get("ALLOW", 0),
        "legit_review": legit_counts.get("REVIEW", 0),
        "legit_block": legit_counts.get("BLOCK", 0),
        "fraud_allow": fraud_counts.get("ALLOW", 0),
        "fraud_review": fraud_counts.get("REVIEW", 0),
        "fraud_block": fraud_counts.get("BLOCK", 0),
    }
    
    # Percentages
    decision_metrics["legit_allow_pct"] = decision_metrics["legit_allow"] / len(legit_df) if len(legit_df) else 0.0
    decision_metrics["legit_review_pct"] = decision_metrics["legit_review"] / len(legit_df) if len(legit_df) else 0.0
    decision_metrics["legit_block_pct"] = decision_metrics["legit_block"] / len(legit_df) if len(legit_df) else 0.0
    
    decision_metrics["fraud_allow_pct"] = decision_metrics["fraud_allow"] / len(fraud_df) if len(fraud_df) else 0.0
    decision_metrics["fraud_review_pct"] = decision_metrics["fraud_review"] / len(fraud_df) if len(fraud_df) else 0.0
    decision_metrics["fraud_block_pct"] = decision_metrics["fraud_block"] / len(fraud_df) if len(fraud_df) else 0.0
    
    # Business Cost
    cost_fraud_allow = decision_metrics["fraud_allow"] * 500
    cost_fraud_review = decision_metrics["fraud_review"] * 50
    cost_legit_review = decision_metrics["legit_review"] * 50
    cost_legit_block = decision_metrics["legit_block"] * 100
    
    total_cost = cost_fraud_allow + cost_fraud_review + cost_legit_review + cost_legit_block
    
    business_cost = {
        "fraud_allowed_cost": cost_fraud_allow,
        "fraud_reviewed_cost": cost_fraud_review,
        "legit_reviewed_cost": cost_legit_review,
        "legit_blocked_cost": cost_legit_block,
        "total_test_business_cost": total_cost,
        "avg_cost_per_transaction": total_cost / len(y_test) if len(y_test) else 0.0,
        "avg_cost_per_fraud": (cost_fraud_allow + cost_fraud_review) / len(fraud_df) if len(fraud_df) else 0.0,
        "avg_cost_per_legit": (cost_legit_review + cost_legit_block) / len(legit_df) if len(legit_df) else 0.0
    }
    
    # Rule Evidence Analysis
    rule_counts = {}
    severity_counts = {"INFO": 0, "LOW": 0, "MEDIUM": 0, "HIGH": 0}
    blocking_eligible = 0
    missing_evidence = 0
    
    conflict_model_rule = 0
    conflict_completeness = {"complete": 0, "partial": 0, "unavailable": 0}
    conflict_confidence = {"low": 0, "medium": 0, "high": 0}
    
    # SHAP tracking
    shap_contributions = {}
    shap_counts = 0
    
    for f in fusion_results:
        # Rule
        r_ev = f.get("rule_evidence", {})
        triggered = r_ev.get("triggered_rules", [])
        for tr in triggered:
            rid = tr["rule_id"]
            sev = tr["severity"]
            rule_counts[rid] = rule_counts.get(rid, 0) + 1
            severity_counts[sev] += 1
            if tr.get("blocking_eligible", False):
                blocking_eligible += 1
        
        # Conflict / Evidence
        if f.get("missing_evidence", False):
            missing_evidence += 1
            
        c = f.get("evidence_completeness", "unknown")
        conflict_completeness[c] = conflict_completeness.get(c, 0) + 1
        
        conf = f.get("confidence", "unknown")
        conflict_confidence[conf] = conflict_confidence.get(conf, 0) + 1
        
        # If rules block but model is very low risk, or rules say fine but model is high risk
        m_prob = f.get("primary_risk_probability", 0.0)
        has_blocking = any(tr.get("blocking_eligible", False) for tr in triggered)
        if (has_blocking and m_prob < 0.10) or (not has_blocking and m_prob > 0.80):
            conflict_model_rule += 1
            
        # SHAP
        shap_ev = f.get("model_evidence", {})
        if shap_ev and isinstance(shap_ev, dict) and "all_contributions" in shap_ev:
            shap_counts += 1
            for sh in shap_ev["all_contributions"]:
                fn = sh["feature"]
                shap_contributions[fn] = shap_contributions.get(fn, []) + [sh["shap_contribution"]]
        elif shap_ev and isinstance(shap_ev, list):
            shap_counts += 1
            for sh in shap_ev:
                fn = sh.get("feature_name", sh.get("feature"))
                if fn:
                    shap_contributions[fn] = shap_contributions.get(fn, []) + [sh.get("shap_contribution", 0.0)]
    rule_metrics = {
        "total_rule_triggers": sum(rule_counts.values()),
        "trigger_count_by_rule": rule_counts,
        "rule_trigger_rate": sum(rule_counts.values()) / len(y_test) if len(y_test) else 0.0,
        "severity_distribution": severity_counts,
        "blocking_eligible_trigger_count": blocking_eligible,
        "missing_unavailable_evidence_count": missing_evidence
    }
    
    evidence_conflicts = {
        "model_rule_conflict": conflict_model_rule,
        "completeness": conflict_completeness,
        "confidence": conflict_confidence
    }
    
    shap_metrics = {}
    if shap_contributions:
        shap_means = {k: float(np.mean(np.abs(v))) for k, v in shap_contributions.items()}
        shap_positive = {k: float(np.mean([x for x in v if x > 0] or [0])) for k, v in shap_contributions.items()}
        shap_negative = {k: float(np.mean([x for x in v if x < 0] or [0])) for k, v in shap_contributions.items()}
        
        top_global = sorted(shap_means.items(), key=lambda x: x[1], reverse=True)[:5]
        top_pos = sorted(shap_positive.items(), key=lambda x: x[1], reverse=True)[:5]
        top_neg = sorted(shap_negative.items(), key=lambda x: x[1], reverse=False)[:5] # most negative
        
        shap_metrics = {
            "test_rows_explained": shap_counts,
            "top_global_mean_abs": dict(top_global),
            "top_positive_contributors": dict(top_pos),
            "top_negative_contributors": dict(top_neg)
        }
        
    t_metric_end = time.time()
    
    performance = {
        "dataset_generation_time": t_gen_end - t_gen_start,
        "feature_generation_time": t_feat_end - t_feat_start,
        "model_fitting_time": t_model_end - t_model_start,
        "calibration_time": t_calib_end - t_calib_start,
        "prediction_time": t_pred_end - t_pred_start,
        "metric_calculation_time": t_metric_end - t_metric_start,
        "total_evaluation_time": t_metric_end - t_start
    }
    
    # 9. JSON Artifact
    artifact = {
        "status": "PASS" if all(leakage_audit.values()) else "FAIL",
        "timestamp": time.time(),
        "model_info": {
            "algorithm": "XGBClassifier",
            "feature_count": len(X_train.columns),
            "features": list(X_train.columns),
            "preprocessing": "StandardScaler + frequency encoding for location",
            "class_weight": "balanced",
            "calibration": "None (Native XGBoost LogLoss)",
            "random_state": 42
        },
        "dataset": dataset_stats,
        "leakage_audit": leakage_audit,
        "classification_metrics": metrics_clf,
        "decision_metrics": decision_metrics,
        "business_cost": business_cost,
        "calibration_metrics": calib_metrics,
        "rule_metrics": rule_metrics,
        "evidence_conflicts": evidence_conflicts,
        "shap_metrics": shap_metrics,
        "performance": performance
    }
    
    with open(EVAL_ARTIFACT_PATH, "w") as f:
        json.dump(artifact, f, indent=2)
        
    logger.info(f"Evaluation complete. Artifact saved to {EVAL_ARTIFACT_PATH}")
    return artifact

if __name__ == "__main__":
    run_evaluation()
