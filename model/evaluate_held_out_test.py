"""
HELD-OUT TEST SET EVALUATION — ONE-TIME, IRREVERSIBLE.

Evaluates MODEL C exactly once on the untouched held-out test split.
No tuning, no calibration, no model modification after this run.
"""
import logging
import joblib
import numpy as np

from sklearn.metrics import (
    roc_auc_score, average_precision_score,
    precision_score, recall_score, f1_score, confusion_matrix,
)

from model.real_feature_pipeline import RealFeaturePipeline

logging.basicConfig(level=logging.INFO, format="%(name)s:%(levelname)s:%(message)s")
logger = logging.getLogger(__name__)

ARTIFACT_PATH = "data/model_c_engineered_raw_safe.joblib"
TARGET_COL = "isFraud"
THRESHOLD = 0.5   # SAME threshold used in validation comparison — not re-optimized


def _metrics(y_true, y_prob, threshold):
    y_pred = (y_prob >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred).ravel()
    return dict(
        roc_auc=round(roc_auc_score(y_true, y_prob), 4),
        pr_auc=round(average_precision_score(y_true, y_prob), 4),
        precision=round(precision_score(y_true, y_pred, zero_division=0), 4),
        recall=round(recall_score(y_true, y_pred, zero_division=0), 4),
        f1=round(f1_score(y_true, y_pred, zero_division=0), 4),
        fpr=round(fp / (fp + tn + 1e-9), 4),
        fnr=round(fn / (fn + tp + 1e-9), 4),
        specificity=round(tn / (tn + fp + 1e-9), 4),
        tp=int(tp), fp=int(fp), fn=int(fn), tn=int(tn),
    )


