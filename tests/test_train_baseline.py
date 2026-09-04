import pytest
import pandas as pd
from model.real_feature_pipeline import RealFeaturePipeline
from model.real_feature_contract import PRIMARY_REAL_FEATURE_SET
import joblib

def test_target_excluded_from_x():
    assert "isFraud" not in PRIMARY_REAL_FEATURE_SET

def test_deterministic_feature_order():
    features = list(PRIMARY_REAL_FEATURE_SET.keys())
    assert features[0] == "log_amount"
    assert features[-1] == "m_match_count"

def test_model_artifact_loadable():
    try:
        artifact = joblib.load("data/offline_model_artifact.joblib")
        assert "model_artifact" in artifact
        assert "feature_order" in artifact
        assert "train_roc_auc" in artifact
        assert artifact["feature_order"] == list(PRIMARY_REAL_FEATURE_SET.keys())
    except FileNotFoundError:
        pytest.skip("Offline artifact not generated yet in test environment.")
    except ModuleNotFoundError as e:
        pytest.skip(f"Environment missing dependency for loading artifact: {e}")
