"""
Integrity and contract tests for the Razorpay Serving Model held-out test evaluation.
"""
import hashlib
import json
import os
import numpy as np
import pandas as pd
import pytest
import joblib

KNOWN_HASHES = {
    "data/razorpay_serving_model_uncalibrated.joblib": "1242b74830962d8d323676563648ffdb",
    "data/razorpay_serving_dataset/test.csv": "fc4e76764a2e7ad1df631ce37d050f35",
    "data/model_c_calibrated.joblib": "17eaa5aad2a2672f497221362ee4cefd",
    "data/model_c_engineered_raw_safe.joblib": "7de3be91a463ce8d9c74193869212aea",
    "data/validation_selected_policy.json": "a6f2994d904e4dab0bb8ceca52924106",
}

REJECTED = {
    "isFraud", "TransactionID", "TransactionDT",
    "addr1", "addr2", "dist1", "R_emaildomain",
    "card2", "card3", "card5", "DeviceType",
}


def md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


@pytest.fixture(scope="module")
def artifact():
    return joblib.load("data/razorpay_serving_model_uncalibrated.joblib")


@pytest.fixture(scope="module")
def contract_features():
    with open("data/razorpay_serving_feature_contract.json") as f:
        c = json.load(f)
    return [feat["name"] for feat in c["features"]]


@pytest.fixture(scope="module")
def test_df():
    return pd.read_csv("data/razorpay_serving_dataset/test.csv")


def test_frozen_test_hash():
    assert md5("data/razorpay_serving_dataset/test.csv") == KNOWN_HASHES["data/razorpay_serving_dataset/test.csv"]


def test_model_artifact_hash():
    assert md5("data/razorpay_serving_model_uncalibrated.joblib") == KNOWN_HASHES["data/razorpay_serving_model_uncalibrated.joblib"]


def test_model_c_integrity():
    for path in [
        "data/model_c_calibrated.joblib",
        "data/model_c_engineered_raw_safe.joblib",
        "data/validation_selected_policy.json",
    ]:
        assert md5(path) == KNOWN_HASHES[path], f"Model C artifact modified: {path}"


def test_exact_feature_contract(artifact, contract_features):
    assert artifact["metadata"]["features"] == contract_features
    assert len(artifact["metadata"]["features"]) == 15


def test_no_rejected_features(artifact):
    features = set(artifact["metadata"]["features"])
    for r in REJECTED:
        assert r not in features, f"Rejected feature in contract: {r}"


def test_no_train_test_overlap(test_df):
    train_df = pd.read_csv("data/razorpay_serving_dataset/train.csv")
    overlap = set(train_df["TransactionID"]) & set(test_df["TransactionID"])
    assert len(overlap) == 0


def test_no_val_test_overlap(test_df):
    val_df = pd.read_csv("data/razorpay_serving_dataset/validation.csv")
    overlap = set(val_df["TransactionID"]) & set(test_df["TransactionID"])
    assert len(overlap) == 0


def test_deterministic_predictions(artifact, test_df):
    features = artifact["metadata"]["features"]
    pipeline = artifact["model_artifact"]
    X = test_df[features].iloc[:100]
    scores1 = pipeline.predict_proba(X)[:, 1]
    scores2 = pipeline.predict_proba(X)[:, 1]
    np.testing.assert_array_equal(scores1, scores2)


def test_labels_only_in_metrics(test_df):
    # Confirm isFraud is present in the CSV but not in feature list
    assert "isFraud" in test_df.columns
    with open("data/razorpay_serving_feature_contract.json") as f:
        contract = json.load(f)
    feature_names = [feat["name"] for feat in contract["features"]]
    assert "isFraud" not in feature_names


def test_evaluation_results_exist():
    assert os.path.exists("data/razorpay_serving_test_evaluation.json")
    with open("data/razorpay_serving_test_evaluation.json") as f:
        results = json.load(f)
    assert "metrics_at_threshold_0.50" in results
    assert results["metrics_at_threshold_0.50"]["roc_auc"] > 0.5
