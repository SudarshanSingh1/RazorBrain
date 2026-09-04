"""
Razorpay Serving Model — Risk Decision Policy Optimizer.
Uses VALIDATION data only. test.csv is never opened.
Calibrated model is used frozen — no refit.
"""
import hashlib
import json
import logging
from datetime import datetime, timezone
from itertools import product

import numpy as np
import pandas as pd
import joblib

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────────────────
CAL_MODEL_PATH = "data/razorpay_serving_model_calibrated.joblib"
VAL_PATH = "data/razorpay_serving_dataset/validation.csv"
CONTRACT_PATH = "data/razorpay_serving_feature_contract.json"
POLICY_OUT = "data/razorpay_serving_selected_policy.json"

KNOWN_HASHES = {
    "data/razorpay_serving_model_calibrated.joblib": "1aada82e6f1af13bcada372eb02ec312",
    "data/razorpay_serving_model_uncalibrated.joblib": "1242b74830962d8d323676563648ffdb",
    "data/razorpay_serving_dataset/test.csv": "fc4e76764a2e7ad1df631ce37d050f35",
    "data/model_c_calibrated.joblib": "17eaa5aad2a2672f497221362ee4cefd",
    "data/model_c_engineered_raw_safe.joblib": "7de3be91a463ce8d9c74193869212aea",
    "data/validation_selected_policy.json": "a6f2994d904e4dab0bb8ceca52924106",
}

# ── Cost model ─────────────────────────────────────────────────────────────────
COST_MODELS = {
    "base": {"C_FN": 100, "C_FP_BLOCK": 15, "C_FP_REVIEW": 5, "C_REVIEW": 2},
    "high_fn": {"C_FN": 200, "C_FP_BLOCK": 15, "C_FP_REVIEW": 5, "C_REVIEW": 2},
    "high_fp_block": {"C_FN": 100, "C_FP_BLOCK": 30, "C_FP_REVIEW": 5, "C_REVIEW": 2},
}


def md5(path: str) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_hashes(label: str = "pre-policy"):
    for path, expected in KNOWN_HASHES.items():
        actual = md5(path)
        if actual != expected:
            raise RuntimeError(f"INTEGRITY FAILURE ({label}): {path}\n  Expected: {expected}\n  Got: {actual}")
    logger.info(f"All hashes OK ({label}).")


def transaction_cost(y_true: int, decision: str, costs: dict) -> float:
    C_FN, C_FP_BLOCK = costs["C_FN"], costs["C_FP_BLOCK"]
    C_FP_REVIEW, C_REVIEW = costs["C_FP_REVIEW"], costs["C_REVIEW"]
    if y_true == 0:   # Legitimate
        if decision == "ALLOW":
            return 0.0
        if decision == "REVIEW":
            return C_FP_REVIEW + C_REVIEW
        if decision == "BLOCK":
            return C_FP_BLOCK
    else:             # Fraud
        if decision == "ALLOW":
            return C_FN
        if decision == "REVIEW":
            return C_REVIEW
        if decision == "BLOCK":
            return 0.0
    raise ValueError(f"Unknown decision: {decision}")


def apply_policy(risk: np.ndarray, t_review: float, t_block: float) -> np.ndarray:
    decisions = np.where(risk < t_review, "ALLOW",
                np.where(risk < t_block, "REVIEW", "BLOCK"))
    return decisions


def evaluate_policy(y_true: np.ndarray, decisions: np.ndarray, costs: dict) -> dict:
    n = len(y_true)
    fraud_mask = y_true == 1
    legit_mask = ~fraud_mask
    n_fraud = fraud_mask.sum()

    allow_mask = decisions == "ALLOW"
    review_mask = decisions == "REVIEW"
    block_mask = decisions == "BLOCK"

    review_rate = review_mask.sum() / n
    block_rate = block_mask.sum() / n
    fraud_review = (fraud_mask & review_mask).sum()
    fraud_block = (fraud_mask & block_mask).sum()
    fraud_allow = (fraud_mask & allow_mask).sum()
    legit_review = (legit_mask & review_mask).sum()
    legit_block = (legit_mask & block_mask).sum()

    total_cost = sum(
        transaction_cost(y, d, costs)
        for y, d in zip(y_true, decisions)
    )

    caught = fraud_review + fraud_block
    precision_rb = caught / max((review_mask | block_mask).sum(), 1)
    recall_rb = caught / max(n_fraud, 1)
    precision_b = fraud_block / max(block_mask.sum(), 1)
    recall_b = fraud_block / max(n_fraud, 1)

    return {
        "total_cost": float(total_cost),
        "avg_cost_per_txn": float(total_cost / n),
        "review_rate": float(review_rate),
        "block_rate": float(block_rate),
        "fraud_review": int(fraud_review),
        "fraud_block": int(fraud_block),
        "fraud_allow": int(fraud_allow),
        "fraud_total_caught": int(caught),
        "fraud_missed": int(fraud_allow),
        "legit_review": int(legit_review),
        "legit_block": int(legit_block),
        "precision_review_block": float(precision_rb),
        "recall_review_block": float(recall_rb),
        "precision_block": float(precision_b),
        "recall_block": float(recall_b),
    }


