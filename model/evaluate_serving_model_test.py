"""
Razorpay Serving Model — Held-Out Test Evaluation.
Evaluation-only. No retraining. No preprocessing fitting.
No calibration. No threshold optimization.
"""
import hashlib
import json
import logging

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# --- Paths (read-only) ---
MODEL_PATH = "data/razorpay_serving_model_uncalibrated.joblib"
TEST_PATH = "data/razorpay_serving_dataset/test.csv"
TRAIN_PATH = "data/razorpay_serving_dataset/train.csv"
VAL_PATH = "data/razorpay_serving_dataset/validation.csv"
METRICS_PATH = "data/razorpay_serving_model_metrics.json"
CONTRACT_PATH = "data/razorpay_serving_feature_contract.json"
OUTPUT_PATH = "data/razorpay_serving_test_evaluation.json"

KNOWN_HASHES = {
    MODEL_PATH: "1242b74830962d8d323676563648ffdb",
    TEST_PATH: "fc4e76764a2e7ad1df631ce37d050f35",
    "data/model_c_calibrated.joblib": "17eaa5aad2a2672f497221362ee4cefd",
    "data/model_c_engineered_raw_safe.joblib": "7de3be91a463ce8d9c74193869212aea",
    "data/validation_selected_policy.json": "a6f2994d904e4dab0bb8ceca52924106",
}

REJECTED_FEATURES = {
    "isFraud", "TransactionID", "TransactionDT",
    "addr1", "addr2", "dist1", "R_emaildomain",
    "card2", "card3", "card5", "DeviceType",
}


def md5(path: str) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_hashes():
    logger.info("Verifying artifact hashes...")
    for path, expected in KNOWN_HASHES.items():
        actual = md5(path)
        if actual != expected:
            raise RuntimeError(f"INTEGRITY FAILURE: {path}\n  Expected: {expected}\n  Got:      {actual}")
    logger.info("All artifact hashes verified OK.")


def load_contract():
    with open(CONTRACT_PATH) as f:
        contract = json.load(f)
    return [feat["name"] for feat in contract["features"]]


def check_no_overlap(train_df, val_df, test_df):
    train_ids = set(train_df["TransactionID"])
    val_ids = set(val_df["TransactionID"])
    test_ids = set(test_df["TransactionID"])
    assert len(train_ids & test_ids) == 0, "LEAKAGE: train/test overlap"
    assert len(val_ids & test_ids) == 0, "LEAKAGE: validation/test overlap"
    logger.info("No train/test or val/test overlap detected.")


def check_chronological_order(train_df, val_df, test_df):
    assert train_df["TransactionDT"].max() < val_df["TransactionDT"].min(), \
        "Chronological violation: train extends into validation"
    assert val_df["TransactionDT"].max() < test_df["TransactionDT"].min(), \
        "Chronological violation: validation extends into test"
    logger.info("Chronological ordering verified: train < validation < test.")


def score_distribution(scores: np.ndarray) -> dict:
    return {
        "min": float(np.min(scores)),
        "p25": float(np.percentile(scores, 25)),
        "p50": float(np.percentile(scores, 50)),
        "p75": float(np.percentile(scores, 75)),
        "p90": float(np.percentile(scores, 90)),
        "p95": float(np.percentile(scores, 95)),
        "p99": float(np.percentile(scores, 99)),
        "max": float(np.max(scores)),
    }


def class_score_stats(scores: np.ndarray, labels: np.ndarray, cls: int) -> dict:
    subset = scores[labels == cls]
    return {
        "mean": float(np.mean(subset)),
        "median": float(np.median(subset)),
        "p90": float(np.percentile(subset, 90)),
    }


