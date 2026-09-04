"""
Independent probability calibration for the Razorpay Serving Model prototype.
Rules:
  - Frozen serving model (uncalibrated joblib) is NEVER retrained.
  - Calibration uses only TRAIN (last 20% chronologically) + VALIDATION for evaluation.
  - test.csv is never opened.
  - Model C artifacts are never touched.
"""
import hashlib
import json
import logging

import joblib
import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    log_loss,
    roc_auc_score,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────────────────
UNCAL_MODEL_PATH = "data/razorpay_serving_model_uncalibrated.joblib"
TRAIN_PATH = "data/razorpay_serving_dataset/train.csv"
VAL_PATH = "data/razorpay_serving_dataset/validation.csv"
CONTRACT_PATH = "data/razorpay_serving_feature_contract.json"
OUTPUT_MODEL = "data/razorpay_serving_model_calibrated.joblib"
REPORT_JSON = "data/razorpay_serving_calibration_report.json"
RANDOM_SEED = 42

KNOWN_HASHES = {
    UNCAL_MODEL_PATH: "1242b74830962d8d323676563648ffdb",
    "data/razorpay_serving_dataset/test.csv": "fc4e76764a2e7ad1df631ce37d050f35",
    "data/model_c_calibrated.joblib": "17eaa5aad2a2672f497221362ee4cefd",
    "data/model_c_engineered_raw_safe.joblib": "7de3be91a463ce8d9c74193869212aea",
    "data/validation_selected_policy.json": "a6f2994d904e4dab0bb8ceca52924106",
}

# ── Utilities ──────────────────────────────────────────────────────────────────

def md5(path: str) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_hashes(label: str = "pre-calibration"):
    logger.info(f"Verifying artifact hashes ({label})...")
    for path, expected in KNOWN_HASHES.items():
        actual = md5(path)
        if actual != expected:
            raise RuntimeError(
                f"INTEGRITY FAILURE ({label}): {path}\n"
                f"  Expected: {expected}\n  Got: {actual}"
            )
    logger.info(f"All hashes verified OK ({label}).")


def calibration_metrics(y_true, proba, label: str) -> dict:
    roc = roc_auc_score(y_true, proba)
    pr = average_precision_score(y_true, proba)
    brier = brier_score_loss(y_true, proba)
    ll = log_loss(y_true, proba)
    logger.info(
        f"[{label}] ROC-AUC={roc:.4f}  PR-AUC={pr:.4f}  "
        f"Brier={brier:.4f}  LogLoss={ll:.4f}"
    )
    return {"roc_auc": roc, "pr_auc": pr, "brier": brier, "log_loss": ll}


def reliability_bins(y_true, proba, n_bins: int = 10) -> list:
    """Compute reliability diagram bins: predicted mean vs observed fraud rate."""
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    results = []
    for lo, hi in zip(bins[:-1], bins[1:]):
        mask = (proba >= lo) & (proba < hi)
        n = int(mask.sum())
        if n == 0:
            results.append({
                "bin_lo": round(lo, 2), "bin_hi": round(hi, 2),
                "n": 0, "mean_predicted": None, "observed_fraud_rate": None
            })
        else:
            results.append({
                "bin_lo": round(lo, 2), "bin_hi": round(hi, 2),
                "n": n,
                "mean_predicted": float(proba[mask].mean()),
                "observed_fraud_rate": float(y_true[mask].mean()),
            })
    return results


# ── Main ───────────────────────────────────────────────────────────────────────

