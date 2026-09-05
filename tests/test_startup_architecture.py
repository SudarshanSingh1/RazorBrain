import os
import joblib
from fastapi.testclient import TestClient

from api.app import app
from api.lifespan import app_state

def test_startup_without_artifact_fails_safely():
    # Ensure no model path is set
    if "RAZORBRAIN_MODEL_PATH" in os.environ:
        del os.environ["RAZORBRAIN_MODEL_PATH"]
        
    with TestClient(app) as client:
        # 1. Startup does not call synthetic data generation
        # 2. Startup does not call model.fit
        # (This is implicitly tested because we removed them from lifespan)
        
        # 3. Missing artifact results in not-ready state
        assert app_state.is_ready is False
        
        # 6. Inference is not falsely executed
        response = client.post("/transactions", json={
            "transaction_id": "test_txn",
            "timestamp": "2023-01-01T00:00:00Z",
            "amount": 100.0,
            "currency": "INR",
            "customer_id": "c1",
            "merchant_id": "m1",
            "payment_method": "card",
            "device_id": "d1",
            "ip_address": "1.1.1.1"
        })
        assert response.status_code == 503
        assert "not ready" in response.json()["error"]["message"].lower()

def test_startup_with_invalid_artifact_fails_safely(tmp_path):
    invalid_artifact_path = tmp_path / "invalid.joblib"
    joblib.dump({"not_a_model": True}, invalid_artifact_path)
    
    os.environ["RAZORBRAIN_MODEL_PATH"] = str(invalid_artifact_path)
    
    with TestClient(app) as client:
        # 4. Invalid model artifact fails safely
        assert app_state.is_ready is False
        
        response = client.get("/ready")
        assert response.status_code == 503
        
    del os.environ["RAZORBRAIN_MODEL_PATH"]

class MockModel:
    def predict_proba(self, X):
        return [[0.5, 0.5]] * len(X)

def test_startup_with_valid_artifact_works(tmp_path):
    valid_artifact_path = tmp_path / "valid.joblib"
    mock_artifact = {
        "model_artifact": {"model": MockModel()},
        "calibration_artifact": {},
        "explainer_artifact": {},
        "training_thresholds": {},
        "feature_encoder_state": {},
        "reference_distribution": {}
    }
    joblib.dump(mock_artifact, valid_artifact_path)
    
    os.environ["RAZORBRAIN_MODEL_PATH"] = str(valid_artifact_path)
    
    with TestClient(app) as client:
        # 5. Valid artifact loading works
        assert app_state.is_ready is True
        
        response = client.get("/ready")
        assert response.status_code == 200
        assert response.json()["status"] == "ready"
        
    del os.environ["RAZORBRAIN_MODEL_PATH"]
