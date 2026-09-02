"""
XGBoost Fraud Classification Model for RazorBrain.

Implements a robust supervised binary classification model tailored for 
highly imbalanced transaction fraud data.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import (
    precision_score,
    recall_score,
    f1_score,
    precision_recall_curve,
    auc,
    roc_auc_score,
    confusion_matrix,
)

logger = logging.getLogger(__name__)


def calculate_scale_pos_weight(y_train: pd.Series) -> float:
    """
    Calculate the natural scale_pos_weight from the training distribution.
    Formula: count(negative) / count(positive)
    """
    neg_count = (y_train == 0).sum()
    pos_count = (y_train == 1).sum()
    if pos_count == 0:
        return 1.0
    return float(neg_count / pos_count)


def train_xgboost(
    X_train: pd.DataFrame, 
    y_train: pd.Series, 
    config: dict[str, Any] | None = None,
    random_state: int = 42
) -> dict[str, Any]:
    """
    Train an XGBoost classifier on the provided training set.
    
    Parameters
    ----------
    X_train : pd.DataFrame
        Model-ready numerical feature matrix.
    y_train : pd.Series
        Binary target vector (is_fraud).
    config : dict | None
        Hyperparameters for the XGBClassifier.
    random_state : int
        Seed for reproducibility.
        
    Returns
    -------
    dict[str, Any]
        Model artifact containing the fitted model and metadata.
    """
    logger.info("Training XGBoost on %d samples", len(X_train))
    config = config or {}
    
    # Auto-calculate class imbalance weight if not strictly provided
    if "scale_pos_weight" not in config:
        config["scale_pos_weight"] = calculate_scale_pos_weight(y_train)
        
    # Ensure default objective for probabilities
    if "objective" not in config:
        config["objective"] = "binary:logistic"
        
    if "eval_metric" not in config:
        config["eval_metric"] = "aucpr"
        
    model = xgb.XGBClassifier(
        random_state=random_state,
        n_jobs=-1,  # Use all available CPU cores
        **config
    )
    
    t0 = time.time()
    model.fit(X_train, y_train)
    train_time = time.time() - t0
    
    return {
        "model": model,
        "feature_names": list(X_train.columns),
        "config": config,
        "train_time_sec": train_time,
        "train_samples": len(X_train),
        "train_fraud_count": int(y_train.sum()),
    }


def predict_proba(model_artifact: dict[str, Any], X: pd.DataFrame) -> np.ndarray:
    """
    Generate probability predictions from the XGBoost model artifact.
    """
    model: xgb.XGBClassifier = model_artifact["model"]
    expected_features = model_artifact["feature_names"]
    
    # Enforce exact feature ordering
    if list(X.columns) != expected_features:
        raise ValueError("Feature columns do not match the expected training order.")
        
    return model.predict_proba(X)[:, 1]


def evaluate_xgboost(model_artifact: dict[str, Any], X: pd.DataFrame, y: pd.Series, threshold: float = 0.5) -> dict[str, Any]:
    """
    Evaluate the XGBoost model on a given dataset partition.
    """
    t0 = time.time()
    y_prob = predict_proba(model_artifact, X)
    pred_time = time.time() - t0
    
    y_pred = (y_prob >= threshold).astype(int)
    
    precision = precision_score(y, y_pred, zero_division=0)
    recall = recall_score(y, y_pred, zero_division=0)
    f1 = f1_score(y, y_pred, zero_division=0)
    
    try:
        roc_auc = roc_auc_score(y, y_prob)
    except ValueError:
        roc_auc = 0.0
        
    precision_curve, recall_curve, _ = precision_recall_curve(y, y_prob)
    pr_auc = auc(recall_curve, precision_curve)
    
    tn, fp, fn, tp = confusion_matrix(y, y_pred).ravel()
    
    return {
        "samples": len(y),
        "fraud_count": int(y.sum()),
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
        "pr_auc": float(pr_auc),
        "roc_auc": float(roc_auc),
        "tp": int(tp),
        "tn": int(tn),
        "fp": int(fp),
        "fn": int(fn),
        "fpr": float(fp / (fp + tn)) if (fp + tn) > 0 else 0.0,
        "fnr": float(fn / (fn + tp)) if (fn + tp) > 0 else 0.0,
        "pred_time_sec": pred_time,
    }


def tune_xgboost(
    X_train: pd.DataFrame, 
    y_train: pd.Series, 
    X_val: pd.DataFrame, 
    y_val: pd.Series, 
    candidates: list[dict[str, Any]]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """
    Perform a controlled hyperparameter search over a bounded set of candidates.
    Prioritizes PR-AUC on the validation set for model selection.
    
    Returns
    -------
    tuple
        The best model artifact, and a list of all evaluation records.
    """
    records = []
    best_artifact = None
    best_pr_auc = -1.0
    
    for i, config in enumerate(candidates):
        logger.info("Evaluating candidate %d/%d: %s", i+1, len(candidates), config)
        
        artifact = train_xgboost(X_train, y_train, config=config)
        metrics = evaluate_xgboost(artifact, X_val, y_val)
        
        record = {
            "candidate_index": i,
            "config": artifact["config"],
            "train_time_sec": artifact["train_time_sec"],
            "metrics": metrics
        }
        records.append(record)
        
        if metrics["pr_auc"] > best_pr_auc:
            best_pr_auc = metrics["pr_auc"]
            best_artifact = artifact
            
    return best_artifact, records
