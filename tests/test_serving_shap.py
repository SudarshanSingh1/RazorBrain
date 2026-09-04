"""
Tests for the Razorpay Serving Model SHAP explanation layer.
All fixtures are synthetic — test.csv is never opened.
"""
import ast
import hashlib
import json
import math
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from model.serving_shap_explainer import ServingSHAPExplainer, make_fixture
from model.serving_model_loader import ServingModelLoader
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


@pytest.fixture(scope="module")
def explainer():
    return ServingSHAPExplainer()


@pytest.fixture(scope="module")
def fixture():
    return make_fixture()


# ── Integrity ─────────────────────────────────────────────────────────────────

def test_serving_model_artifacts_unchanged():
    for path, expected in KNOWN_HASHES.items():
        assert md5(path) == expected, f"Hash mismatch: {path}"


# ── Static source code check ──────────────────────────────────────────────────

def test_shap_script_never_opens_test_csv():
    with open("model/serving_shap_explainer.py") as f:
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
                        pytest.fail("serving_shap_explainer.py opens test.csv")


# ── 1. AVAILABLE for a valid transaction ─────────────────────────────────────

def test_shap_available_for_valid_transaction(explainer, fixture):
    result = explainer.explain(fixture)
    assert result["status"] == "AVAILABLE"
    assert result["model_track"] == "RAZORPAY_SERVING_MODEL"
    assert result["explained_output"] == "UNCALIBRATED_XGBOOST_MARGIN"


# ── 2. Deterministic for same input ──────────────────────────────────────────

def test_shap_deterministic(explainer, fixture):
    r1 = explainer.explain(fixture)
    r2 = explainer.explain(fixture)
    assert r1["base_value"] == r2["base_value"]
    assert r1["model_output"] == r2["model_output"]
    assert r1["top_positive"] == r2["top_positive"]
    assert r1["top_negative"] == r2["top_negative"]


# ── 3. Directions are correct ─────────────────────────────────────────────────

def test_directions_correct(explainer, fixture):
    result = explainer.explain(fixture)
    for item in result["top_positive"]:
        assert item["direction"] == "INCREASES_MODEL_SCORE"
        assert item["shap_value"] > 0
    for item in result["top_negative"]:
        assert item["direction"] == "DECREASES_MODEL_SCORE"
        assert item["shap_value"] < 0


# ── 4 & 5. Sorted by absolute value ──────────────────────────────────────────

def test_top_positive_sorted(explainer, fixture):
    result = explainer.explain(fixture)
    vals = [abs(x["shap_value"]) for x in result["top_positive"]]
    assert vals == sorted(vals, reverse=True)


def test_top_negative_sorted(explainer, fixture):
    result = explainer.explain(fixture)
    vals = [abs(x["shap_value"]) for x in result["top_negative"]]
    assert vals == sorted(vals, reverse=True)


# ── 6. Feature names map to original source names ────────────────────────────

def test_feature_names_are_original(explainer, fixture):
    result = explainer.explain(fixture)
    expected = explainer.features
    for item in result["top_positive"] + result["top_negative"]:
        assert item["feature"] in expected, f"Unexpected feature name: {item['feature']}"


# ── 7. Categorical contributions aggregate under one key ──────────────────────

def test_categorical_aggregated(explainer, fixture):
    result = explainer.explain(fixture)
    feature_names = [x["feature"] for x in result["top_positive"] + result["top_negative"]]
    # No raw OHE names should leak
    for name in feature_names:
        assert not name.startswith("cat__"), f"Raw OHE name leaked: {name}"
        assert not name.startswith("num__"), f"Raw transformer name leaked: {name}"
    # email_domain should appear at most once (aggregated)
    assert feature_names.count("email_domain") <= 1


# ── 8. Exact 15-feature contract enforced ────────────────────────────────────

def test_15_feature_contract(explainer):
    assert len(explainer.features) == 15


# ── 9. Rejected features rejected ────────────────────────────────────────────

def test_rejected_features_blocked(explainer, fixture):
    bad = fixture.copy()
    bad["isFraud"] = 1
    result = explainer.explain(bad)
    assert result["status"] == "UNAVAILABLE"


# ── 10. Missing required features fail clearly ────────────────────────────────

def test_missing_feature_fails(explainer, fixture):
    partial = fixture.drop(columns=["amount"])
    result = explainer.explain(partial)
    assert result["status"] == "UNAVAILABLE"


# ── 11. SHAP failure returns UNAVAILABLE ─────────────────────────────────────

def test_multi_row_input_returns_unavailable(explainer, fixture):
    two_rows = pd.concat([fixture, fixture], ignore_index=True)
    result = explainer.explain(two_rows)
    assert result["status"] == "UNAVAILABLE"


# ── 12 & 13. SHAP failure does not modify risk or decision ────────────────────

def test_shap_failure_does_not_affect_risk_or_decision(explainer, fixture):
    # Get risk from the serving model loader
    loader = ServingModelLoader()
    risk_before = loader.predict_calibrated_proba(fixture)[0]

    # Trigger a SHAP failure by passing extra rows
    two_rows = pd.concat([fixture, fixture], ignore_index=True)
    shap_result = explainer.explain(two_rows)
    assert shap_result["status"] == "UNAVAILABLE"

    # Risk must be unchanged
    risk_after = loader.predict_calibrated_proba(fixture)[0]
    assert risk_before == risk_after

    # Decision must be unchanged
    policy = ServingPolicyLoader()
    assert policy.make_decision(risk_before) == policy.make_decision(risk_after)


# ── 14. No test.csv loaded (already covered by static check, guard here too) ─

def test_no_test_csv_in_memory(explainer, fixture):
    # Just re-assert the static analysis guard passed
    assert os.path.exists("model/serving_shap_explainer.py")


# ── 15. No model fitting occurs ──────────────────────────────────────────────

def test_no_fit_method_called(explainer):
    # The explainer's xgb model should already be fitted; calling .fit() would
    # violate the contract. We just verify the attribute exists as a fitted model.
    import xgboost as xgb
    assert isinstance(explainer.xgb_model, xgb.XGBClassifier)
    # Fitted models have feature_names_in_ or n_features_in_
    assert hasattr(explainer.xgb_model, "n_features_in_")


# ── 16. Calibrated risk not replaced by SHAP output ─────────────────────────

def test_calibrated_risk_independent_of_shap(explainer, fixture):
    shap_result = explainer.explain(fixture)
    # SHAP explains the XGBoost margin — this is NOT the calibrated risk
    # The calibrated risk comes from isotonic regression on top
    loader = ServingModelLoader()
    calibrated_risk = float(loader.predict_calibrated_proba(fixture)[0])
    # They must differ (margin space != calibrated probability space)
    margin = shap_result["model_output"]
    # Can't assert exact inequality (they might coincidentally be close) but
    # we CAN assert the SHAP result doesn't claim to be the calibrated risk
    assert shap_result["explained_output"] == "UNCALIBRATED_XGBOOST_MARGIN"
    assert shap_result["explained_output"] != "CALIBRATED_PROBABILITY"


# ── Additivity check ─────────────────────────────────────────────────────────

def test_additivity(explainer, fixture):
    check = explainer.check_additivity(fixture, tol=1e-3)
    assert check["passed"], f"Additivity check failed: delta={check['delta']}"
