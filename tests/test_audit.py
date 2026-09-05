import numpy as np
import joblib
import json

def test_frozen_estimator_predictions_unchanged():
    artifact = joblib.load("data/model_c_engineered_raw_safe.joblib")
    base_model = artifact["model_artifact"]
    
    calib_artifact = joblib.load("data/model_c_calibrated.joblib")
    calibrator = calib_artifact["calibrator"]
    frozen_model = calibrator.estimator
    
    # Generate random input matching feature dimension
    num_features = base_model.n_features_in_
    X_test = np.random.rand(10, num_features)
    
    # Predict using raw base model
    raw_probs = base_model.predict_proba(X_test)
    
    # Predict using frozen model inside calibrator
    frozen_probs = frozen_model.predict_proba(X_test)
    
    # They MUST be absolutely identical
    np.testing.assert_array_equal(raw_probs, frozen_probs)

def test_calibrated_predictions_deterministic():
    calib_artifact = joblib.load("data/model_c_calibrated.joblib")
    calibrator = calib_artifact["calibrator"]
    
    num_features = calibrator.estimator.n_features_in_
    X_test = np.random.rand(10, num_features)
    
    probs1 = calibrator.predict_proba(X_test)
    probs2 = calibrator.predict_proba(X_test)
    
    np.testing.assert_array_equal(probs1, probs2)

def test_policy_metadata():
    with open("data/validation_selected_policy.json", "r") as f:
        policy = json.load(f)
        
    assert "model_id" in policy
    assert "calibration_method" in policy
    assert policy["policy_status"] == "VALIDATION_SELECTED"
    assert "t_review" in policy
    assert "t_block" in policy
    assert policy["t_review"] < policy["t_block"]
