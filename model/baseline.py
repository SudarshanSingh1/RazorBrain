"""
Baseline Fraud Classification Model for RazorBrain.

Provides a reproducible, simple XGBoost baseline to establish 
a performance floor before introducing complex non-linear models.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd
from xgboost import XGBClassifier
from sklearn.preprocessing import StandardScaler
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


def train_baseline(X_train: pd.DataFrame, y_train: pd.Series, random_state: int = 42) -> dict[str, Any]:
    """
    Train a baseline XGBoost model on the provided training set.
    
    Parameters
    ----------
    X_train : pd.DataFrame
        Model-ready numerical feature matrix (must NOT contain target).
    y_train : pd.Series
        Binary target vector (is_fraud).
    random_state : int
        Seed for reproducibility.
        
    Returns
    -------
    dict[str, Any]
        A dictionary containing the fitted scaler and the fitted model.
    """
    logger.info("Training baseline model on %d samples", len(X_train))
    
    # XGBoost requires scaled features.
    # We fit the scaler strictly on the training set to prevent leakage.
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X_train)
    
    # We use class_weight='balanced' because fraud is a severe minority class
    # and we want the baseline to naturally attempt to capture it without 
    # requiring manual threshold tuning out of the gate.
    model = XGBClassifier(
        n_estimators=100,
        max_depth=3,
        learning_rate=0.05,
        random_state=random_state,
        eval_metric='logloss'
    )
    model.fit(X_scaled, y_train)
    
    logger.info("Baseline training complete.")
    
    return {
        "scaler": scaler,
        "model": model,
        "feature_names": list(X_train.columns),
    }


def predict_proba(model_artifact: dict[str, Any], X: pd.DataFrame) -> np.ndarray:
    """
    Generate probability predictions from the baseline model.
    
    Parameters
    ----------
    model_artifact : dict
        The dictionary returned by train_baseline containing scaler and model.
    X : pd.DataFrame
        The feature matrix to score.
        
    Returns
    -------
    np.ndarray
        1D array of fraud probabilities.
    """
    scaler = model_artifact["scaler"]
    model = model_artifact["model"]
    expected_features = model_artifact["feature_names"]
    
    # Ensure exact feature ordering to prevent silent misalignment
    if list(X.columns) != expected_features:
        raise ValueError("Feature columns do not match the expected training order.")
        
    X_scaled = scaler.transform(X)
    return model.predict_proba(X_scaled)[:, 1]


def evaluate_model(model_artifact: dict[str, Any], X: pd.DataFrame, y: pd.Series, threshold: float = 0.5) -> dict[str, Any]:
    """
    Evaluate the model on a given dataset partition.
    
    Parameters
    ----------
    model_artifact : dict
        The trained model dictionary.
    X : pd.DataFrame
        Feature matrix.
    y : pd.Series
        True labels.
    threshold : float
        Decision threshold for binary metrics (defaults to 0.5).
        
    Returns
    -------
    dict
        Computed evaluation metrics.
    """
    # 1. Probabilities
    y_prob = predict_proba(model_artifact, X)
    
    # 2. Binary predictions
    y_pred = (y_prob >= threshold).astype(int)
    
    # 3. Core Metrics
    precision = precision_score(y, y_pred, zero_division=0)
    recall = recall_score(y, y_pred, zero_division=0)
    f1 = f1_score(y, y_pred, zero_division=0)
    roc_auc = roc_auc_score(y, y_prob)
    
    # PR-AUC
    precision_curve, recall_curve, _ = precision_recall_curve(y, y_prob)
    pr_auc = auc(recall_curve, precision_curve)
    
    # Confusion Matrix
    tn, fp, fn, tp = confusion_matrix(y, y_pred).ravel()
    
    n_samples = len(y)
    n_fraud = int(y.sum())
    
    return {
        "samples": n_samples,
        "fraud_count": n_fraud,
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
        "pr_auc": float(pr_auc),
        "roc_auc": float(roc_auc),
        "tp": int(tp),
        "tn": int(tn),
        "fp": int(fp),
        "fn": int(fn),
        "false_positive_rate": float(fp / (fp + tn)) if (fp + tn) > 0 else 0.0,
        "false_negative_rate": float(fn / (fn + tp)) if (fn + tp) > 0 else 0.0,
    }
