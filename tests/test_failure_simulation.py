import pytest
from fastapi.testclient import TestClient
import os
import tempfile
from unittest.mock import patch

from database.migrations import run_migrations
from api.app import app
from api.security_service import SecurityService

@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    run_migrations(db_path=path)
    yield path
    os.remove(path)

def test_model_failure_graceful_handling(temp_db, monkeypatch):
    monkeypatch.setenv("RAZORBRAIN_DB_PATH", temp_db)
    monkeypatch.setenv("RAZORBRAIN_TEST_MODE", "0")
    app.state.razor_state.db_path = temp_db
    with patch("model.serving_model_loader.ServingModelLoader.predict_proba", side_effect=Exception("Simulated XGBoost crash")):
        with TestClient(app) as client:
            svc = SecurityService(temp_db)
            meta, raw_secret = svc.create_api_key("Sim Testing", "ADMIN")
            payload = {"amount": 500}
            res = client.post("/transactions/decide", json=payload, headers={"X-API-Key": raw_secret})
            assert res.status_code in [500, 503]
            assert "Simulated XGBoost crash" not in res.text

def test_rule_engine_failure_graceful_handling(temp_db, monkeypatch):
    monkeypatch.setenv("RAZORBRAIN_DB_PATH", temp_db)
    monkeypatch.setenv("RAZORBRAIN_TEST_MODE", "0")
    app.state.razor_state.db_path = temp_db
    with patch("model.serving_rule_engine.ServingRuleEngine.evaluate", side_effect=Exception("Rule evaluation failed")):
        with TestClient(app) as client:
            svc = SecurityService(temp_db)
            meta, raw_secret = svc.create_api_key("Sim Testing", "ADMIN")
            payload = {"amount": 500}
            res = client.post("/transactions/decide", json=payload, headers={"X-API-Key": raw_secret})
            assert res.status_code in [500, 503]

def test_fusion_failure_graceful_handling(temp_db, monkeypatch):
    monkeypatch.setenv("RAZORBRAIN_DB_PATH", temp_db)
    monkeypatch.setenv("RAZORBRAIN_TEST_MODE", "0")
    app.state.razor_state.db_path = temp_db
    with patch("model.serving_risk_fusion.HybridRiskFusionEngine.fuse", side_effect=Exception("Fusion failed")):
        with TestClient(app) as client:
            svc = SecurityService(temp_db)
            meta, raw_secret = svc.create_api_key("Sim Testing", "ADMIN")
            payload = {"amount": 500}
            res = client.post("/transactions/decide", json=payload, headers={"X-API-Key": raw_secret})
            assert res.status_code in [500, 503]

def test_explanation_provider_failure(temp_db, monkeypatch):
    monkeypatch.setenv("RAZORBRAIN_DB_PATH", temp_db)
    monkeypatch.setenv("RAZORBRAIN_TEST_MODE", "0")
    app.state.razor_state.db_path = temp_db
    with patch("model.serving_explanation_service.ServingExplanationService.explain_transaction", return_value={"status": "UNAVAILABLE", "reason": "SHAP failed"}):
        with TestClient(app) as client:
            svc = SecurityService(temp_db)
            meta, raw_secret = svc.create_api_key("Sim Testing", "ADMIN")
            payload = {"amount": 500, "include_explanation": True}
            res = client.post("/transactions/decide", json=payload, headers={"X-API-Key": raw_secret})
            assert res.status_code == 200
            assert res.json()["decision"].get("explanation", {}).get("status") == "UNAVAILABLE"

def test_case_management_invalid_transition(temp_db, monkeypatch):
    monkeypatch.setenv("RAZORBRAIN_DB_PATH", temp_db)
    monkeypatch.setenv("RAZORBRAIN_TEST_MODE", "0")
    app.state.razor_state.db_path = temp_db
    with TestClient(app) as client:
        svc = SecurityService(temp_db)
        meta, raw_secret = svc.create_api_key("Sim Testing", "ADMIN")
        
        res = client.post("/transactions/decide", json={"amount": 500}, headers={"X-API-Key": raw_secret})
        assessment_id = res.json()["decision"]["case"]["assessment_id"]
        
        res3 = client.post(f"/cases/{assessment_id}/resolve", json={"resolution": "FRAUD_CONFIRMED", "notes": "resolved"}, headers={"X-API-Key": raw_secret})
        assert res3.status_code == 200
        
        res4 = client.post(f"/cases/{assessment_id}/escalate", json={"notes": "escalate"}, headers={"X-API-Key": raw_secret})
        assert res4.status_code == 400
