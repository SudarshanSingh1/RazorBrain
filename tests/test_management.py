import pytest
import tempfile
import os

from database.migrations import run_migrations
from api.management_service import ModelManagementService, PolicyManagementService, ManagementError
from fastapi.testclient import TestClient
from api.app import app

@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    run_migrations(db_path=path)
    yield path
    os.remove(path)

@pytest.fixture
def model_service(temp_db):
    return ModelManagementService(db_path=temp_db)

@pytest.fixture
def policy_service(temp_db):
    return PolicyManagementService(db_path=temp_db)

# ── Model Tests ──────────────────────────────────────────────────────────────

def test_model_registry_bootstrap(model_service):
    active = model_service.get_active_model()
    assert active is not None
    assert active["model_version"] == "fraud-model-v1"
    assert active["status"] == "ACTIVE"
    assert active["feature_contract_version"] == "feature-contract-v1"

def test_register_and_activate_model(model_service, tmp_path):
    # create a dummy joblib file
    dummy_path = tmp_path / "dummy.joblib"
    import joblib
    joblib.dump({"dummy": True}, dummy_path)

    model = model_service.register_model({
        "model_name": "Test Model",
        "model_version": "v2.0",
        "artifact_path": str(dummy_path),
        "feature_contract_version": "v1",
    })
    
    assert model["status"] == "INACTIVE"
    
    # Activate
    active = model_service.activate_model(model["id"])
    assert active["status"] == "ACTIVE"
    
    # Check old model is inactive
    old_active = model_service.get_model("m-initial-legacy-v1")
    assert old_active["status"] == "INACTIVE"
    assert old_active["deactivated_at"] is not None

def test_activate_missing_artifact(model_service):
    model = model_service.register_model({
        "model_name": "Test Model",
        "model_version": "v3.0",
        "artifact_path": "/invalid/path/missing.joblib",
        "feature_contract_version": "v1",
    })
    
    with pytest.raises(ManagementError, match="Artifact missing"):
        model_service.activate_model(model["id"])
        
    # Ensure active model wasn't changed
    active = model_service.get_active_model()
    assert active["model_version"] == "fraud-model-v1"

# ── Policy Tests ─────────────────────────────────────────────────────────────

def test_policy_registry_bootstrap(policy_service):
    active = policy_service.get_active_policy()
    assert active is not None
    assert active["policy_version"] == "policy-v2"
    assert active["status"] == "ACTIVE"

def test_create_and_activate_policy(policy_service):
    config = {
        "thresholds": {
            "approve_max": 0.1,
            "review_max": 0.2,
            "step_up_max": 0.3
        }
    }
    policy = policy_service.create_policy({
        "policy_name": "Test Policy",
        "policy_version": "v3.0",
        "configuration": config
    })
    
    assert policy["status"] == "INACTIVE"
    
    # Activate
    active = policy_service.activate_policy(policy["id"])
    assert active["status"] == "ACTIVE"
    
    old_active = policy_service.get_policy("p-initial-legacy-v2")
    assert old_active["status"] == "INACTIVE"

def test_invalid_policy_thresholds(policy_service):
    config = {
        "thresholds": {
            "approve_max": 0.5,
            "review_max": 0.2, # Invalid ordering
            "step_up_max": 0.8
        }
    }
    with pytest.raises(ManagementError, match="Invalid threshold ordering"):
        policy_service.create_policy({
            "policy_name": "Test Policy",
            "policy_version": "v4.0",
            "configuration": config
        })

# ── API Tests ────────────────────────────────────────────────────────────────

def test_management_apis(temp_db, monkeypatch):
    monkeypatch.setenv("RAZORBRAIN_DB_PATH", temp_db)
    app.state.razor_state.db_path = temp_db
    
    with TestClient(app) as client:
        res = client.get("/management/models")
        assert res.status_code == 200
        assert len(res.json()["models"]) >= 1
        
        res = client.get("/management/policies")
        assert res.status_code == 200
        assert len(res.json()["policies"]) >= 1
