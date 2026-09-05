"""
Tests for the Razorpay Serving Model calibration step.
Verifies:
  - test.csv is never opened by calibration code
  - all artifact hashes remain unchanged
  - calibrator loads and produces deterministic output
  - feature contract enforced
  - no threshold optimisation occurred
  - no target column in feature preprocessing
"""
import ast
import hashlib
import json
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from model.serving_model_loader import ServingModelLoader

KNOWN_HASHES = {
    "data/razorpay_serving_model_uncalibrated.joblib": "1242b74830962d8d323676563648ffdb",
    "data/razorpay_serving_dataset/test.csv": "fc4e76764a2e7ad1df631ce37d050f35",
    "data/model_c_calibrated.joblib": "17eaa5aad2a2672f497221362ee4cefd",
    "data/model_c_engineered_raw_safe.joblib": "7de3be91a463ce8d9c74193869212aea",
    "data/validation_selected_policy.json": "a6f2994d904e4dab0bb8ceca52924106",
}


def md5(path: str) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ── Integrity ──────────────────────────────────────────────────────────────────

def test_test_csv_hash_unchanged():
    assert md5("data/razorpay_serving_dataset/test.csv") == KNOWN_HASHES["data/razorpay_serving_dataset/test.csv"]


def test_uncalibrated_model_hash_unchanged():
    assert md5("data/razorpay_serving_model_uncalibrated.joblib") == KNOWN_HASHES["data/razorpay_serving_model_uncalibrated.joblib"]


def test_model_c_hashes_unchanged():
    for path in [
        "data/model_c_calibrated.joblib",
        "data/model_c_engineered_raw_safe.joblib",
        "data/validation_selected_policy.json",
    ]:
        assert md5(path) == KNOWN_HASHES[path], f"Model C artifact modified: {path}"


# ── Calibration source code audit ─────────────────────────────────────────────

def test_calibration_script_never_opens_test_csv():
    """Static check: calibrate_serving_model.py must not open test.csv via pd.read_csv or open()."""
    with open("model/calibrate_serving_model.py") as f:
        source = f.read()
    # Reject any actual call to read_csv or open with test.csv
    assert 'read_csv("' not in source or "test.csv" not in source.split("read_csv")[1].split(")")[0] \
        if "read_csv" in source else True
    # Simpler: scan the AST for string literals 'test.csv' passed to open/read_csv
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func_name = ""
            if isinstance(node.func, ast.Attribute):
                func_name = node.func.attr
            elif isinstance(node.func, ast.Name):
                func_name = node.func.id
            if func_name in ("read_csv", "open"):
                for arg in node.args:
                    if isinstance(arg, ast.Constant) and "test.csv" in str(arg.value):
                        pytest.fail(f"calibrate_serving_model.py calls {func_name}('...test.csv')")


def test_calibration_script_no_threshold_optimisation():
    """Static check: no threshold or policy-setting logic in calibration script."""
    with open("model/calibrate_serving_model.py") as f:
        source = f.read()
    forbidden = ["t_review", "t_block", "allow_threshold", "block_threshold", "T_review", "T_block"]
    for token in forbidden:
        assert token not in source, f"Threshold token '{token}' found in calibration script"


# ── Calibration report ────────────────────────────────────────────────────────

def test_calibration_report_exists():
    assert os.path.exists("data/razorpay_serving_calibration_report.json")


def test_calibration_report_metrics_reasonable():
    with open("data/razorpay_serving_calibration_report.json") as f:
        report = json.load(f)
    # ROC-AUC should be preserved (monotonic transformation)
    uncal_roc = report["metrics"]["uncalibrated"]["roc_auc"]
    platt_roc = report["metrics"]["platt"]["roc_auc"]
    report["metrics"]["isotonic"]["roc_auc"]
    assert abs(platt_roc - uncal_roc) < 0.005, "Platt must not change ROC-AUC significantly"
    # Brier and log_loss must improve under calibration
    assert report["metrics"]["platt"]["brier"] < report["metrics"]["uncalibrated"]["brier"]
    assert report["metrics"]["isotonic"]["brier"] < report["metrics"]["uncalibrated"]["brier"]


def test_selected_calibrator_is_platt_or_isotonic():
    with open("data/razorpay_serving_calibration_report.json") as f:
        report = json.load(f)
    assert report["selected_calibrator"] in {"platt", "isotonic"}


# ── Calibrated artifact ────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def loader():
    return ServingModelLoader()


def test_calibrated_artifact_loads(loader):
    assert loader is not None
    assert len(loader.features) == 15


def test_feature_contract_enforced(loader):
    with open("data/razorpay_serving_feature_contract.json") as f:
        contract = json.load(f)
    expected = [feat["name"] for feat in contract["features"]]
    assert loader.features == expected


def test_no_target_in_features(loader):
    assert "isFraud" not in loader.features
    assert "TransactionID" not in loader.features


def test_no_rejected_feature_in_contract(loader):
    rejected = {"addr1", "addr2", "dist1", "R_emaildomain", "card2", "card3", "card5", "DeviceType"}
    for r in rejected:
        assert r not in loader.features, f"Rejected feature in loader contract: {r}"


def test_loader_rejects_model_c_path():
    with pytest.raises(ValueError, match="Model C"):
        ServingModelLoader("data/model_c_calibrated.joblib")


def test_loader_fails_on_missing_artifact():
    with pytest.raises(FileNotFoundError):
        ServingModelLoader("data/nonexistent_artifact.joblib")


def test_deterministic_calibrated_predictions(loader):
    dummy = {f: [0.5] if f not in ["email_domain", "card_network", "card_type"] else ["MISSING"]
             for f in loader.features}
    df = pd.DataFrame(dummy)
    p1 = loader.predict_calibrated_proba(df)
    p2 = loader.predict_calibrated_proba(df)
    np.testing.assert_array_equal(p1, p2)


def test_calibrated_probabilities_in_range(loader):
    dummy = {f: [0.1, 0.5, 0.9] if f not in ["email_domain", "card_network", "card_type"] else ["MISSING"] * 3
             for f in loader.features}
    df = pd.DataFrame(dummy)
    p = loader.predict_calibrated_proba(df)
    assert np.all(p >= 0) and np.all(p <= 1)


def test_calibration_uses_only_allowed_splits():
    """Calibration report must not contain test set DT range overlap."""
    with open("data/razorpay_serving_calibration_report.json") as f:
        report = json.load(f)
    test_df = pd.read_csv("data/razorpay_serving_dataset/test.csv")
    test_min_dt = test_df["TransactionDT"].min()
    cal_max_dt = report["calibration_split"]["cal_dt_range"][1]
    assert cal_max_dt < test_min_dt, "Calibration rows overlap with test set time range"
