"""
Tests for Probability Calibration module.
"""

import pytest

from data.generator import generate_transactions
from model.feature_engineering import compute_historical_features, fit_transform_features, transform_features, get_feature_matrix, get_target
from model.dataset_split import split_chronological
from model.baseline import train_baseline
from model.calibration import fit_calibration, predict_calibrated_proba, evaluate_calibration


@pytest.fixture(scope="module")
def calibration_fixtures():
    df = generate_transactions(n=1000, seed=42)
    df_hist = compute_historical_features(df)
    train, val, test = split_chronological(df_hist)
    
    train_feat, state = fit_transform_features(train)
    val_feat = transform_features(val, state)
    
    X_train = get_feature_matrix(train_feat)
    y_train = get_target(train_feat)
    X_val = get_feature_matrix(val_feat)
    y_val = get_target(val_feat)
    
    model_art = train_baseline(X_train, y_train)
    return model_art, X_train, y_train, X_val, y_val


def test_calibration_fit_and_predict(calibration_fixtures):
    model_art, X_train, y_train, X_val, y_val = calibration_fixtures
    
    # We calibrate on the train set logically (predictions out of base model)
    calib_art = fit_calibration(model_art, X_train, y_train, method="isotonic")
    
    probs = predict_calibrated_proba(calib_art, X_val)
    assert len(probs) == len(X_val)
    assert ((probs >= 0.0) & (probs <= 1.0)).all()


def test_evaluate_calibration(calibration_fixtures):
    model_art, X_train, y_train, X_val, y_val = calibration_fixtures
    calib_art = fit_calibration(model_art, X_train, y_train, method="isotonic")
    
    from model.baseline import predict_proba
    y_raw = predict_proba(model_art, X_val)
    y_calib = predict_calibrated_proba(calib_art, X_val)
    
    metrics = evaluate_calibration(y_val, y_raw, y_calib, n_bins=5)
    
    assert "raw_brier" in metrics
    assert "calib_brier" in metrics
    assert "raw_ece" in metrics
    assert "calib_ece" in metrics
    assert len(metrics["raw_curve"]) == 5
    assert len(metrics["calib_curve"]) == 5
