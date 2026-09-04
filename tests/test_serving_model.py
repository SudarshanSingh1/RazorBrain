import pytest
import joblib
import pandas as pd
import json
import os
import hashlib

def get_md5(file_path):
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()

def test_serving_model_feature_contract():
    artifact = joblib.load('data/razorpay_serving_model_uncalibrated.joblib')
    features = artifact['metadata']['features']
    assert len(features) == 15, "Model must use exactly 15 features"
    
    with open('data/razorpay_serving_feature_contract.json') as f:
        contract = json.load(f)
    
    contract_features = [f['name'] for f in contract['features']]
    assert set(features) == set(contract_features), "Features must match contract exactly"
    
    assert "isFraud" not in features, "Target leakage in features"
    assert "TransactionID" not in features, "ID leakage in features"

def test_serving_test_untouched():
    # Hash from previous check
    expected_hash = "fc4e76764a2e7ad1df631ce37d050f35"
    actual_hash = get_md5("data/razorpay_serving_dataset/test.csv")
    assert expected_hash == actual_hash, "Razorpay Serving Test CSV was modified!"

def test_model_c_integrity():
    # Hashes verified prior to execution
    expected = {
        "data/model_c_calibrated.joblib": "17eaa5aad2a2672f497221362ee4cefd",
        "data/model_c_engineered_raw_safe.joblib": "7de3be91a463ce8d9c74193869212aea",
        "data/validation_selected_policy.json": "a6f2994d904e4dab0bb8ceca52924106"
    }
    
    for path, exp_hash in expected.items():
        actual_hash = get_md5(path)
        assert actual_hash == exp_hash, f"Model C artifact {path} was modified!"

def test_artifact_loading_and_predictions():
    artifact = joblib.load('data/razorpay_serving_model_uncalibrated.joblib')
    pipeline = artifact['model_artifact']
    features = artifact['metadata']['features']
    
    # Create dummy data
    dummy_data = {f: [0] if f not in ['email_domain', 'card_network', 'card_type'] else ['MISSING'] for f in features}
    df = pd.DataFrame(dummy_data)
    
    preds = pipeline.predict_proba(df)
    assert preds.shape == (1, 2)
    assert preds[0, 1] >= 0 and preds[0, 1] <= 1