def search_policies(risk: np.ndarray, y_true: np.ndarray, costs: dict,
                    n_thresholds: int = 80, capacity: float = None) -> dict:
    """Grid search over T_review, T_block pairs. If capacity given, constrain review_rate <= capacity."""
    candidates = np.percentile(risk, np.linspace(1, 99, n_thresholds))
    candidates = np.unique(np.round(candidates, 4))

    best_cost = np.inf
    best = None

    for t_rev, t_blk in product(candidates, candidates):
        if t_rev >= t_blk:
            continue
        decisions = apply_policy(risk, t_rev, t_blk)
        stats = evaluate_policy(y_true, decisions, costs)
        if capacity is not None and stats["review_rate"] > capacity + 1e-6:
            continue
        if stats["total_cost"] < best_cost:
            best_cost = stats["total_cost"]
            best = {"t_review": float(t_rev), "t_block": float(t_blk), **stats}

    return best


def optimize():
    verify_hashes("pre-policy")

    # ── Load contract ──────────────────────────────────────────────────────────
    with open(CONTRACT_PATH) as f:
        contract = json.load(f)
    features = [feat["name"] for feat in contract["features"]]

    # ── Load calibrated model (frozen) ────────────────────────────────────────
    artifact = joblib.load(CAL_MODEL_PATH)
    pipeline = artifact["frozen_model_artifact"]
    calibrator = artifact["calibrator"]
    cal_type = artifact["calibrator_type"]

    # ── Load VALIDATION for policy search ─────────────────────────────────────
    logger.info("Loading validation set for policy optimization...")
    val_df = pd.read_csv(VAL_PATH)
    X_val = val_df[features]
    y_val = val_df["isFraud"].values

    logger.info(f"Validation: {len(val_df)} rows, {y_val.sum()} fraud ({y_val.mean()*100:.2f}%)")

    # ── Generate calibrated risk scores ───────────────────────────────────────
    logger.info("Generating calibrated risk scores...")
    raw_scores = pipeline.predict_proba(X_val)[:, 1]
    if cal_type == "isotonic":
        risk = np.clip(calibrator.predict(raw_scores), 1e-7, 1 - 1e-7)
    else:
        risk = calibrator.predict_proba(raw_scores.reshape(-1, 1))[:, 1]

    logger.info(f"Risk scores — min={risk.min():.4f} p50={np.percentile(risk,50):.4f} max={risk.max():.4f}")

    results = {}

    # ── BASE cost model ────────────────────────────────────────────────────────
    base_costs = COST_MODELS["base"]

    logger.info("=== BASE COST MODEL ===")

    # Unconstrained
    unconstrained = search_policies(risk, y_val, base_costs, capacity=None)
    logger.info(f"Unconstrained: T_review={unconstrained['t_review']:.4f} T_block={unconstrained['t_block']:.4f} "
                f"review={unconstrained['review_rate']*100:.1f}% cost={unconstrained['total_cost']:.0f}")

    # Capacity-constrained
    cap_policies = {}
    for cap in [0.01, 0.02, 0.05, 0.10]:
        p = search_policies(risk, y_val, base_costs, capacity=cap)
        cap_policies[f"{int(cap*100)}pct"] = p
        logger.info(f"{int(cap*100)}% capacity: T_review={p['t_review']:.4f} T_block={p['t_block']:.4f} "
                    f"review={p['review_rate']*100:.2f}% cost={p['total_cost']:.0f} "
                    f"fraud_caught={p['fraud_total_caught']}")

    results["base"] = {"unconstrained": unconstrained, "capacity_constrained": cap_policies}

    # ── Sensitivity analysis ──────────────────────────────────────────────────
    logger.info("=== SENSITIVITY ANALYSIS ===")
    sensitivity = {}
    for name, costs in COST_MODELS.items():
        best = search_policies(risk, y_val, costs, capacity=0.05)
        sensitivity[name] = {"t_review": best["t_review"], "t_block": best["t_block"],
                              "review_rate": best["review_rate"], "total_cost": best["total_cost"]}
        logger.info(f"{name}: T_review={best['t_review']:.4f} T_block={best['t_block']:.4f} "
                    f"review={best['review_rate']*100:.2f}%")
    results["sensitivity_at_5pct_capacity"] = sensitivity

    # ── Select demo policy ────────────────────────────────────────────────────
    # Use 5% review capacity, base cost model.
    demo = cap_policies["5pct"]
    logger.info(f"Selected demo policy: T_review={demo['t_review']:.4f} T_block={demo['t_block']:.4f}")

    # ── Write policy artifact ──────────────────────────────────────────────────
    policy = {
        "model_track": "RAZORPAY_SERVING_MODEL",
        "policy_version": "1.0",
        "policy_status": "VALIDATION_SELECTED",
        "calibrated_artifact": CAL_MODEL_PATH,
        "calibrated_artifact_hash": md5(CAL_MODEL_PATH),
        "threshold_review": demo["t_review"],
        "threshold_block": demo["t_block"],
        "cost_assumptions": base_costs,
        "cost_assumption_note": (
            "These are explicit operational assumptions, not measured Razorpay financial costs."
        ),
        "review_capacity_target": "5%",
        "selection_methodology": "Minimum total cost under 5% review capacity constraint on VALIDATION set",
        "optimization_dataset": VAL_PATH,
        "optimization_dataset_rows": int(len(val_df)),
        "optimization_dataset_fraud": int(y_val.sum()),
        "selected_policy_stats": {k: v for k, v in demo.items() if k not in ("t_review", "t_block")},
        "all_results": results,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    with open(POLICY_OUT, "w") as f:
        json.dump(policy, f, indent=4)
    logger.info(f"Policy artifact written to {POLICY_OUT}")

    verify_hashes("post-policy")
    return policy


if __name__ == "__main__":
    optimize()
