#!/usr/bin/env python3
"""
Automated ML Reporting Pipeline for RazorBrain.

Loads the existing trained fraud detection model and validation dataset,
computes deterministic evaluation metrics and SHAP explainability values,
and outputs publication-ready visualizations and structured datasets.

Usage:
    python scripts/generate_report.py
"""

from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Ensure writable matplotlib cache dir
os.environ["MPLCONFIGDIR"] = tempfile.gettempdir()

import joblib
import matplotlib
matplotlib.use("Agg")  # Non-interactive backend
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shap
from sklearn.metrics import (
    auc,
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
    roc_curve,
)

# ── Logging Configuration ──────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("generate_report")

# ── Constant Paths ─────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
MODEL_ARTIFACT_PATH = BASE_DIR / "data" / "razorpay_serving_model_calibrated.joblib"
CONTRACT_PATH = BASE_DIR / "data" / "razorpay_serving_feature_contract.json"
POLICY_PATH = BASE_DIR / "data" / "razorpay_serving_selected_policy.json"
TRAIN_DATA_PATH = BASE_DIR / "data" / "razorpay_serving_dataset" / "train.csv"
VAL_DATA_PATH = BASE_DIR / "data" / "razorpay_serving_dataset" / "validation.csv"
OUTPUT_DIR = BASE_DIR / "outputs"

# ── Styling Constants ──────────────────────────────────────────────────────────
COLOR_BG = "#0b1528"          # Deep dark navy
COLOR_CARD = "#112038"        # Card background
COLOR_TEXT = "#e2e8f0"        # Light slate text
COLOR_MUTED = "#94a3b8"       # Secondary text
COLOR_GRID = "#1e293b"        # Subtle gridlines
COLOR_BLUE = "#38bdf8"        # Electric cyan-blue
COLOR_DARK_BLUE = "#2563eb"   # Primary blue
COLOR_GREEN = "#10b981"       # Emerald green (legit / negative)
COLOR_RED = "#f43f5e"         # Rose / red (fraud / positive)
COLOR_AMBER = "#f59e0b"       # Amber / yellow (warning)
COLOR_PURPLE = "#a855f7"      # Purple (threshold marker)


def apply_custom_plot_style(fig: plt.Figure, axes: List[plt.Axes] | plt.Axes) -> None:
    """Apply consistent RazorBrain dark-fintech styling across matplotlib figures."""
    fig.patch.set_facecolor(COLOR_BG)
    axes_list = axes if isinstance(axes, (list, np.ndarray)) else [axes]
    if isinstance(axes, np.ndarray):
        axes_list = axes.flatten()

    for ax in axes_list:
        ax.set_facecolor(COLOR_CARD)
        ax.tick_params(colors=COLOR_MUTED, labelsize=9)
        ax.xaxis.label.set_color(COLOR_TEXT)
        ax.yaxis.label.set_color(COLOR_TEXT)
        ax.title.set_color(COLOR_TEXT)
        ax.title.set_fontweight("bold")
        ax.title.set_fontsize(11)

        # Clean borders (spines)
        for spine in ax.spines.values():
            spine.set_color(COLOR_GRID)
            spine.set_linewidth(1.0)

        # Subtle grid
        ax.grid(True, linestyle="--", alpha=0.35, color=COLOR_GRID)


# ── Step 1: Load Assets and Data ──────────────────────────────────────────────
def load_assets() -> Tuple[Dict[str, Any], pd.DataFrame, pd.DataFrame, List[str], Dict[str, Any]]:
    """Load model artifact, contract, training data, and validation data."""
    logger.info("Loading model artifact from %s", MODEL_ARTIFACT_PATH)
    if not MODEL_ARTIFACT_PATH.exists():
        raise FileNotFoundError(f"Calibrated model artifact not found at {MODEL_ARTIFACT_PATH}")

    artifact = joblib.load(MODEL_ARTIFACT_PATH)

    logger.info("Loading feature contract from %s", CONTRACT_PATH)
    with open(CONTRACT_PATH, "r") as f:
        contract = json.load(f)
    features = [feat["name"] for feat in contract["features"]]

    logger.info("Loading policy configuration from %s", POLICY_PATH)
    policy = {}
    if POLICY_PATH.exists():
        with open(POLICY_PATH, "r") as f:
            policy = json.load(f)

    logger.info("Loading training dataset from %s", TRAIN_DATA_PATH)
    train_df = pd.read_csv(TRAIN_DATA_PATH)

    logger.info("Loading validation dataset from %s", VAL_DATA_PATH)
    val_df = pd.read_csv(VAL_DATA_PATH)

    return artifact, train_df, val_df, features, policy


