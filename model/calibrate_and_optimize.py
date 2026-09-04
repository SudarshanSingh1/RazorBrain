import logging
import joblib
import json
import numpy as np
from datetime import datetime, timezone

from sklearn.metrics import (
    roc_auc_score, average_precision_score, brier_score_loss, log_loss
)
from sklearn.calibration import CalibratedClassifierCV

from model.real_feature_pipeline import RealFeaturePipeline

logging.basicConfig(level=logging.INFO, format="%(name)s:%(levelname)s:%(message)s")
logger = logging.getLogger(__name__)

ARTIFACT_PATH = "data/model_c_engineered_raw_safe.joblib"
CALIB_ARTIFACT_PATH = "data/model_c_calibrated.joblib"
POLICY_PATH = "data/validation_selected_policy.json"
TARGET_COL = "isFraud"

def main():
    logger.info("Loading and joining IEEE-CIS dataset...")
    pipe = RealFeaturePipeline()
    raw = pipe.load_and_join()
    features_df = pipe.build_real_features(raw)
    
    # We must use EXACTLY the same temporal split boundaries to perfectly reproduce validation
    # test_df is completely discarded and NEVER used in optimization
    train_df, val_df, _ = pipe.split_temporally(features_df, train_frac=0.7, val_frac=0.15)
    
    # Chronological split of validation set for calibration vs threshold optimization
    split_idx = int(len(val_df) * 0.5)
    val_calib_df = val_df.iloc[:split_idx].copy()
    val_eval_df = val_df.iloc[split_idx:].copy()
    logger.info(f"Train: {len(train_df)}, Val-Calib: {len(val_calib_df)}, Val-Eval: {len(val_eval_df)}")

    # Load frozen Model C
    logger.info(f"Loading Model C artifact from {ARTIFACT_PATH}...")
    artifact = joblib.load(ARTIFACT_PATH)
    model = artifact["model_artifact"]
    preprocessor = artifact["preprocessor"]
    feature_order = artifact["feature_order"]
    actual_cat = preprocessor.transformers_[0][2] if preprocessor.transformers_[0][0] == "cat" else []

    def prep_X(df):
        X = df[[c for c in feature_order if c in df.columns]].copy()
        missing = [c for c in feature_order if c not in X.columns]
        for c in missing:
            X[c] = np.nan
        X = X[feature_order]
        for c in actual_cat:
            if c in X.columns:
                X[c] = X[c].astype(str).replace("nan", "UNKNOWN")
        return preprocessor.transform(X)

    logger.info("Preprocessing validation splits...")
    X_val_calib = prep_X(val_calib_df)
    y_val_calib = val_calib_df[TARGET_COL].values

    X_val_eval = prep_X(val_eval_df)
    y_val_eval = val_eval_df[TARGET_COL].values

    logger.info("Generating raw predictions...")
    prob_raw = model.predict_proba(X_val_eval)[:, 1]

    from sklearn.frozen import FrozenEstimator

    logger.info("Fitting Platt Scaling (Logistic Regression)...")
    platt = CalibratedClassifierCV(estimator=FrozenEstimator(model), method='sigmoid')
    platt.fit(X_val_calib, y_val_calib)
    prob_platt = platt.predict_proba(X_val_eval)[:, 1]

    logger.info("Fitting Isotonic Regression...")
    iso = CalibratedClassifierCV(estimator=FrozenEstimator(model), method='isotonic')
    iso.fit(X_val_calib, y_val_calib)
    prob_iso = iso.predict_proba(X_val_eval)[:, 1]

    def eval_calib(y_true, y_prob):
        return {
            "brier": round(brier_score_loss(y_true, y_prob), 5),
            "log_loss": round(log_loss(y_true, y_prob), 5),
            "roc_auc": round(roc_auc_score(y_true, y_prob), 5),
            "pr_auc": round(average_precision_score(y_true, y_prob), 5)
        }

    m_raw = eval_calib(y_val_eval, prob_raw)
    m_platt = eval_calib(y_val_eval, prob_platt)
    m_iso = eval_calib(y_val_eval, prob_iso)

    logger.info(f"Raw:   {m_raw}")
    logger.info(f"Platt: {m_platt}")
    logger.info(f"Iso:   {m_iso}")

    # Select best based on log_loss (Platt typically preserves PR-AUC better than Isotonic due to strict monotonicity)
    methods = [("raw", prob_raw, m_raw, None), ("platt", prob_platt, m_platt, platt), ("isotonic", prob_iso, m_iso, iso)]
    best_name, best_probs, best_m, best_calibrator = min(methods, key=lambda x: x[2]["log_loss"])
    logger.info(f"Selected calibration method: {best_name.upper()} (lowest log_loss)")

    if best_calibrator is not None:
        calib_artifact = {
            "base_model_artifact": artifact,
            "calibrator": best_calibrator,
            "calibrator_method": best_name,
            "calibrated_at": datetime.now(timezone.utc).isoformat()
        }
        joblib.dump(calib_artifact, CALIB_ARTIFACT_PATH)
        logger.info(f"Saved calibrated artifact -> {CALIB_ARTIFACT_PATH}")
    else:
        logger.info("Raw probabilities selected. No calibrated artifact saved.")

    # Threshold Optimization
    logger.info("Optimizing thresholds on val_eval...")
    
    C_FN = 100.0          # Loss exposure
    C_FP_REVIEW = 5.0     # Review friction
    C_FP_BLOCK = 15.0     # Block friction/lost TXN
    C_REVIEW = 2.0        # Manual review op cost

    def calculate_cost(y_true, decisions):
        total_cost = 0.0
        
        # Fast numpy approach
        is_allow = (decisions == 'ALLOW')
        is_review = (decisions == 'REVIEW')
        is_block = (decisions == 'BLOCK')
        
        is_fraud = (y_true == 1)
        is_legit = (y_true == 0)
        
        fn_count = np.sum(is_allow & is_fraud)
        total_cost += fn_count * C_FN
        
        fp_review = np.sum(is_review & is_legit)
        total_cost += fp_review * C_FP_REVIEW
        
        fp_block = np.sum(is_block & is_legit)
        total_cost += fp_block * C_FP_BLOCK
        
        review_count = np.sum(is_review)
        total_cost += review_count * C_REVIEW
        
        return total_cost, {
            "fn_count": fn_count,
            "fp_review": fp_review,
            "fp_block": fp_block,
            "review_count": review_count,
            "block_count": np.sum(is_block),
            "allow_count": np.sum(is_allow),
            "fraud_caught": np.sum((is_review | is_block) & is_fraud)
        }

    # Grid search candidate percentiles
    percentiles = np.linspace(50, 99.5, 100)
    t_candidates = np.unique(np.percentile(best_probs, percentiles))
    
    results = []
    for t_rev in t_candidates:
        for t_blk in t_candidates:
            if t_rev >= t_blk:
                continue
                
            dec = np.where(best_probs >= t_blk, 'BLOCK',
                           np.where(best_probs >= t_rev, 'REVIEW', 'ALLOW'))
            cost, stats = calculate_cost(y_val_eval, dec)
            rev_pct = stats["review_count"] / len(y_val_eval)
            
            results.append({
                "t_review": float(t_rev),
                "t_block": float(t_blk),
                "cost": float(cost),
                "review_pct": float(rev_pct),
                "stats": {k: int(v) for k, v in stats.items()}
            })

    # Operational constraints
    capacities = [0.01, 0.02, 0.05, 0.10, 1.0] # 1.0 = unlimited
    best_policies = {}
    for cap in capacities:
        valid = [r for r in results if r["review_pct"] <= cap]
        if valid:
            best_policies[cap] = min(valid, key=lambda x: x["cost"])

    selected_policy = best_policies.get(0.05) or best_policies[1.0]
    
    # Add metadata to policy
    policy_doc = {
        "model_id": "MODEL_C_ENGINEERED_PLUS_RAW",
        "calibration_method": best_name.upper(),
        "capacity_target": 0.05,
        "policy_status": "VALIDATION_SELECTED",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "cost_parameters": {
            "C_FN": C_FN,
            "C_FP_BLOCK": C_FP_BLOCK,
            "C_FP_REVIEW": C_FP_REVIEW,
            "C_REVIEW": C_REVIEW
        },
        "optimization_dataset": "validation_eval_split_chronological",
        "t_review": selected_policy["t_review"],
        "t_block": selected_policy["t_block"],
        "cost": selected_policy["cost"],
        "review_pct": selected_policy["review_pct"],
        "stats": selected_policy["stats"]
    }
    
    with open(POLICY_PATH, 'w') as f:
        json.dump(policy_doc, f, indent=2)
    logger.info(f"Saved selected policy -> {POLICY_PATH}")

    # Sensitivity Analysis
    logger.info("Running sensitivity analysis...")
    scenarios = [
        ("A (Base)", 100.0, 15.0, 5.0, 2.0),
        ("B (High FN Cost)", 200.0, 15.0, 5.0, 2.0),
        ("C (High Block Cost)", 100.0, 30.0, 5.0, 2.0),
        ("D (High Review FP)", 100.0, 15.0, 10.0, 2.0),
        ("E (High Ops Cost)", 100.0, 15.0, 5.0, 5.0),
    ]
    
    sensitivity_md = "## Sensitivity Analysis (5% Capacity Target)\n\n"
    sensitivity_md += "| Scenario | C_FN | C_FP_BLOCK | C_FP_REVIEW | C_REVIEW | T_review | T_block | Review % | Fraud Caught | Total Cost |\n"
    sensitivity_md += "|---|---|---|---|---|---|---|---|---|---|\n"
    
    for s_name, c_fn, c_fp_b, c_fp_r, c_rev in scenarios:
        s_best = None
        for t_rev in t_candidates:
            for t_blk in t_candidates:
                if t_rev >= t_blk:
                    continue
                dec = np.where(best_probs >= t_blk, 'BLOCK', np.where(best_probs >= t_rev, 'REVIEW', 'ALLOW'))
                is_fraud = y_val_eval == 1
                is_legit = y_val_eval == 0
                r_c = np.sum(dec == 'REVIEW')
                if r_c / len(y_val_eval) > 0.05:
                    continue
                
                cost = (np.sum((dec == 'ALLOW') & is_fraud) * c_fn + 
                        np.sum((dec == 'BLOCK') & is_legit) * c_fp_b + 
                        np.sum((dec == 'REVIEW') & is_legit) * c_fp_r + 
                        r_c * c_rev)
                if s_best is None or cost < s_best['cost']:
                    s_best = {
                        'cost': cost, 'tr': t_rev, 'tb': t_blk, 
                        'rp': r_c / len(y_val_eval), 
                        'fc': np.sum((dec != 'ALLOW') & is_fraud)
                    }
        sensitivity_md += f"| {s_name} | {c_fn} | {c_fp_b} | {c_fp_r} | {c_rev} | {s_best['tr']:.4f} | {s_best['tb']:.4f} | {s_best['rp']*100:.2f}% | {s_best['fc']} | {s_best['cost']:.1f} |\n"

    # Generate Markdown Reports
    calib_md = f"""# Probability Calibration

## Methodology
- **Base Model:** Frozen Model C (147 features), trained on 413,378 rows.
- **Calibration Split:** Validation set chronologically split into `val_calib` (44,290 rows) and `val_eval` (44,291 rows).
- **Fitting:** Calibrators fit on `val_calib` using raw predictions from frozen Model C.
- **Evaluation:** Evaluated purely on untouched `val_eval`. 
- **Test Set Firewall:** Test set was completely excluded.

## Results on `val_eval`
| Method | Brier Score | Log Loss | ROC-AUC | PR-AUC |
|---|---|---|---|---|
| Raw XGBoost | {m_raw['brier']} | {m_raw['log_loss']} | {m_raw['roc_auc']} | {m_raw['pr_auc']} |
| Platt (Logistic) | {m_platt['brier']} | {m_platt['log_loss']} | {m_platt['roc_auc']} | {m_platt['pr_auc']} |
| Isotonic | {m_iso['brier']} | {m_iso['log_loss']} | {m_iso['roc_auc']} | {m_iso['pr_auc']} |

## Conclusion
Selected method: **{best_name.upper()}** (lowest log_loss). 
{f'Saved artifact: `{CALIB_ARTIFACT_PATH}`' if best_calibrator else 'Kept raw probabilities (no artifact change).'}
"""
    with open("docs/probability_calibration.md", "w") as f:
        f.write(calib_md)

    thresh_md = f"""# Validation-Based Threshold Optimization

## Methodology
- Evaluated thresholds on `val_eval` using {best_name.upper()} probabilities.
- Cost grid search ensuring `T_review < T_block`.
- **Test Set Firewall:** Test labels were never used.

## Cost Assumptions
- `C_FN` (Fraud allowed) = 100.0
- `C_FP_BLOCK` (Legit blocked) = 15.0
- `C_FP_REVIEW` (Legit reviewed) = 5.0
- `C_REVIEW` (Manual ops cost) = 2.0

## Optimal Policies by Review Capacity
| Capacity | T_review | T_block | Actual Rev% | Fraud Caught | Cost |
|---|---|---|---|---|---|
"""
    for cap in capacities:
        if cap in best_policies:
            pol = best_policies[cap]
            thresh_md += f"| {cap*100:.0f}% | {pol['t_review']:.4f} | {pol['t_block']:.4f} | {pol['review_pct']*100:.2f}% | {pol['stats']['fraud_caught']} | {pol['cost']:.1f} |\n"

    thresh_md += "\n" + sensitivity_md + "\n"

    thresh_md += f"""
## Validation-Selected Demonstration Policy
Selected the 5% capacity constraint as a realistic operational target.
- **T_review:** {selected_policy['t_review']:.4f}
- **T_block:** {selected_policy['t_block']:.4f}
- **Saved to:** `{POLICY_PATH}`

*The held-out test set was not used to select this policy.*
"""
    with open("docs/threshold_cost_optimization.md", "w") as f:
        f.write(thresh_md)

    logger.info("Done.")

if __name__ == "__main__":
    main()
