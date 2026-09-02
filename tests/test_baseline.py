"""
Tests for the Baseline Fraud Model.
"""

import pytest
import pandas as pd
import numpy as np

from data.generator import generate_transactions
from model.feature_engineering import (
    compute_historical_features,
    fit_transform_features,
    transform_features,
    get_feature_matrix,
    get_target,
)
from model.dataset_split import split_chronological
from model.baseline import train_baseline, predict_proba, evaluate_model


@pytest.fixture(scope="module")
def prepared_splits():
    df = generate_transactions(n=1000, seed=42)
    df_hist = compute_historical_features(df)
    train, val, test = split_chronological(df_hist)
    
    train_feat, state = fit_transform_features(train)
    val_feat = transform_features(val, state)
    
    return train_feat, val_feat


def test_baseline_training(prepared_splits):
    train_feat, _ = prepared_splits
    X_train = get_feature_matrix(train_feat)
    y_train = get_target(train_feat)
    
    artifact = train_baseline(X_train, y_train)
    
    assert "scaler" in artifact
    assert "model" in artifact
    assert "feature_names" in artifact
    assert artifact["feature_names"] == list(X_train.columns)


def test_baseline_prediction_and_evaluation(prepared_splits):
    train_feat, val_feat = prepared_splits
    X_train = get_feature_matrix(train_feat)
    y_train = get_target(train_feat)
    
    X_val = get_feature_matrix(val_feat)
    y_val = get_target(val_feat)
    
    artifact = train_baseline(X_train, y_train)
    
    probs = predict_proba(artifact, X_val)
    assert len(probs) == len(X_val)
    assert ((probs >= 0.0) & (probs <= 1.0)).all()
    
    metrics = evaluate_model(artifact, X_val, y_val)
    assert metrics["samples"] == len(X_val)
    assert "roc_auc" in metrics
    assert "pr_auc" in metrics
    assert "precision" in metrics
    
    # Internal consistency of confusion matrix
    assert metrics["tp"] + metrics["tn"] + metrics["fp"] + metrics["fn"] == metrics["samples"]


def test_predict_rejects_missing_or_misordered_features(prepared_splits):
    train_feat, val_feat = prepared_splits
    X_train = get_feature_matrix(train_feat)
    y_train = get_target(train_feat)
    
    artifact = train_baseline(X_train, y_train)
    
    X_val = get_feature_matrix(val_feat)
    
    # Drop a column
    X_val_missing = X_val.drop(columns=[X_val.columns[0]])
    with pytest.raises(ValueError, match="Feature columns do not match"):
        predict_proba(artifact, X_val_missing)
        
    # Reorder columns
    X_val_reordered = X_val[X_val.columns[::-1]]
    with pytest.raises(ValueError, match="Feature columns do not match"):
        predict_proba(artifact, X_val_reordered)


def test_preprocessing_fit_audit():
    """
    CRITICAL AUDIT: Prove that modifying validation/test category frequencies 
    cannot change the training-fitted mapping.
    """
    df = generate_transactions(n=1000, seed=42)
    df_hist = compute_historical_features(df)
    train, val, test = split_chronological(df_hist)
    
    # Fit state on pure train
    train_feat, pure_state = fit_transform_features(train)
    
    # Now artificially poison the validation set by making every location "POISON_ISLAND"
    val_poison = val.copy()
    val_poison["location"] = "POISON_ISLAND"
    
    # Transform validation
    val_poison_feat = transform_features(val_poison, pure_state)
    
    # Assert that "POISON_ISLAND" mapped to 0.0 because it wasn't in train
    assert (val_poison_feat["location_freq"] == 0.0).all()
    
    # Assert that train_feat is unaffected (state didn't leak backward)
    train_feat_2, pure_state_2 = fit_transform_features(train)
    pd.testing.assert_frame_equal(train_feat, train_feat_2)
    assert pure_state == pure_state_2


def test_baseline_edge_cases_do_not_crash(prepared_splits):
    """
    Test baseline inference with anomalous rows to ensure it does not crash.
    """
    train_feat, _ = prepared_splits
    X_train = get_feature_matrix(train_feat)
    y_train = get_target(train_feat)
    artifact = train_baseline(X_train, y_train)
    
    # Create an edge-case DataFrame matching the feature layout exactly
    edge_cases = pd.DataFrame(columns=X_train.columns)
    
    # Base row of zeros
    base_row = {col: 0.0 for col in X_train.columns}
    
    # 1. Missing IP / Missing Location / New Customer / New Merchant
    row_new = base_row.copy()
    row_new.update({
        "ip_is_missing": 1.0,
        "location_is_missing": 1.0,
        "is_new_customer": 1.0,
        "is_new_merchant": 1.0,
        "new_device_flag": 1.0,
        "new_location_flag": 1.0,
    })
    
    # 2. Extremely high velocity / amounts
    row_extreme = base_row.copy()
    row_extreme.update({
        "amount": 9999999.0,
        "amount_deviation": 9999999.0,
        "txns_last_5min": 500,
        "txns_last_1h": 2000,
        "txns_last_24h": 50000,
        "previous_fraud_count": 100,
    })
    
    edge_cases.loc[0] = row_new
    edge_cases.loc[1] = row_extreme
    
    # Ensure prediction succeeds without raising exceptions
    probs = predict_proba(artifact, edge_cases)
    assert len(probs) == 2
    assert ((probs >= 0.0) & (probs <= 1.0)).all()