# ── Step 2: Model Inference and Scoring ────────────────────────────────────────
def run_model_inference(
    artifact: Dict[str, Any], val_df: pd.DataFrame, features: List[str]
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Generate raw scores and calibrated probabilities using the frozen model artifact.
    Reuses existing preprocessor and calibrator without modifying model state.
    """
    logger.info("Running deterministic inference on validation dataset (%d rows)...", len(val_df))
    pipeline = artifact["frozen_model_artifact"]
    calibrator = artifact["calibrator"]
    calibrator_type = artifact["calibrator_type"]

    X_val = val_df[features]
    y_val = val_df["isFraud"].values

    raw_scores = pipeline.predict_proba(X_val)[:, 1]

    if calibrator_type == "isotonic":
        calibrated_proba = np.clip(calibrator.predict(raw_scores), 1e-7, 1 - 1e-7)
    elif calibrator_type == "platt":
        calibrated_proba = calibrator.predict_proba(raw_scores.reshape(-1, 1))[:, 1]
    else:
        raise ValueError(f"Unsupported calibrator type: {calibrator_type}")

    return raw_scores, calibrated_proba, y_val


# ── Step 3: Threshold Determination ───────────────────────────────────────────
def determine_operating_thresholds(
    y_val: np.ndarray, calibrated_proba: np.ndarray, policy: Dict[str, Any]
) -> Dict[str, Dict[str, Any]]:
    """
    Calculate HIGH_PRECISION and BALANCED operating thresholds from validation data,
    and include DEFAULT_0.50 and operational policy thresholds.
    """
    logger.info("Calculating optimal operating thresholds on validation data...")
    precisions, recalls, thresholds = precision_recall_curve(y_val, calibrated_proba)

    # 1. BALANCED: Maximize F1 score on validation set (harmonic mean of precision & recall)
    f1_scores = 2 * (precisions * recalls) / np.maximum(precisions + recalls, 1e-9)
    best_f1_idx = int(np.argmax(f1_scores[:-1]))
    balanced_threshold = float(thresholds[best_f1_idx])

    # 2. HIGH_PRECISION: Maximize F0.5 score (precision weighted 2x recall) prioritizing low false positives
    f05_scores = (1 + 0.5**2) * (precisions * recalls) / np.maximum((0.5**2 * precisions) + recalls, 1e-9)
    best_f05_idx = int(np.argmax(f05_scores[:-1]))
    high_precision_threshold = float(thresholds[best_f05_idx])

    # Operational policy thresholds if configured
    t_review = policy.get("threshold_review", 0.1213)
    t_block = policy.get("threshold_block", 0.2053)

    return {
        "HIGH_PRECISION": {
            "threshold": high_precision_threshold,
            "logic": "Maximizes F0.5 score on validation data (weights precision 2x over recall) to minimize false positives",
        },
        "BALANCED": {
            "threshold": balanced_threshold,
            "logic": "Maximizes F1 score on validation data to achieve balanced precision-recall tradeoff",
        },
        "DEFAULT_0.50": {
            "threshold": 0.50,
            "logic": "Standard default classification threshold",
        },
        "POLICY_REVIEW": {
            "threshold": float(t_review),
            "logic": "Validation-selected policy threshold for flagging transactions into manual review",
        },
        "POLICY_BLOCK": {
            "threshold": float(t_block),
            "logic": "Validation-selected policy threshold for automated blocking of high-confidence fraud",
        },
    }


def compute_metrics_at_threshold(
    y_true: np.ndarray, y_prob: np.ndarray, threshold: float
) -> Dict[str, Any]:
    """Compute binary classification metrics and confusion matrix at a specific threshold."""
    y_pred = (y_prob >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred).ravel()

    precision = float(precision_score(y_true, y_pred, zero_division=0))
    recall = float(recall_score(y_true, y_pred, zero_division=0))
    f1 = float(f1_score(y_true, y_pred, zero_division=0))
    fpr = float(fp / (fp + tn)) if (fp + tn) > 0 else 0.0
    specificity = float(tn / (tn + fp)) if (tn + fp) > 0 else 0.0
    accuracy = float((tp + tn) / len(y_true))

    return {
        "threshold": round(threshold, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1_score": round(f1, 4),
        "fpr": round(fpr, 4),
        "specificity": round(specificity, 4),
        "accuracy": round(accuracy, 4),
        "tp": int(tp),
        "tn": int(tn),
        "fp": int(fp),
        "fn": int(fn),
    }


# ── Step 4: SHAP Analysis ─────────────────────────────────────────────────────
def compute_shap_importance(
    artifact: Dict[str, Any], val_df: pd.DataFrame, features: List[str], sample_size: int = 2000
) -> Tuple[pd.DataFrame, float, np.ndarray, List[str]]:
    """
    Compute SHAP values using TreeExplainer on a representative validation sample.
    Aggregates one-hot encoded categories back to original source contract features.
    """
    logger.info("Computing SHAP TreeExplainer values on %d validation samples...", sample_size)
    pipeline = artifact["frozen_model_artifact"]
    preprocessor = pipeline.named_steps["preprocessor"]
    xgb_clf = pipeline.named_steps["classifier"]

    # Sample deterministically
    sample_df = val_df.sample(n=min(sample_size, len(val_df)), random_state=42)
    X_sample = sample_df[features]

    # Preprocess with frozen transformer
    X_trans = preprocessor.transform(X_sample)
    transformed_names = list(preprocessor.get_feature_names_out())

    # Map transformed OHE names back to original 15 feature names
    name_map: Dict[str, str] = {}
    for t_name in transformed_names:
        if t_name.startswith("num__"):
            name_map[t_name] = t_name[5:]
        elif t_name.startswith("cat__"):
            inner = t_name[5:]
            matched = None
            for orig in features:
                if inner.startswith(orig + "_") or inner == orig:
                    if matched is None or len(orig) > len(matched):
                        matched = orig
            name_map[t_name] = matched if matched else inner
        else:
            name_map[t_name] = t_name

    explainer = shap.TreeExplainer(xgb_clf)
    shap_results = explainer(X_trans)
    shap_values = shap_results.values  # Shape: (sample_size, n_transformed_features)
    base_value = float(np.mean(shap_results.base_values))

    # Aggregate absolute SHAP values per original feature
    abs_shap = np.abs(shap_values)
    mean_abs_per_transformed = np.mean(abs_shap, axis=0)

    feature_shap_sums: Dict[str, float] = {f: 0.0 for f in features}
    for i, t_name in enumerate(transformed_names):
        orig = name_map.get(t_name, t_name)
        if orig in feature_shap_sums:
            feature_shap_sums[orig] += float(mean_abs_per_transformed[i])

    total_importance = sum(feature_shap_sums.values()) or 1.0
    records = []
    for rank, (feat, val) in enumerate(
        sorted(feature_shap_sums.items(), key=lambda x: x[1], reverse=True), start=1
    ):
        records.append({
            "rank": rank,
            "feature": feat,
            "mean_abs_shap": round(float(val), 6),
            "relative_importance_pct": round(float(val / total_importance * 100), 2),
            "sample_size": len(sample_df),
        })

    shap_df = pd.DataFrame(records)
    return shap_df, base_value, shap_values, transformed_names


# ── Step 5: Visualizations Generation ─────────────────────────────────────────

def plot_eda(val_df: pd.DataFrame, output_path: Path) -> None:
    """Generate 4-panel EDA overview: day of week, hour, velocity, card network."""
    logger.info("Generating EDA overview chart: %s", output_path)
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    apply_custom_plot_style(fig, axes)

    # 1. Day of Week
    ax1 = axes[0, 0]
    dow_stats = val_df.groupby("day_of_week")["isFraud"].agg(["count", "mean"]).reset_index()
    ax1.bar(dow_stats["day_of_week"], dow_stats["count"], color=COLOR_BLUE, alpha=0.6, label="Transaction Volume")
    ax1.set_ylabel("Total Transactions", color=COLOR_TEXT)
    ax1.set_xlabel("Day of Week (0-6)")
    ax1.set_title("Transaction Volume & Fraud Rate by Day of Week")

    ax1_twin = ax1.twinx()
    ax1_twin.plot(dow_stats["day_of_week"], dow_stats["mean"] * 100, color=COLOR_RED, marker="o", linewidth=2.2, label="Fraud Rate %")
    ax1_twin.set_ylabel("Fraud Rate (%)", color=COLOR_RED)
    ax1_twin.tick_params(colors=COLOR_RED, labelsize=9)
    ax1_twin.grid(False)

    # 2. Hour of Day
    ax2 = axes[0, 1]
    hod_stats = val_df.groupby("hour_of_day")["isFraud"].agg(["count", "mean"]).reset_index()
    ax2.bar(hod_stats["hour_of_day"], hod_stats["count"], color=COLOR_DARK_BLUE, alpha=0.6)
    ax2.set_ylabel("Total Transactions", color=COLOR_TEXT)
    ax2.set_xlabel("Hour of Day (0-23)")
    ax2.set_title("Hourly Distribution & Fraud Risk")

    ax2_twin = ax2.twinx()
    ax2_twin.plot(hod_stats["hour_of_day"], hod_stats["mean"] * 100, color=COLOR_AMBER, marker="s", linewidth=2.0)
    ax2_twin.set_ylabel("Fraud Rate (%)", color=COLOR_AMBER)
    ax2_twin.tick_params(colors=COLOR_AMBER, labelsize=9)
    ax2_twin.grid(False)

    # 3. Velocity by Class (txns_last_1h & txns_last_24h)
    ax3 = axes[1, 0]
    velocity_cols = ["txns_last_1h", "txns_last_24h"]
    legit_v = [val_df[val_df["isFraud"] == 0][col].mean() for col in velocity_cols]
    fraud_v = [val_df[val_df["isFraud"] == 1][col].mean() for col in velocity_cols]

    x_indices = np.arange(len(velocity_cols))
    width = 0.35
    ax3.bar(x_indices - width/2, legit_v, width, label="Legitimate", color=COLOR_GREEN, alpha=0.85)
    ax3.bar(x_indices + width/2, fraud_v, width, label="Fraud", color=COLOR_RED, alpha=0.85)
    ax3.set_xticks(x_indices)
    ax3.set_xticklabels(["1-Hour Velocity", "24-Hour Velocity"])
    ax3.set_ylabel("Average Historical Transactions")
    ax3.set_title("Velocity Spike Comparison (Legit vs. Fraud)")
    ax3.legend(facecolor=COLOR_CARD, edgecolor=COLOR_GRID, labelcolor=COLOR_TEXT)

    # 4. Fraud Rate by Card Network
    ax4 = axes[1, 1]
    net_stats = val_df.groupby("card_network")["isFraud"].agg(["count", "mean"]).reset_index()
    net_stats = net_stats[net_stats["count"] > 10].sort_values("mean", ascending=True)
    bars = ax4.barh(net_stats["card_network"], net_stats["mean"] * 100, color=COLOR_BLUE, alpha=0.85)
    ax4.set_xlabel("Fraud Rate (%)")
    ax4.set_title("Card Network Fraud Rate")
    for bar in bars:
        w = bar.get_width()
        ax4.text(w + 0.1, bar.get_y() + bar.get_height() / 2, f"{w:.2f}%", va="center", color=COLOR_TEXT, fontsize=8)

    plt.tight_layout()
    fig.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def plot_class_balance(train_df: pd.DataFrame, val_df: pd.DataFrame, output_path: Path) -> None:
    """Generate class balance visualization for training and validation splits."""
    logger.info("Generating class balance chart: %s", output_path)
    fig, ax = plt.subplots(figsize=(9, 6))
    apply_custom_plot_style(fig, ax)

    train_total = len(train_df)
    train_fraud = int(train_df["isFraud"].sum())
    train_legit = train_total - train_fraud

    val_total = len(val_df)
    val_fraud = int(val_df["isFraud"].sum())
    val_legit = val_total - val_fraud

    categories = ["Training Set\n(413,378 rows)", "Validation Set\n(88,581 rows)"]
    legit_counts = [train_legit, val_legit]
    fraud_counts = [train_fraud, val_fraud]

    x = np.arange(len(categories))
    width = 0.35

    bar1 = ax.bar(x - width / 2, legit_counts, width, label="Legitimate (Class 0)", color=COLOR_GREEN, alpha=0.9)
    bar2 = ax.bar(x + width / 2, fraud_counts, width, label="Fraud (Class 1)", color=COLOR_RED, alpha=0.9)

    ax.set_ylabel("Transaction Count (Log Scale)", color=COLOR_TEXT)
    ax.set_yscale("log")
    ax.set_title("Class Balance & Imbalance Ratio Across Splits", pad=12)
    ax.set_xticks(x)
    ax.set_xticklabels(categories)
    ax.legend(facecolor=COLOR_CARD, edgecolor=COLOR_GRID, labelcolor=COLOR_TEXT)

    # Data value labels
    for b in bar1:
        h = b.get_height()
        ax.text(b.get_x() + b.get_width() / 2, h * 1.15, f"{h:,}\n({h/train_total if b.get_x()<0 else h/val_total:.1%})",
                ha="center", va="bottom", color=COLOR_TEXT, fontsize=8.5)

    for b in bar2:
        h = b.get_height()
        ax.text(b.get_x() + b.get_width() / 2, h * 1.15, f"{h:,}\n({h/train_total if b.get_x()<1 else h/val_total:.2%})",
                ha="center", va="bottom", color=COLOR_RED, fontsize=8.5, fontweight="bold")

    plt.tight_layout()
    fig.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def plot_transaction_distribution(val_df: pd.DataFrame, output_path: Path) -> None:
    """Generate distribution charts of transaction amount and log_amount."""
    logger.info("Generating transaction distribution chart: %s", output_path)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5.5))
    apply_custom_plot_style(fig, [ax1, ax2])

    legit_amt = val_df[val_df["isFraud"] == 0]["amount"]
    fraud_amt = val_df[val_df["isFraud"] == 1]["amount"]

    # 1. Truncated amount (up to 98th percentile for clear visual separation)
    p98 = np.percentile(val_df["amount"], 98)
    bins_amt = np.linspace(0, p98, 45)
    ax1.hist(legit_amt, bins=bins_amt, density=True, alpha=0.5, color=COLOR_GREEN, label=f"Legitimate (Median: ₹{legit_amt.median():.1f})")
    ax1.hist(fraud_amt, bins=bins_amt, density=True, alpha=0.6, color=COLOR_RED, label=f"Fraud (Median: ₹{fraud_amt.median():.1f})")
    ax1.set_xlabel("Transaction Amount (INR, ≤ 98th %ile)")
    ax1.set_ylabel("Probability Density")
    ax1.set_title("Transaction Amount Distribution")
    ax1.legend(facecolor=COLOR_CARD, edgecolor=COLOR_GRID, labelcolor=COLOR_TEXT)

    # 2. Log Amount Distribution
    legit_log = val_df[val_df["isFraud"] == 0]["log_amount"]
    fraud_log = val_df[val_df["isFraud"] == 1]["log_amount"]
    bins_log = np.linspace(val_df["log_amount"].min(), val_df["log_amount"].max(), 50)

    ax2.hist(legit_log, bins=bins_log, density=True, alpha=0.5, color=COLOR_BLUE, label="Legitimate")
    ax2.hist(fraud_log, bins=bins_log, density=True, alpha=0.6, color=COLOR_AMBER, label="Fraud")
    ax2.set_xlabel("Log-scaled Amount (log1p)")
    ax2.set_ylabel("Probability Density")
    ax2.set_title("Log-Transformed Amount Distribution")
    ax2.legend(facecolor=COLOR_CARD, edgecolor=COLOR_GRID, labelcolor=COLOR_TEXT)

    plt.tight_layout()
    fig.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def plot_missing_values(val_df: pd.DataFrame, features: List[str], output_path: Path) -> None:
    """Generate bar chart of missing value representation rates."""
    logger.info("Generating missing values chart: %s", output_path)
    fig, ax = plt.subplots(figsize=(10, 5.5))
    apply_custom_plot_style(fig, ax)

    # In the contract dataset, explicit missingness is tracked as 'MISSING' or binary flag
    missing_rates = {}
    for feat in features:
        if feat in val_df.columns:
            # Check NaN
            nan_count = int(val_df[feat].isna().sum())
            # Check 'MISSING' string
            str_missing = int((val_df[feat].astype(str).str.upper() == "MISSING").sum())
            # Check binary missing flag
            flag_missing = int((val_df[feat] == 1).sum()) if feat.endswith("_missing") else 0
            
            total_missing = max(nan_count + str_missing, flag_missing)
            rate = (total_missing / len(val_df)) * 100
            missing_rates[feat] = rate

    sorted_missing = sorted(missing_rates.items(), key=lambda x: x[1], reverse=True)
    # Take top 8 features by missingness or non-zero
    top_items = [x for x in sorted_missing if x[1] > 0]
    if len(top_items) < 6:
        top_items = sorted_missing[:6]

    top_features = [x[0] for x in top_items]
    top_rates = [x[1] for x in top_items]

    bars = ax.barh(top_features[::-1], top_rates[::-1], color=COLOR_BLUE, alpha=0.85)
    ax.set_xlabel("Missingness Rate (%)")
    ax.set_title("Top Features by Missing Value / Default Indicator Rate", pad=12)

    max_val = max(top_rates + [1.0])
    for bar in bars:
        w = bar.get_width()
        ax.text(w + (max_val * 0.015), bar.get_y() + bar.get_height() / 2, f"{w:.2f}%", va="center", color=COLOR_TEXT, fontsize=9)

    ax.set_xlim(0, max_val * 1.18)
    plt.tight_layout()
    fig.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def plot_shap_importance(shap_df: pd.DataFrame, output_path: Path) -> None:
    """Generate ranked SHAP feature importance horizontal bar plot."""
    logger.info("Generating SHAP importance chart: %s", output_path)
    fig, ax = plt.subplots(figsize=(11, 7))
    apply_custom_plot_style(fig, ax)

    df_sorted = shap_df.sort_values("mean_abs_shap", ascending=True)
    bars = ax.barh(df_sorted["feature"], df_sorted["mean_abs_shap"], color=COLOR_BLUE, alpha=0.85)

    ax.set_xlabel("Mean Absolute SHAP Value (Impact on Model Margin)")
    ax.set_title("Global Feature Importance via TreeExplainer (15 Features)", pad=12)

    for bar, pct in zip(bars, df_sorted["relative_importance_pct"]):
        w = bar.get_width()
        ax.text(w + (max(df_sorted["mean_abs_shap"]) * 0.015), bar.get_y() + bar.get_height() / 2,
                f"{w:.4f} ({pct:.1f}%)", va="center", color=COLOR_TEXT, fontsize=8.5)

    ax.set_xlim(0, max(df_sorted["mean_abs_shap"]) * 1.25)
    plt.tight_layout()
    fig.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def plot_roc_curve(
    y_val: np.ndarray, calibrated_proba: np.ndarray, thresholds_info: Dict[str, Dict[str, Any]], output_path: Path
) -> float:
    """Generate ROC curve with operating points marked."""
    logger.info("Generating ROC curve chart: %s", output_path)
    fpr, tpr, _ = roc_curve(y_val, calibrated_proba)
    roc_auc = float(roc_auc_score(y_val, calibrated_proba))

    fig, ax = plt.subplots(figsize=(8, 6.5))
    apply_custom_plot_style(fig, ax)

    ax.plot(fpr, tpr, color=COLOR_BLUE, linewidth=2.5, label=f"RazorBrain Serving Model (AUC = {roc_auc:.4f})")
    ax.plot([0, 1], [0, 1], color=COLOR_MUTED, linestyle="--", linewidth=1.2, label="Random Guess (AUC = 0.5000)")

    # Mark operating points
    markers = {
        "HIGH_PRECISION": ("*", COLOR_RED, "High Precision"),
        "BALANCED": ("o", COLOR_AMBER, "Balanced F1"),
        "DEFAULT_0.50": ("s", COLOR_PURPLE, "Default 0.50"),
    }

    for key, (marker, col, label) in markers.items():
        thresh = thresholds_info[key]["threshold"]
        m = compute_metrics_at_threshold(y_val, calibrated_proba, thresh)
        ax.scatter(m["fpr"], m["recall"], color=col, s=110, zorder=5, marker=marker,
                   label=f"{label} (t={thresh:.3f}, Recall={m['recall']:.2f}, FPR={m['fpr']:.2f})")

    ax.set_xlabel("False Positive Rate (1 - Specificity)")
    ax.set_ylabel("True Positive Rate (Recall)")
    ax.set_title("Receiver Operating Characteristic (ROC) Curve", pad=12)
    ax.set_xlim([-0.02, 1.02])
    ax.set_ylim([-0.02, 1.02])
    ax.legend(loc="lower right", facecolor=COLOR_CARD, edgecolor=COLOR_GRID, labelcolor=COLOR_TEXT, fontsize=9)

    plt.tight_layout()
    fig.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return roc_auc


def plot_precision_recall_curve(
    y_val: np.ndarray, calibrated_proba: np.ndarray, thresholds_info: Dict[str, Dict[str, Any]], output_path: Path
) -> float:
    """Generate Precision-Recall curve with operating thresholds annotated."""
    logger.info("Generating Precision-Recall curve chart: %s", output_path)
    precisions, recalls, _ = precision_recall_curve(y_val, calibrated_proba)
    pr_auc = float(average_precision_score(y_val, calibrated_proba))
    base_rate = float(y_val.sum() / len(y_val))

    fig, ax = plt.subplots(figsize=(8, 6.5))
    apply_custom_plot_style(fig, ax)

    ax.plot(recalls, precisions, color=COLOR_BLUE, linewidth=2.5, label=f"RazorBrain Serving Model (PR-AUC = {pr_auc:.4f})")
    ax.axhline(base_rate, color=COLOR_MUTED, linestyle="--", linewidth=1.2, label=f"Baseline Prevalence ({base_rate:.2%})")

    markers = {
        "HIGH_PRECISION": ("*", COLOR_RED, "High Precision"),
        "BALANCED": ("o", COLOR_AMBER, "Balanced F1"),
        "DEFAULT_0.50": ("s", COLOR_PURPLE, "Default 0.50"),
    }

    for key, (marker, col, label) in markers.items():
        thresh = thresholds_info[key]["threshold"]
        m = compute_metrics_at_threshold(y_val, calibrated_proba, thresh)
        ax.scatter(m["recall"], m["precision"], color=col, s=110, zorder=5, marker=marker,
                   label=f"{label} (t={thresh:.3f}, P={m['precision']:.2f}, R={m['recall']:.2f})")

    ax.set_xlabel("Recall (True Positive Rate)")
    ax.set_ylabel("Precision (Positive Predictive Value)")
    ax.set_title("Precision-Recall Curve (Highly Imbalanced Data)", pad=12)
    ax.set_xlim([-0.02, 1.02])
    ax.set_ylim([-0.02, 1.02])
    ax.legend(loc="upper right", facecolor=COLOR_CARD, edgecolor=COLOR_GRID, labelcolor=COLOR_TEXT, fontsize=9)

    plt.tight_layout()
    fig.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return pr_auc


def plot_score_distribution(
    y_val: np.ndarray, calibrated_proba: np.ndarray, thresholds_info: Dict[str, Dict[str, Any]], output_path: Path
) -> None:
    """Generate probability score distribution comparing legitimate vs fraud classes."""
    logger.info("Generating fraud probability score distribution chart: %s", output_path)
    fig, ax = plt.subplots(figsize=(10, 6))
    apply_custom_plot_style(fig, ax)

    legit_scores = calibrated_proba[y_val == 0]
    fraud_scores = calibrated_proba[y_val == 1]

    bins = np.linspace(0, 1, 60)
    ax.hist(legit_scores, bins=bins, density=True, alpha=0.55, color=COLOR_GREEN, label="Legitimate Transactions (Class 0)")
    ax.hist(fraud_scores, bins=bins, density=True, alpha=0.65, color=COLOR_RED, label="Fraud Transactions (Class 1)")

    # Threshold markers
    t_bal = thresholds_info["BALANCED"]["threshold"]
    t_hp = thresholds_info["HIGH_PRECISION"]["threshold"]
    t_rev = thresholds_info["POLICY_REVIEW"]["threshold"]
    t_blk = thresholds_info["POLICY_BLOCK"]["threshold"]

    ax.axvline(t_bal, color=COLOR_AMBER, linestyle="--", linewidth=2.0, label=f"Balanced Threshold (t={t_bal:.3f})")
    ax.axvline(t_hp, color=COLOR_RED, linestyle=":", linewidth=2.2, label=f"High Precision Threshold (t={t_hp:.3f})")
    ax.axvline(t_rev, color=COLOR_BLUE, linestyle="-.", linewidth=1.5, label=f"Policy Review (t={t_rev:.3f})")
    ax.axvline(t_blk, color=COLOR_PURPLE, linestyle="-.", linewidth=1.5, label=f"Policy Block (t={t_blk:.3f})")

    ax.set_xlabel("Calibrated Fraud Probability Risk Score")
    ax.set_ylabel("Probability Density (Log Scale)")
    ax.set_yscale("log")
    ax.set_title("Fraud Probability Score Separation & Operating Thresholds", pad=12)
    ax.legend(facecolor=COLOR_CARD, edgecolor=COLOR_GRID, labelcolor=COLOR_TEXT, fontsize=8.5)

    plt.tight_layout()
    fig.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)


# ── Step 6: CSV & JSON Metric Generators ──────────────────────────────────────

def export_model_parameters_csv(
    artifact: Dict[str, Any], train_df: pd.DataFrame, val_df: pd.DataFrame, output_path: Path
) -> None:
    """Export model parameters and configuration table to CSV."""
    logger.info("Exporting model parameters to %s", output_path)
    pipeline = artifact["frozen_model_artifact"]
    xgb_clf = pipeline.named_steps["classifier"]
    xgb_params = xgb_clf.get_params()
    metadata = artifact.get("metadata", {})

    params = [
        ("model_track", metadata.get("model_track", "RAZORPAY_SERVING_MODEL"), "Authoritative serving model identifier"),
        ("model_framework", "XGBoost (xgboost.sklearn.XGBClassifier)", "Underlying tree boosting framework"),
        ("pipeline_type", "sklearn.pipeline.Pipeline", "End-to-end encapsulated estimator pipeline"),
        ("calibrator_type", artifact.get("calibrator_type", "isotonic"), "Probability calibration technique applied post-inference"),
        ("number_of_features", len(metadata.get("features", [])), "Exact count of causally safe contract features"),
        ("features_list", ";".join(metadata.get("features", [])), "Semicolon-separated contract feature list"),
        ("training_dataset_rows", len(train_df), "Number of transactions in training partition"),
        ("training_fraud_count", int(train_df["isFraud"].sum()), "Number of fraud transactions in training partition"),
        ("training_fraud_prevalence", f"{(train_df['isFraud'].sum() / len(train_df)):.4%}", "Natural fraud prevalence in training split"),
        ("validation_dataset_rows", len(val_df), "Number of transactions in validation partition"),
        ("validation_fraud_count", int(val_df["isFraud"].sum()), "Number of fraud transactions in validation partition"),
        ("validation_fraud_prevalence", f"{(val_df['isFraud'].sum() / len(val_df)):.4%}", "Natural fraud prevalence in validation split"),
        ("best_iteration", getattr(xgb_clf, "best_iteration", 71), "Early stopping best iteration round"),
        ("n_estimators", xgb_params.get("n_estimators", 100), "Maximum number of boosting rounds"),
        ("max_depth", xgb_params.get("max_depth", 4), "Maximum tree depth for base learners"),
        ("learning_rate", xgb_params.get("learning_rate", 0.1), "Boosting shrinkage parameter"),
        ("scale_pos_weight", round(float(xgb_params.get("scale_pos_weight", 27.434)), 4), "Class imbalance negative/positive ratio weight"),
        ("objective", xgb_params.get("objective", "binary:logistic"), "Loss objective for binary classification"),
        ("eval_metric", xgb_params.get("eval_metric", "aucpr"), "Validation metric used for early stopping"),
        ("early_stopping_rounds", xgb_params.get("early_stopping_rounds", 10), "Rounds without PR-AUC gain before stopping"),
        ("random_state", xgb_params.get("random_state", 42), "Deterministic seed for reproducibility"),
    ]

    df = pd.DataFrame(params, columns=["parameter", "value", "description"])
    df.to_csv(output_path, index=False)


def export_metrics_csv_and_json(
    y_val: np.ndarray,
    calibrated_proba: np.ndarray,
    roc_auc: float,
    pr_auc: float,
    thresholds_info: Dict[str, Dict[str, Any]],
    artifact: Dict[str, Any],
    train_df: pd.DataFrame,
    val_df: pd.DataFrame,
    shap_df: pd.DataFrame,
    csv_path: Path,
    json_path: Path,
) -> None:
    """Export tabular metrics to CSV and complete machine-readable metrics to JSON."""
    logger.info("Exporting metrics to %s and %s", csv_path, json_path)
    records = []

    for mode, info in thresholds_info.items():
        thresh = info["threshold"]
        m = compute_metrics_at_threshold(y_val, calibrated_proba, thresh)
        records.append({
            "mode": mode,
            "threshold": m["threshold"],
            "threshold_selection_logic": info["logic"],
            "auc_roc": round(roc_auc, 4),
            "pr_auc": round(pr_auc, 4),
            "precision": m["precision"],
            "recall": m["recall"],
            "f1_score": m["f1_score"],
            "false_positive_rate": m["fpr"],
            "specificity": m["specificity"],
            "accuracy": m["accuracy"],
            "true_positives": m["tp"],
            "true_negatives": m["tn"],
            "false_positives": m["fp"],
            "false_negatives": m["fn"],
            "total_samples": len(y_val),
        })

    metrics_df = pd.DataFrame(records)
    metrics_df.to_csv(csv_path, index=False)

    # Score percentile distribution
    percentiles = [0, 10, 25, 50, 75, 90, 95, 99, 100]
    score_dist_all = {f"p{p}": round(float(np.percentile(calibrated_proba, p)), 6) for p in percentiles}
    score_dist_legit = {f"p{p}": round(float(np.percentile(calibrated_proba[y_val == 0], p)), 6) for p in percentiles}
    score_dist_fraud = {f"p{p}": round(float(np.percentile(calibrated_proba[y_val == 1], p)), 6) for p in percentiles}

    pipeline = artifact["frozen_model_artifact"]
    xgb_clf = pipeline.named_steps["classifier"]

    json_payload = {
        "metadata": {
            "model_track": "RAZORPAY_SERVING_MODEL",
            "framework": "XGBoost",
            "calibrator": artifact.get("calibrator_type", "isotonic"),
            "best_iteration": int(getattr(xgb_clf, "best_iteration", 71)),
            "features_count": len(artifact["metadata"].get("features", [])),
            "features": artifact["metadata"].get("features", []),
        },
        "dataset_sizes": {
            "train_rows": len(train_df),
            "train_fraud": int(train_df["isFraud"].sum()),
            "train_fraud_rate": round(float(train_df["isFraud"].mean()), 6),
            "val_rows": len(val_df),
            "val_fraud": int(val_df["isFraud"].sum()),
            "val_fraud_rate": round(float(val_df["isFraud"].mean()), 6),
        },
        "overall_evaluation": {
            "auc_roc": round(roc_auc, 6),
            "pr_auc": round(pr_auc, 6),
        },
        "operating_modes": records,
        "score_distribution": {
            "all": score_dist_all,
            "legitimate": score_dist_legit,
            "fraud": score_dist_fraud,
        },
        "shap_importance_summary": shap_df.to_dict(orient="records"),
    }

    with open(json_path, "w") as f:
        json.dump(json_payload, f, indent=2)


# ── Main Pipeline Orchestrator ────────────────────────────────────────────────
def main() -> None:
    logger.info("=== Starting RazorBrain Automated ML Reporting Pipeline ===")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Load data & model
    artifact, train_df, val_df, features, policy = load_assets()

    # 2. Run deterministic model inference
    raw_scores, calibrated_proba, y_val = run_model_inference(artifact, val_df, features)

    # 3. Determine thresholds
    thresholds_info = determine_operating_thresholds(y_val, calibrated_proba, policy)
    for mode, info in thresholds_info.items():
        logger.info("  -> Operating Mode %-15s : threshold = %.4f", mode, info["threshold"])

    # 4. Compute SHAP Importance
    shap_df, base_value, shap_values, transformed_names = compute_shap_importance(
        artifact, val_df, features, sample_size=2000
    )
    shap_csv_path = OUTPUT_DIR / "shap_importance.csv"
    shap_df.to_csv(shap_csv_path, index=False)
    logger.info("Saved SHAP feature importance table to %s", shap_csv_path)

    # 5. Generate all 8 visual artifacts
    plot_eda(val_df, OUTPUT_DIR / "eda.png")
    plot_class_balance(train_df, val_df, OUTPUT_DIR / "class_balance.png")
    plot_transaction_distribution(val_df, OUTPUT_DIR / "transaction_distribution.png")
    plot_missing_values(val_df, features, OUTPUT_DIR / "missing_values.png")
    plot_shap_importance(shap_df, OUTPUT_DIR / "shap_importance.png")
    roc_auc = plot_roc_curve(y_val, calibrated_proba, thresholds_info, OUTPUT_DIR / "roc_curve.png")
    pr_auc = plot_precision_recall_curve(y_val, calibrated_proba, thresholds_info, OUTPUT_DIR / "precision_recall_curve.png")
    plot_score_distribution(y_val, calibrated_proba, thresholds_info, OUTPUT_DIR / "score_distribution.png")

    # 6. Export structured metrics
    export_model_parameters_csv(artifact, train_df, val_df, OUTPUT_DIR / "model_parameters.csv")
    export_metrics_csv_and_json(
        y_val=y_val,
        calibrated_proba=calibrated_proba,
        roc_auc=roc_auc,
        pr_auc=pr_auc,
        thresholds_info=thresholds_info,
        artifact=artifact,
        train_df=train_df,
        val_df=val_df,
        shap_df=shap_df,
        csv_path=OUTPUT_DIR / "metrics.csv",
        json_path=OUTPUT_DIR / "metrics.json",
    )

    logger.info("=== Pipeline Completed Successfully. All artifacts generated in %s ===", OUTPUT_DIR)


if __name__ == "__main__":
    main()