def evaluate():
    verify_hashes()

    # --- Load artifact (no retraining) ---
    artifact = joblib.load(MODEL_PATH)
    pipeline = artifact["model_artifact"]
    metadata = artifact["metadata"]

    assert metadata["selected_model"] == "XGBoost", \
        f"Expected XGBoost, got {metadata['selected_model']}"
    assert metadata["features"] == load_contract(), \
        "Feature list in artifact does not match contract"
    logger.info(f"Artifact loaded — model: {metadata['selected_model']}, version: {metadata['version']}")

    # --- Load datasets ---
    logger.info("Loading datasets...")
    test_df = pd.read_csv(TEST_PATH)
    train_df = pd.read_csv(TRAIN_PATH)
    val_df = pd.read_csv(VAL_PATH)

    # --- Structural checks ---
    features = metadata["features"]
    for feat in REJECTED_FEATURES:
        assert feat not in features, f"Rejected feature in contract: {feat}"

    check_no_overlap(train_df, val_df, test_df)
    check_chronological_order(train_df, val_df, test_df)

    # --- Isolate test features and labels (labels only used for metrics) ---
    X_test = test_df[features]
    y_test = test_df["isFraud"].values  # used ONLY in metric calculation below

    # --- Inference (no fitting, no calibration) ---
    logger.info("Running inference on frozen test set...")
    scores = pipeline.predict_proba(X_test)[:, 1]  # uncalibrated probability

    # --- Metrics at threshold=0.50 ---
    preds = (scores >= 0.50).astype(int)

    roc_auc = roc_auc_score(y_test, scores)
    pr_auc = average_precision_score(y_test, scores)
    precision = precision_score(y_test, preds)
    recall = recall_score(y_test, preds)
    f1 = f1_score(y_test, preds)
    tn, fp, fn, tp = confusion_matrix(y_test, preds).ravel()
    fpr = fp / (fp + tn)
    fnr = fn / (fn + tp)
    specificity = tn / (tn + fp)

    n_total = len(y_test)
    n_fraud = int(y_test.sum())
    n_legit = n_total - n_fraud
    prevalence = n_fraud / n_total

    # --- Score distributions ---
    dist_all = score_distribution(scores)
    dist_fraud = class_score_stats(scores, y_test, cls=1)
    dist_legit = class_score_stats(scores, y_test, cls=0)

    # --- Load prior metrics for gap analysis ---
    with open(METRICS_PATH) as f:
        prior_metrics = json.load(f)

    # Recompute train metrics (train data, same frozen model)
    X_train = train_df[features]
    y_train = train_df["isFraud"].values
    train_scores = pipeline.predict_proba(X_train)[:, 1]
    train_roc = roc_auc_score(y_train, train_scores)
    train_pr = average_precision_score(y_train, train_scores)

    val_roc = prior_metrics["selected"]["roc_auc"]
    val_pr = prior_metrics["selected"]["pr_auc"]

    # --- Log results ---
    logger.info("=== RAZORPAY SERVING MODEL — HELD-OUT TEST EVALUATION ===")
    logger.info(f"Test rows: {n_total} | Fraud: {n_fraud} | Legit: {n_legit} | Prevalence: {prevalence:.4f}")
    logger.info(f"ROC-AUC: {roc_auc:.4f} | PR-AUC: {pr_auc:.4f}")
    logger.info(f"Precision: {precision:.4f} | Recall: {recall:.4f} | F1: {f1:.4f}")
    logger.info(f"Specificity: {specificity:.4f} | FPR: {fpr:.4f} | FNR: {fnr:.4f}")
    logger.info(f"Confusion: TN={tn}, FP={fp}, FN={fn}, TP={tp}")
    logger.info(f"TRAIN   ROC-AUC={train_roc:.4f}  PR-AUC={train_pr:.4f}")
    logger.info(f"VAL     ROC-AUC={val_roc:.4f}  PR-AUC={val_pr:.4f}")
    logger.info(f"TEST    ROC-AUC={roc_auc:.4f}  PR-AUC={pr_auc:.4f}")
    logger.info(f"Gap (val→test) ROC-AUC={roc_auc - val_roc:+.4f}  PR-AUC={pr_auc - val_pr:+.4f}")
    logger.info(f"Gap (train→test) ROC-AUC={roc_auc - train_roc:+.4f}  PR-AUC={pr_auc - train_pr:+.4f}")
    logger.info(f"Prevalence — TRAIN: {y_train.sum()/len(y_train):.4f} | VAL: {prior_metrics['selected']['tp'] / (prior_metrics['selected']['tp'] + prior_metrics['selected']['fn']):.4f}* | TEST: {prevalence:.4f}")

    results = {
        "dataset": {
            "n_total": n_total,
            "n_fraud": n_fraud,
            "n_legit": n_legit,
            "fraud_prevalence": prevalence,
        },
        "metrics_at_threshold_0.50": {
            "roc_auc": roc_auc,
            "pr_auc": pr_auc,
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "specificity": specificity,
            "fpr": fpr,
            "fnr": fnr,
            "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
        },
        "score_distribution_all": dist_all,
        "score_distribution_fraud": dist_fraud,
        "score_distribution_legit": dist_legit,
        "gap_analysis": {
            "train_roc_auc": train_roc,
            "train_pr_auc": train_pr,
            "val_roc_auc": val_roc,
            "val_pr_auc": val_pr,
            "test_roc_auc": roc_auc,
            "test_pr_auc": pr_auc,
            "val_to_test_roc_gap": roc_auc - val_roc,
            "val_to_test_pr_gap": pr_auc - val_pr,
            "train_to_test_roc_gap": roc_auc - train_roc,
            "train_to_test_pr_gap": pr_auc - train_pr,
        },
        "integrity_hashes": {k: md5(k) for k in KNOWN_HASHES},
    }

    with open(OUTPUT_PATH, "w") as f:
        json.dump(results, f, indent=4)
    logger.info(f"Evaluation results written to {OUTPUT_PATH}")

    return results


if __name__ == "__main__":
    evaluate()
