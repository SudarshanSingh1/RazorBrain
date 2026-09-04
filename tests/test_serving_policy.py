"""
Tests for the Razorpay Serving Model risk decision policy.
Verifies:
  - test.csv is never opened by the optimizer script.
  - all artifact hashes remain unchanged.
  - policy loader enforces T_review < T_block and handles invalid inputs.
  - deterministic ALLOW/REVIEW/BLOCK boundary behavior.
"""
import ast
import hashlib
import json
import math
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from model.serving_policy_loader import ServingPolicyLoader

KNOWN_HASHES = {
    "data/razorpay_serving_model_calibrated.joblib": "1aada82e6f1af13bcada372eb02ec312",
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

def test_frozen_serving_test_hash():
    assert md5("data/razorpay_serving_dataset/test.csv") == KNOWN_HASHES["data/razorpay_serving_dataset/test.csv"]

def test_calibrated_model_hash():
    assert md5("data/razorpay_serving_model_calibrated.joblib") == KNOWN_HASHES["data/razorpay_serving_model_calibrated.joblib"]

def test_uncalibrated_model_hash():
    assert md5("data/razorpay_serving_model_uncalibrated.joblib") == KNOWN_HASHES["data/razorpay_serving_model_uncalibrated.joblib"]

def test_model_c_hashes():
    for path in [
        "data/model_c_calibrated.joblib",
        "data/model_c_engineered_raw_safe.joblib",
        "data/validation_selected_policy.json",
    ]:
        assert md5(path) == KNOWN_HASHES[path], f"Model C artifact modified: {path}"


# ── Optimizer Static Analysis ─────────────────────────────────────────────────

def test_optimizer_never_opens_test_csv():
    """Static check: optimize_serving_policy.py must not open test.csv."""
    with open("model/optimize_serving_policy.py") as f:
        source = f.read()

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
                        pytest.fail(f"optimize_serving_policy.py calls {func_name}('...test.csv')")


# ── Policy Artifact & Loader ──────────────────────────────────────────────────

@pytest.fixture
def loader():
    return ServingPolicyLoader()


def test_loader_loads_successfully(loader):
    assert loader is not None
    assert loader.t_review < loader.t_block


def test_t_review_less_than_t_block(loader):
    assert loader.t_review < loader.t_block
    assert math.isfinite(loader.t_review)
    assert math.isfinite(loader.t_block)


def test_allow_boundary(loader):
    assert loader.make_decision(0.0) == "ALLOW"
    assert loader.make_decision(loader.t_review - 0.0001) == "ALLOW"


def test_review_boundary(loader):
    assert loader.make_decision(loader.t_review) == "REVIEW"
    assert loader.make_decision(loader.t_review + 0.0001) == "REVIEW"
    assert loader.make_decision(loader.t_block - 0.0001) == "REVIEW"


def test_block_boundary(loader):
    assert loader.make_decision(loader.t_block) == "BLOCK"
    assert loader.make_decision(loader.t_block + 0.0001) == "BLOCK"
    assert loader.make_decision(1.0) == "BLOCK"


def test_invalid_risk_returns_review(loader):
    # Safe fallback on invalid/NaN
    assert loader.make_decision(None) == "REVIEW"
    assert loader.make_decision(np.nan) == "REVIEW"
    assert loader.make_decision(float("inf")) == "REVIEW"
    assert loader.make_decision("not a number") == "REVIEW"


def test_loader_rejects_wrong_track(tmp_path):
    policy = {
        "model_track": "MODEL_C",
        "policy_status": "VALIDATION_SELECTED",
        "threshold_review": 0.1,
        "threshold_block": 0.2
    }
    p = tmp_path / "bad.json"
    with open(p, "w") as f:
        json.dump(policy, f)
    with pytest.raises(ValueError, match="Invalid model track"):
        ServingPolicyLoader(str(p))


def test_loader_rejects_missing_thresholds(tmp_path):
    policy = {
        "model_track": "RAZORPAY_SERVING_MODEL",
        "policy_status": "VALIDATION_SELECTED",
    }
    p = tmp_path / "bad.json"
    with open(p, "w") as f:
        json.dump(policy, f)
    with pytest.raises(ValueError, match="Missing threshold"):
        ServingPolicyLoader(str(p))


def test_loader_rejects_malformed_thresholds(tmp_path):
    policy = {
        "model_track": "RAZORPAY_SERVING_MODEL",
        "policy_status": "VALIDATION_SELECTED",
        "threshold_review": 0.3,
        "threshold_block": 0.1  # t_block < t_review!
    }
    p = tmp_path / "bad.json"
    with open(p, "w") as f:
        json.dump(policy, f)
    with pytest.raises(ValueError, match="must be < T_block"):
        ServingPolicyLoader(str(p))
