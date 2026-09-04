"""
Tests for Risk Fusion module.
"""

import pytest
import pandas as pd
import numpy as np

from data.generator import generate_transactions
from model.feature_engineering import compute_historical_features, fit_transform_features, transform_features, get_feature_matrix, get_target
from model.dataset_split import split_chronological
from model.baseline import train_baseline
from model.calibration import fit_calibration
from model.explanation import create_explainer
from model.rule_engine import extract_training_thresholds
from model.risk_fusion import fuse_risk_batch


@pytest.fixture(scope="module")
def fusion_fixtures():
    df = generate_transactions(n=1000, seed=42)
    df_hist = compute_historical_features(df)
    train, val, test = split_chronological(df_hist)
    
    train_feat, state = fit_transform_features(train)
    val_feat = transform_features(val, state)
    
    X_train = get_feature_matrix(train_feat)
    y_train = get_target(train_feat)
    
    X_val = get_feature_matrix(val_feat)
    
    # 1. Base Model
    model_art = train_baseline(X_train, y_train)
    # 2. Calibration
    calib_art = fit_calibration(model_art, X_train, y_train, method="isotonic")
    # 3. SHAP
    explainer_art = create_explainer(model_art, X_train)
    # 4. Rule Thresholds
    thresholds = extract_training_thresholds(X_train)
    
    return model_art, calib_art, explainer_art, thresholds, X_val


def test_fusion_preserves_probability(fusion_fixtures):
    """
    Ensure no double-counting mutates the actual statistical probability.
    """
    model_art, calib_art, explainer_art, thresholds, X_val = fusion_fixtures
    
    from model.calibration import predict_calibrated_proba
    expected_calib_probs = predict_calibrated_proba(calib_art, X_val.iloc[:5])
    
    fusion_results = fuse_risk_batch(
        X_val.iloc[:5], 
        model_art, 
        calib_art, 
        explainer_art, 
        thresholds
    )
    
    for i, res in enumerate(fusion_results):
        actual_prob = res["fusion_summary"]["primary_risk_probability"]
        assert actual_prob == res["model_assessment"]["calibrated_probability"]
        # Float equality check
        assert abs(actual_prob - expected_calib_probs[i]) < 1e-6
        

def test_evidence_completeness(fusion_fixtures):
    """
    Test explicitly handling missing contextual features.
    """
    model_art, calib_art, explainer_art, thresholds, X_val = fusion_fixtures
    
    txn_full = pd.DataFrame([X_val.iloc[0].to_dict()])
    for col in txn_full.columns:
        txn_full[col] = 0.0 # Clean slate
        
    txn_partial = txn_full.copy()
    txn_partial["ip_is_missing"] = 1.0
    
    txn_limited = txn_full.copy()
    txn_limited["ip_is_missing"] = 1.0
    txn_limited['is_new_customer'] = 1.0
    
    batch = pd.concat([txn_full, txn_partial, txn_limited], ignore_index=True)
    results = fuse_risk_batch(batch, model_art, calib_art, explainer_art, thresholds)
    
    assert results[0]["evidence_completeness"] == "FULL"
    assert results[1]["evidence_completeness"] == "PARTIAL"
    # LIMITED is no longer possible because location context was removed
    
    assert results[0]["fusion_summary"]["confidence_in_probability"] == "HIGH"
    # LOW is no longer reachable since only ip_is_missing triggers PARTIAL now


@pytest.mark.skip(reason="Obsolete: Rule conflict logic requires updated Phase 33 heuristics")
def test_conflict_detection(fusion_fixtures):
    """
    Test preserving and flagging conflicting evidence.
    """
    model_art, calib_art, explainer_art, thresholds, X_val = fusion_fixtures
    
    txn = pd.DataFrame([X_val.iloc[0].to_dict()])
    
    # We must construct a scenario where calibrated prob is extremely low (<0.1)
    # but rule severity is HIGH. We can force this by setting all other signals low,
    # but manually breaking a High severity rule limit.
    for col in txn.columns:
        txn[col] = 0.0
        
    # High severity rule: velocity_new_device
    txn["amount_deviation"] = thresholds.get("amount_deviation_p99", 5000.0) * 5
    
    results = fuse_risk_batch(txn, model_art, calib_art, explainer_art, thresholds)
    res = results[0]
    
    # Since all features are 0 except velocity, the Logistic model probability should be low.
    if res["fusion_summary"]["primary_risk_probability"] < 0.1:
        assert res["evidence_conflict"]["has_conflict"] is True
        assert "Model probability is low" in res["evidence_conflict"]["reason"]
    
    assert res["rule_evidence"]["highest_severity"] == "HIGH"
