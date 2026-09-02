"""
Tests for the XGBoost Fraud Model.
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
from model.fraud_model import train_xgboost, predict_proba, evaluate_xgboost


@pytest.fixture(scope="module")
def prepared_splits():
    df = generate_transactions(n=1000, seed=42)
    df_hist = compute_historical_features(df)
    train, val, test = split_chronological(df_hist)
    
    train_feat, state = fit_transform_features(train)
    val_feat = transform_features(val, state)
    
    return train_feat, val_feat


def test_xgboost_training(prepared_splits):
    train_feat, _ = prepared_splits
    X_train = get_feature_matrix(train_feat)
    y_train = get_target(train_feat)
    
    artifact = train_xgboost(X_train, y_train, config={"n_estimators": 5, "max_depth": 2})
    
    assert "model" in artifact
    assert "feature_names" in artifact
    assert artifact["feature_names"] == list(X_train.columns)
    assert artifact["config"]["scale_pos_weight"] > 1.0  # Given fraud is a minority


def test_xgboost_prediction_and_evaluation(prepared_splits):
    train_feat, val_feat = prepared_splits
    X_train = get_feature_matrix(train_feat)
    y_train = get_target(train_feat)
    
    X_val = get_feature_matrix(val_feat)
    y_val = get_target(val_feat)
    
    artifact = train_xgboost(X_train, y_train, config={"n_estimators": 5})
    
    probs = predict_proba(artifact, X_val)
    assert len(probs) == len(X_val)
    assert ((probs >= 0.0) & (probs <= 1.0)).all()
    
    metrics = evaluate_xgboost(artifact, X_val, y_val)
    assert metrics["samples"] == len(X_val)
    assert "roc_auc" in metrics
    assert "pr_auc" in metrics
    assert "precision" in metrics
    assert metrics["tp"] + metrics["tn"] + metrics["fp"] + metrics["fn"] == metrics["samples"]


def test_predict_rejects_misordered_features(prepared_splits):
    train_feat, val_feat = prepared_splits
    X_train = get_feature_matrix(train_feat)
    y_train = get_target(train_feat)
    
    artifact = train_xgboost(X_train, y_train, config={"n_estimators": 2})
    X_val = get_feature_matrix(val_feat)
    
    # Drop a column
    X_val_missing = X_val.drop(columns=[X_val.columns[0]])
    with pytest.raises(ValueError, match="Feature columns do not match"):
        predict_proba(artifact, X_val_missing)


def test_xgboost_edge_cases_do_not_crash(prepared_splits):
    train_feat, _ = prepared_splits
    X_train = get_feature_matrix(train_feat)
    y_train = get_target(train_feat)
    
    artifact = train_xgboost(X_train, y_train, config={"n_estimators": 5})
    edge_cases = pd.DataFrame(columns=X_train.columns)
    
    base_row = {col: 0.0 for col in X_train.columns}
    
    # Missing / Cold start
    row_new = base_row.copy()
    row_new.update({
        "ip_is_missing": 1.0, "location_is_missing": 1.0,
        "is_new_customer": 1.0, "is_new_merchant": 1.0,
    })
    
    # Extreme Outlier
    row_extreme = base_row.copy()
    row_extreme.update({
        "amount": 9999999.0, "txns_last_5min": 500, "previous_fraud_count": 100
    })
    
    edge_cases.loc[0] = row_new
    edge_cases.loc[1] = row_extreme
    
    probs = predict_proba(artifact, edge_cases)
    assert len(probs) == 2
    assert not np.isnan(probs).any()


def test_reproducibility(prepared_splits):
    train_feat, _ = prepared_splits
    X_train = get_feature_matrix(train_feat)
    y_train = get_target(train_feat)
    
    art1 = train_xgboost(X_train, y_train, config={"n_estimators": 5, "subsample": 0.5}, random_state=42)
    art2 = train_xgboost(X_train, y_train, config={"n_estimators": 5, "subsample": 0.5}, random_state=42)
    
    probs1 = predict_proba(art1, X_train)
    probs2 = predict_proba(art2, X_train)
    
    np.testing.assert_array_equal(probs1, probs2)