def main():
    # ──────────────────────────────────────────────────────────
    # 1. Load artifact (no refit)
    # ──────────────────────────────────────────────────────────
    logger.info(f"Loading Model C artifact from {ARTIFACT_PATH}...")
    artifact = joblib.load(ARTIFACT_PATH)
    model        = artifact["model_artifact"]
    preprocessor = artifact["preprocessor"]
    feature_order = artifact["feature_order"]   # 147 source columns in deterministic order
    actual_cat   = preprocessor.transformers_[0][2] if preprocessor.transformers_[0][0] == "cat" else []
    logger.info(f"Model ID: {artifact['model_id']}")
    logger.info(f"Feature order: {len(feature_order)} source columns")
    logger.info(f"Transformed dim: {artifact['transformed_dim']}")
    logger.info(f"Trained on: {artifact['train_rows']} rows")
    logger.info(f"Validation rows: {artifact['val_rows']}")

    # Retrieve stored train/val metrics for gap calculation
    stored_train = artifact["train_metrics"]
    stored_val   = artifact["val_metrics"]

    # ──────────────────────────────────────────────────────────
    # 2. Rebuild the FULL feature table (all three splits)
    #    then slice only the test split.
    #    The pipeline builds strictly-prior aggregates using ALL
    #    chronologically preceding rows — train/val rows inform
    #    the historical state for test transactions.
    # ──────────────────────────────────────────────────────────
    logger.info("Loading and joining IEEE-CIS dataset...")
    pipe = RealFeaturePipeline()
    raw  = pipe.load_and_join()
    logger.info(f"Raw rows: {len(raw)}")

    logger.info("Building full feature table (ENGINEERED_CORE + RAW_SAFE)...")
    features_df = pipe.build_real_features(raw)
    logger.info("Feature contract validation...")
    assert pipe.validate_feature_contract(features_df), "Contract FAILED — aborting"

    # Chronological split — identical boundaries as training
    train_df, val_df, test_df = pipe.split_temporally(features_df, train_frac=0.7, val_frac=0.15)
    logger.info(f"Train={len(train_df)}  Val={len(val_df)}  Test={len(test_df)}")

    # ──────────────────────────────────────────────────────────
    # 3. Verify test immutability assertions
    # ──────────────────────────────────────────────────────────
    assert set(train_df["TransactionID"]).isdisjoint(set(test_df["TransactionID"])), \
        "INTEGRITY ERROR: train and test share TransactionIDs"
    assert set(val_df["TransactionID"]).isdisjoint(set(test_df["TransactionID"])), \
        "INTEGRITY ERROR: val and test share TransactionIDs"
    assert train_df["TransactionDT"].max() < test_df["TransactionDT"].min(), \
        "INTEGRITY ERROR: train bleeds into test temporally"
    assert val_df["TransactionDT"].max() <= test_df["TransactionDT"].min(), \
        "INTEGRITY ERROR: val bleeds into test temporally"
    logger.info("Test immutability: PASS (no ID overlap, no temporal bleed)")

    # ──────────────────────────────────────────────────────────
    # 4. Prepare test X — use EXACT feature_order from artifact
    # ──────────────────────────────────────────────────────────
    missing_from_test = [c for c in feature_order if c not in test_df.columns]
    if missing_from_test:
        logger.warning(f"Missing from test table (will be 0-imputed): {missing_from_test}")

    X_test = test_df[[c for c in feature_order if c in test_df.columns]].copy()
    for c in missing_from_test:
        X_test[c] = np.nan
    X_test = X_test[feature_order]   # enforce exact column order
    y_test = test_df[TARGET_COL]

    # Cast categoricals (same as during training)
    for c in actual_cat:
        if c in X_test.columns:
            X_test[c] = X_test[c].astype(str).replace("nan", "UNKNOWN")

    # ──────────────────────────────────────────────────────────
    # 5. Score — NO refit, NO modification
    # ──────────────────────────────────────────────────────────
    logger.info("Running inference with frozen preprocessor + frozen model...")
    X_test_enc = preprocessor.transform(X_test)
    prob_test  = model.predict_proba(X_test_enc)[:, 1]
    logger.info("Inference complete.")

    # ──────────────────────────────────────────────────────────
    # 6. Metrics
    # ──────────────────────────────────────────────────────────
    test_m = _metrics(y_test, prob_test, THRESHOLD)

    fraud_count = int(y_test.sum())
    legit_count = int((y_test == 0).sum())
    fraud_rate  = round(y_test.mean(), 4)

    # Score distribution
    pcts = [0, 25, 50, 75, 90, 95, 99, 100]
    score_dist = {f"p{p}" if p not in (0, 100) else ("min" if p == 0 else "max"):
                  round(float(np.percentile(prob_test, p)), 6) for p in pcts}

    # Fraud vs legit score separation
    fraud_probs = prob_test[y_test.values == 1]
    legit_probs = prob_test[y_test.values == 0]

    # Gaps
    train_val_roc = round(stored_train["roc_auc"] - stored_val["roc_auc"], 4)
    train_val_pr  = round(stored_train["pr_auc"]  - stored_val["pr_auc"],  4)
    val_test_roc  = round(stored_val["roc_auc"]   - test_m["roc_auc"],  4)
    val_test_pr   = round(stored_val["pr_auc"]    - test_m["pr_auc"],   4)
    train_test_roc= round(stored_train["roc_auc"] - test_m["roc_auc"],  4)
    train_test_pr = round(stored_train["pr_auc"]  - test_m["pr_auc"],   4)

    # ──────────────────────────────────────────────────────────
    # 7. Print report
    # ──────────────────────────────────────────────────────────
    print("\n" + "="*70)
    print("HELD-OUT REAL TEST EVALUATION")
    print("="*70)
    print("MODEL:              Model C — ENGINEERED_CORE + RAW_SAFE")
    print(f"TEST ROWS:          {len(y_test)}")
    print(f"TEST FRAUD COUNT:   {fraud_count}")
    print(f"TEST LEGIT COUNT:   {legit_count}")
    print(f"TEST FRAUD RATE:    {fraud_rate}")
    print(f"EVALUATION THRESHOLD: {THRESHOLD}  [EXPERIMENTAL — NOT PRODUCTION]")
    print()
    print(f"TEST ROC-AUC:       {test_m['roc_auc']}")
    print(f"TEST PR-AUC:        {test_m['pr_auc']}")
    print(f"TEST PRECISION:     {test_m['precision']}")
    print(f"TEST RECALL:        {test_m['recall']}")
    print(f"TEST F1:            {test_m['f1']}")
    print(f"TEST FPR:           {test_m['fpr']}")
    print(f"TEST FNR:           {test_m['fnr']}")
    print(f"TEST SPECIFICITY:   {test_m['specificity']}")
    print()
    print("CONFUSION MATRIX:")
    print(f"  TN: {test_m['tn']}   FP: {test_m['fp']}")
    print(f"  FN: {test_m['fn']}   TP: {test_m['tp']}")
    print()
    print("TRAIN → VALIDATION:")
    print(f"  ROC-AUC GAP: {train_val_roc:+.4f}")
    print(f"  PR-AUC GAP:  {train_val_pr:+.4f}")
    print()
    print("VALIDATION → TEST:")
    print(f"  ROC-AUC GAP: {val_test_roc:+.4f}")
    print(f"  PR-AUC GAP:  {val_test_pr:+.4f}")
    print()
    print("TRAIN → TEST:")
    print(f"  ROC-AUC GAP: {train_test_roc:+.4f}")
    print(f"  PR-AUC GAP:  {train_test_pr:+.4f}")
    print()
    print("TEST SCORE DISTRIBUTION:")
    for k, v in score_dist.items():
        print(f"  {k.upper():>4}: {v:.6f}")
    print()
    print(f"RISK PROBABILITIES — mean={fraud_probs.mean():.4f}  median={np.median(fraud_probs):.4f}  p90={np.percentile(fraud_probs,90):.4f}")
    print(f"LEGIT PROBABILITIES — mean={legit_probs.mean():.4f}  median={np.median(legit_probs):.4f}  p90={np.percentile(legit_probs,90):.4f}")
    print()
    print("─"*40)
    print(f"TRAIN ROC-AUC:  {stored_train['roc_auc']}  |  VAL ROC-AUC:  {stored_val['roc_auc']}  |  TEST ROC-AUC:  {test_m['roc_auc']}")
    print(f"TRAIN PR-AUC:   {stored_train['pr_auc']}  |  VAL PR-AUC:   {stored_val['pr_auc']}  |  TEST PR-AUC:   {test_m['pr_auc']}")
    print()
    print("TEST USED FOR MODEL SELECTION:    NO")
    print("TEST USED FOR THRESHOLD SELECTION: NO")
    print("TEST USED FOR CALIBRATION:        NO")
    print("MODEL MODIFIED AFTER TEST:        NO")

    return test_m, stored_train, stored_val, score_dist, fraud_probs, legit_probs, {
        "fraud_count": fraud_count,
        "legit_count": legit_count,
        "fraud_rate": fraud_rate,
        "train_val_roc": train_val_roc,
        "train_val_pr": train_val_pr,
        "val_test_roc": val_test_roc,
        "val_test_pr": val_test_pr,
        "train_test_roc": train_test_roc,
        "train_test_pr": train_test_pr,
    }


if __name__ == "__main__":
    main()
