import json
import logging
import numpy as np
import pandas as pd
from sklearn.metrics import confusion_matrix, precision_score, recall_score, f1_score, precision_recall_curve, auc, roc_auc_score, brier_score_loss, log_loss

from data.generator import generate_transactions
from model.dataset_split import split_chronological
from model.feature_engineering import compute_historical_features, fit_transform_features, transform_features, get_feature_matrix, get_target
from model.baseline import train_baseline
from model.calibration import fit_calibration, predict_calibrated_proba
from model.explanation import create_explainer
from model.rule_engine import extract_training_thresholds
from model.decision_engine import DecisionPolicy, make_decision, RULE_BLOCKING_ELIGIBILITY
from model.risk_fusion import fuse_risk_batch

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_evaluation():
    # 1. Regenerate dataset using Phase 21B generator
    logger.info("Generating Phase 21B updated dataset...")
    raw_df = generate_transactions(n=100000, seed=42)
    
    # 2. Historical Feature Engineering
    logger.info("Computing historical features...")
    df_hist = compute_historical_features(raw_df)
    
    # 3. Split
    train_df, val_df, test_df = split_chronological(df_hist)
    
    # 4. Preprocessing
    train_feat, encoder_state = fit_transform_features(train_df)
    test_feat = transform_features(test_df, encoder_state)
    
    X_train = get_feature_matrix(train_feat)
    y_train = get_target(train_feat)
    X_test = get_feature_matrix(test_feat)
    y_test = get_target(test_feat)
    
    # Quality / Leakage Checks
    data_quality = {
        "no_missing_target": bool(y_test.isna().sum() == 0),
        "both_classes_exist": bool(len(y_test.unique()) == 2),
        "feature_columns_match": bool(list(X_train.columns) == list(X_test.columns)),
        "no_target_in_features": bool("is_fraud" not in X_train.columns)
    }
    
    # 5. Fit Model & Artifacts on TRAIN
    logger.info("Fitting Authoritative Pipeline on TRAIN...")
    model_artifact = train_baseline(X_train, y_train, random_state=42)
    calib_artifact = fit_calibration(model_artifact, X_train, y_train, method="none")
    explainer_artifact = create_explainer(model_artifact, X_train)
    rule_thresholds = extract_training_thresholds(X_train)
    
    # 6. Predict on TEST
    logger.info("Evaluating on TEST...")
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
        
    # 7. Metrics calculation
    y_pred_test = (y_prob_calib_test >= 0.40).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_test, y_pred_test).ravel()
    
    precision = precision_score(y_test, y_pred_test, zero_division=0)
    recall = recall_score(y_test, y_pred_test, zero_division=0)
    f1 = f1_score(y_test, y_pred_test, zero_division=0)
    roc_auc = roc_auc_score(y_test, y_prob_calib_test)
    precision_curve, recall_curve, _ = precision_recall_curve(y_test, y_prob_calib_test)
    pr_auc = auc(recall_curve, precision_curve)
    brier = brier_score_loss(y_test, y_prob_calib_test)
    ll = log_loss(y_test, y_prob_calib_test)
    accuracy = (tp + tn) / len(y_test)
    specificity = tn / (tn + fp) if (tn + fp) > 0 else 0
    fpr = fp / (fp + tn) if (fp + tn) > 0 else 0
    fnr = fn / (fn + tp) if (fn + tp) > 0 else 0
    
    classification_metrics = {
        "tp": int(tp), "tn": int(tn), "fp": int(fp), "fn": int(fn),
        "precision": float(precision), "recall": float(recall), "f1": float(f1),
        "roc_auc": float(roc_auc), "pr_auc": float(pr_auc),
        "accuracy": float(accuracy), "specificity": float(specificity),
        "fpr": float(fpr), "fnr": float(fnr)
    }
    
    # Decisions
    dec_df = pd.DataFrame([{"decision": d["decision"], "is_fraud": y} for d, y in zip(decisions, y_test)])
    legit_counts = dec_df[dec_df["is_fraud"] == 0]["decision"].value_counts().to_dict()
    fraud_counts = dec_df[dec_df["is_fraud"] == 1]["decision"].value_counts().to_dict()
    
    decision_metrics = {
        "legit_allow": legit_counts.get("ALLOW", 0),
        "legit_review": legit_counts.get("REVIEW", 0),
        "legit_block": legit_counts.get("BLOCK", 0),
        "fraud_allow": fraud_counts.get("ALLOW", 0),
        "fraud_review": fraud_counts.get("REVIEW", 0),
        "fraud_block": fraud_counts.get("BLOCK", 0)
    }
    
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
        "avg_cost_per_transaction": total_cost / len(y_test) if len(y_test) else 0,
        "avg_cost_per_fraud": (cost_fraud_allow + cost_fraud_review) / sum(fraud_counts.values()) if sum(fraud_counts.values()) else 0,
        "avg_cost_per_legit": (cost_legit_review + cost_legit_block) / sum(legit_counts.values()) if sum(legit_counts.values()) else 0
    }
    
    # Probabilities
    prob_dist = {
        "min": float(y_prob_calib_test.min()),
        "max": float(y_prob_calib_test.max()),
        "median": float(np.median(y_prob_calib_test)),
        "q25": float(np.percentile(y_prob_calib_test, 25)),
        "q75": float(np.percentile(y_prob_calib_test, 75)),
        "num_geq_10": int((y_prob_calib_test >= 0.10).sum()),
        "num_geq_40": int((y_prob_calib_test >= 0.40).sum()),
        "brier": float(brier),
        "log_loss": float(ll)
    }
    
    # Rule Evidence & Conflict & SHAP
    rule_counts = {}
    severity_counts = {"INFO": 0, "LOW": 0, "MEDIUM": 0, "HIGH": 0}
    blocking_eligible_triggers = 0
    
    qual_but_rejected = 0
    
    model_rule_conflicts = 0
    
    shap_contributions = {}
    

    for i, f in enumerate(fusion_results):
        r_ev = f.get("rule_evidence", {})
        triggered = r_ev.get("triggered_rules", [])
        for tr in triggered:
            rid = tr["rule_id"]
            sev = tr["severity"]
            rule_counts[rid] = rule_counts.get(rid, 0) + 1
            severity_counts[sev] += 1
            
            is_eligible = RULE_BLOCKING_ELIGIBILITY.get(rid, False)
            if sev in ["MEDIUM", "HIGH"] and is_eligible:
                blocking_eligible_triggers += 1
                
        prob = f.get("fusion_summary", {}).get("primary_risk_probability", 0.0)
        has_block_rule = any(RULE_BLOCKING_ELIGIBILITY.get(tr["rule_id"], False) and tr["severity"] in ["MEDIUM", "HIGH"] for tr in triggered)
        
        if prob >= 0.40 and not has_block_rule:
            qual_but_rejected += 1
            
        if (has_block_rule and prob < 0.10) or (not has_block_rule and prob > 0.80):
            model_rule_conflicts += 1

            
        shap_ev = f.get("model_evidence", {})
        if shap_ev and isinstance(shap_ev, dict) and "all_contributions" in shap_ev:
            for sh in shap_ev["all_contributions"]:
                fn = sh["feature"]
                shap_contributions[fn] = shap_contributions.get(fn, []) + [sh["shap_contribution"]]
    
    shap_means = {k: float(np.mean(np.abs(v))) for k, v in shap_contributions.items()} if shap_contributions else {}
    shap_positive = {k: float(np.mean([x for x in v if x > 0] or [0])) for k, v in shap_contributions.items()} if shap_contributions else {}
    shap_negative = {k: float(np.mean([x for x in v if x < 0] or [0])) for k, v in shap_contributions.items()} if shap_contributions else {}
    
    artifact = {
        "dataset_rows": len(y_test),
        "fraud_rows": int(sum(fraud_counts.values())),
        "legitimate_rows": int(sum(legit_counts.values())),
        "fraud_prevalence": float(sum(fraud_counts.values()) / len(y_test)),
        "classification_metrics": classification_metrics,
        "decision_metrics": decision_metrics,
        "business_cost": business_cost,
        "probability_distribution": prob_dist,
        "rule_triggers": rule_counts,
        "severity_distribution": severity_counts,
        "blocking_eligible_triggers": blocking_eligible_triggers,
        "qual_but_rejected": qual_but_rejected,
        "model_rule_conflicts": model_rule_conflicts,
        "shap": {
            "top_global_mean_abs": dict(sorted(shap_means.items(), key=lambda x: x[1], reverse=True)[:5]),
            "top_positive": dict(sorted(shap_positive.items(), key=lambda x: x[1], reverse=True)[:5]),
            "top_negative": dict(sorted(shap_negative.items(), key=lambda x: x[1], reverse=False)[:5])
        },
        "data_quality": data_quality
    }
    
    with open("model/final_test_evaluation_artifact.json", "w") as f:
        json.dump(artifact, f, indent=2)
        
    logger.info("Final test evaluation complete.")
    return artifact

if __name__ == "__main__":
    run_evaluation()