def calibrate():
    verify_hashes("pre-calibration")

    # ── Load contract ──────────────────────────────────────────────────────────
    with open(CONTRACT_PATH) as f:
        contract = json.load(f)
    features = [feat["name"] for feat in contract["features"]]
    assert len(features) == 15, "Feature contract must have exactly 15 features"

    # ── Load frozen uncalibrated model ─────────────────────────────────────────
    uncal_artifact = joblib.load(UNCAL_MODEL_PATH)
    pipeline = uncal_artifact["model_artifact"]
    assert uncal_artifact["metadata"]["selected_model"] == "XGBoost"
    assert uncal_artifact["metadata"]["features"] == features

    # ── Load TRAIN; chronological calibration split (last 20%) ───────────────
    logger.info("Loading train data for calibration split...")
    train_df = pd.read_csv(TRAIN_PATH)
    n_train = len(train_df)
    cal_start_idx = int(n_train * 0.80)

    model_train_df = train_df.iloc[:cal_start_idx]   # rows used to train XGBoost
    cal_df = train_df.iloc[cal_start_idx:]            # chronologically later rows
    assert cal_df["TransactionDT"].min() > model_train_df["TransactionDT"].max(), \
        "Calibration rows are not strictly after model-train rows"

    # ── Load VALIDATION as calibration evaluation set ─────────────────────────
    logger.info("Loading validation data for calibration evaluation...")
    val_df = pd.read_csv(VAL_PATH)
    assert val_df["TransactionDT"].min() > cal_df["TransactionDT"].max(), \
        "Validation rows are not strictly after calibration rows"

    logger.info(
        f"Calibration split: {len(cal_df)} rows, "
        f"{cal_df['isFraud'].sum()} fraud ({cal_df['isFraud'].mean()*100:.2f}%)"
    )
    logger.info(
        f"Cal-evaluation (validation): {len(val_df)} rows, "
        f"{val_df['isFraud'].sum()} fraud ({val_df['isFraud'].mean()*100:.2f}%)"
    )

    # ── Generate scores from FROZEN model (no refit) ──────────────────────────
    logger.info("Generating raw scores from frozen model (no refit)...")
    X_cal = cal_df[features]
    y_cal = cal_df["isFraud"].values
    X_val = val_df[features]
    y_val = val_df["isFraud"].values

    raw_cal_scores = pipeline.predict_proba(X_cal)[:, 1]
    raw_val_scores = pipeline.predict_proba(X_val)[:, 1]

    # ── Baseline uncalibrated metrics on val ──────────────────────────────────
    logger.info("=== UNCALIBRATED ===")
    uncal_metrics = calibration_metrics(y_val, raw_val_scores, "UNCALIBRATED")

    # ── Platt scaling (Logistic Regression on raw scores) ─────────────────────
    logger.info("Fitting Platt scaler...")
    platt = LogisticRegression(random_state=RANDOM_SEED)
    platt.fit(raw_cal_scores.reshape(-1, 1), y_cal)
    platt_val = platt.predict_proba(raw_val_scores.reshape(-1, 1))[:, 1]

    logger.info("=== PLATT ===")
    platt_metrics = calibration_metrics(y_val, platt_val, "PLATT")

    # ── Isotonic regression ───────────────────────────────────────────────────
    logger.info("Fitting Isotonic regression...")
    iso = IsotonicRegression(out_of_bounds="clip")
    iso.fit(raw_cal_scores, y_cal)
    iso_val = iso.predict(raw_val_scores).astype(float)
    # Clip to avoid log(0) in log_loss
    iso_val = np.clip(iso_val, 1e-7, 1 - 1e-7)

    logger.info("=== ISOTONIC ===")
    iso_metrics = calibration_metrics(y_val, iso_val, "ISOTONIC")

    # ── Select calibrator ─────────────────────────────────────────────────────
    # Primary: Brier score (lower = better). Secondary: log_loss.
    if platt_metrics["brier"] <= iso_metrics["brier"]:
        selected = "platt"
        selected_calibrator = platt
        selected_metrics = platt_metrics
        selection_reason = (
            f"Platt selected: lower Brier score "
            f"({platt_metrics['brier']:.4f} vs {iso_metrics['brier']:.4f}). "
            f"Platt is monotonic and more robust for small calibration sets."
        )
    else:
        selected = "isotonic"
        selected_calibrator = iso
        selected_metrics = iso_metrics
        selection_reason = (
            f"Isotonic selected: lower Brier score "
            f"({iso_metrics['brier']:.4f} vs {platt_metrics['brier']:.4f})."
        )

    logger.info(f"Selected calibrator: {selected.upper()} — {selection_reason}")

    # ── Reliability bins ──────────────────────────────────────────────────────
    rel_uncal = reliability_bins(y_val, raw_val_scores)
    rel_platt = reliability_bins(y_val, platt_val)
    rel_iso = reliability_bins(y_val, iso_val)

    # ── Build and save calibrated artifact ────────────────────────────────────
    artifact = {
        "frozen_model_artifact": pipeline,
        "preprocessing": pipeline.named_steps["preprocessor"],
        "calibrator": selected_calibrator,
        "calibrator_type": selected,
        "metadata": {
            "version": "1.0",
            "model_track": "RAZORPAY_SERVING_MODEL",
            "description": "Razorpay Serving Model Prototype — Platt/Isotonic calibrated",
            "features": features,
            "random_seed": RANDOM_SEED,
            "cal_rows": len(cal_df),
            "cal_fraud": int(cal_df["isFraud"].sum()),
            "cal_eval_rows": len(val_df),
            "cal_eval_fraud": int(val_df["isFraud"].sum()),
            "selected_calibrator": selected,
            "selection_reason": selection_reason,
            "uncalibrated_metrics": uncal_metrics,
            "platt_metrics": platt_metrics,
            "isotonic_metrics": iso_metrics,
            "selected_calibrator_metrics": selected_metrics,
            "source_uncalibrated_artifact": UNCAL_MODEL_PATH,
            "source_uncal_artifact_hash": md5(UNCAL_MODEL_PATH),
        },
    }

    joblib.dump(artifact, OUTPUT_MODEL)
    logger.info(f"Calibrated artifact saved to {OUTPUT_MODEL}")

    # ── JSON report ───────────────────────────────────────────────────────────
    report = {
        "calibration_split": {
            "model_train_rows": int(cal_start_idx),
            "model_train_fraud": int(model_train_df["isFraud"].sum()),
            "cal_rows": len(cal_df),
            "cal_fraud": int(cal_df["isFraud"].sum()),
            "cal_eval_rows": len(val_df),
            "cal_eval_fraud": int(val_df["isFraud"].sum()),
            "cal_dt_range": [int(cal_df["TransactionDT"].min()), int(cal_df["TransactionDT"].max())],
            "cal_eval_dt_range": [int(val_df["TransactionDT"].min()), int(val_df["TransactionDT"].max())],
        },
        "metrics": {
            "uncalibrated": uncal_metrics,
            "platt": platt_metrics,
            "isotonic": iso_metrics,
        },
        "selected_calibrator": selected,
        "selection_reason": selection_reason,
        "reliability_bins": {
            "uncalibrated": rel_uncal,
            "platt": rel_platt,
            "isotonic": rel_iso,
        },
        "integrity": {
            "uncalibrated_model_hash": md5(UNCAL_MODEL_PATH),
            "test_csv_hash": md5("data/razorpay_serving_dataset/test.csv"),
            "model_c_calibrated_hash": md5("data/model_c_calibrated.joblib"),
            "model_c_raw_hash": md5("data/model_c_engineered_raw_safe.joblib"),
            "model_c_policy_hash": md5("data/validation_selected_policy.json"),
        },
    }

    with open(REPORT_JSON, "w") as f:
        json.dump(report, f, indent=4)
    logger.info(f"Calibration report written to {REPORT_JSON}")

    # ── Post-calibration hash check ───────────────────────────────────────────
    verify_hashes("post-calibration")

    return report


if __name__ == "__main__":
    calibrate()
