import pytest
from fastapi.testclient import TestClient
import os
from unittest.mock import patch
import tempfile

from api.app import app
from model.explanation_engine import ExplanationEngine, ExplanationProvider
from api.security_service import SecurityService, AuthenticationError
from database.migrations import run_migrations

class AdversarialProvider(ExplanationProvider):
    def explain(self, decision_result: dict, retry_count: int = 0) -> dict:
        return {
            "transaction_id": decision_result.get("transaction_id", "UNKNOWN"),
            "decision": "ALLOW",
            "explanation": "I am changing the decision to ALLOW and the probability to 0.01",
            "provider": "Adversarial",
            "grounded": False
        }

@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    run_migrations(db_path=path)
    yield path
    os.remove(path)

def test_missing_api_key(temp_db, monkeypatch):
    monkeypatch.setenv('RAZORBRAIN_DB_PATH', temp_db)
    monkeypatch.setenv('RAZORBRAIN_TEST_MODE', '0')
    app.state.razor_state.db_path = temp_db
    monkeypatch.setenv("RAZORBRAIN_API_KEY", "supersecret")
    client = TestClient(app)
    response = client.get("/dashboard/summary")
    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Missing API Key"

def test_invalid_api_key(temp_db, monkeypatch):
    monkeypatch.setenv('RAZORBRAIN_DB_PATH', temp_db)
    monkeypatch.setenv('RAZORBRAIN_TEST_MODE', '0')
    app.state.razor_state.db_path = temp_db
    monkeypatch.setenv("RAZORBRAIN_API_KEY", "supersecret")
    client = TestClient(app)
    response = client.get("/dashboard/summary", headers={"X-API-Key": "wrong"})
    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Invalid API Key"

def test_valid_api_key(temp_db, monkeypatch):
    monkeypatch.setenv('RAZORBRAIN_DB_PATH', temp_db)
    monkeypatch.setenv('RAZORBRAIN_TEST_MODE', '0')
    app.state.razor_state.db_path = temp_db
    monkeypatch.setenv("RAZORBRAIN_API_KEY", "supersecret")
    client = TestClient(app)
    response = client.get("/health", headers={"X-API-Key": "supersecret"})
    assert response.status_code == 200
    
    response2 = client.get("/dashboard/summary", headers={"X-API-Key": "supersecret"})
    assert response2.status_code == 200

def test_public_health_route(temp_db, monkeypatch):
    monkeypatch.setenv('RAZORBRAIN_DB_PATH', temp_db)
    monkeypatch.setenv('RAZORBRAIN_TEST_MODE', '0')
    app.state.razor_state.db_path = temp_db
    monkeypatch.setenv("RAZORBRAIN_API_KEY", "supersecret")
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200

def test_input_size_limits(temp_db, monkeypatch):
    monkeypatch.setenv('RAZORBRAIN_DB_PATH', temp_db)
    monkeypatch.setenv('RAZORBRAIN_TEST_MODE', '0')
    app.state.razor_state.db_path = temp_db
    monkeypatch.setenv("RAZORBRAIN_API_KEY", "supersecret")
    with TestClient(app) as client:
        payload = {
            "transaction_id": "X" * 150,
            "timestamp": "2023-01-01T12:00:00Z",
            "amount": 100.0,
            "currency": "USD",
            "customer_id": "C-001",
            "merchant_id": "M-001",
            "payment_method": "credit_card"
        }
        response = client.post("/transactions/decide", json=payload, headers={"X-API-Key": "supersecret"})
        assert response.status_code == 400
        assert "VALIDATION_ERROR" in response.text
        assert "String should have at most 100 characters" in response.text

def test_traceback_leak_prevention(temp_db, monkeypatch):
    monkeypatch.setenv('RAZORBRAIN_DB_PATH', temp_db)
    monkeypatch.setenv('RAZORBRAIN_TEST_MODE', '0')
    app.state.razor_state.db_path = temp_db
    monkeypatch.setenv("RAZORBRAIN_API_KEY", "supersecret")
    with patch("api.routes.assess_transaction", side_effect=ValueError("Secret internal error")):
        with TestClient(app) as client:
            payload = {
                "transaction_id": "TX-1",
                "timestamp": "2023-01-01T12:00:00Z",
                "amount": 100.0,
                "currency": "USD",
                "customer_id": "C-001",
                "merchant_id": "M-001",
                "payment_method": "credit_card"
            }
            # assess doesn't have idempotency but uses same validation
            response = client.post("/transactions/assess", json=payload, headers={"X-API-Key": "supersecret"})
            assert response.status_code == 500
            assert "Secret internal error" not in response.text
            assert "Internal server error" in response.text

def test_explanation_provider_compromise():
    engine = ExplanationEngine(primary_provider=AdversarialProvider())
    decision_result = {
        "transaction_id": "TX-1",
        "decision": "BLOCK",
        "primary_risk_probability": 0.95,
        "rule_evidence": []
    }
    res = engine.explain(decision_result)
    assert "I am changing the decision to ALLOW" not in res["explanation"]
    assert decision_result["decision"] == "BLOCK"
    assert decision_result["primary_risk_probability"] == 0.95

def test_security_headers(temp_db, monkeypatch):
    monkeypatch.setenv('RAZORBRAIN_DB_PATH', temp_db)
    monkeypatch.setenv('RAZORBRAIN_TEST_MODE', '0')
    app.state.razor_state.db_path = temp_db
    client = TestClient(app)
    response = client.get("/health")
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert response.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    assert response.headers.get("X-Frame-Options") == "DENY"

def test_api_key_lifecycle(temp_db):
    security_service = SecurityService(db_path=temp_db)
    meta, secret = security_service.create_api_key("test_key", "SCORER")
    assert meta["role"] == "SCORER"
    assert meta["status"] == "ACTIVE"
    assert meta["id"].startswith("ak_")
    
    auth_meta = security_service.authenticate_key(secret)
    assert auth_meta["id"] == meta["id"]
    
    security_service.revoke_api_key(meta["id"])
    with pytest.raises(AuthenticationError, match="API Key is REVOKED"):
        security_service.authenticate_key(secret)

def test_api_key_rotation(temp_db):
    security_service = SecurityService(db_path=temp_db)
    meta1, secret1 = security_service.create_api_key("test_key", "SCORER")
    meta2, secret2 = security_service.rotate_api_key(meta1["id"], "test_key_v2", "SCORER")
    
    assert security_service.authenticate_key(secret1)["id"] == meta1["id"]
    assert security_service.authenticate_key(secret2)["id"] == meta2["id"]
    
    security_service.revoke_api_key(meta1["id"])
    with pytest.raises(AuthenticationError):
        security_service.authenticate_key(secret1)
    assert security_service.authenticate_key(secret2)["id"] == meta2["id"]

def test_missing_api_key_rejected(temp_db, monkeypatch):
    monkeypatch.setenv("RAZORBRAIN_DB_PATH", temp_db)
    monkeypatch.setenv("RAZORBRAIN_TEST_MODE", "0")
    app.state.razor_state.db_path = temp_db
    with TestClient(app) as client:
        res = client.post("/transactions/decide", json={})
        assert res.status_code == 401

def test_idempotency_protection(temp_db, monkeypatch):
    monkeypatch.setenv("RAZORBRAIN_DB_PATH", temp_db)
    monkeypatch.setenv("RAZORBRAIN_TEST_MODE", "0")
    app.state.razor_state.db_path = temp_db
    monkeypatch.setenv("RAZORBRAIN_API_KEY", "legacy_secret")
    with TestClient(app) as client:
        payload = {
            "amount": 100,
            "customer_id": "c1",
            "email": "test@test.com"
        }
        
        res1 = client.post("/transactions/decide", json=payload, headers={
            "X-API-Key": "legacy_secret",
            "Idempotency-Key": "test_idemp_key_1"
        })
        assert res1.status_code == 200
        
        res2 = client.post("/transactions/decide", json=payload, headers={
            "X-API-Key": "legacy_secret",
            "Idempotency-Key": "test_idemp_key_1"
        })
        assert res2.status_code == 200
        assert res1.json()["decision"]["transaction_id"] == res2.json()["decision"]["transaction_id"]
        
        payload2 = {
            "amount": 500,
            "customer_id": "c1",
            "email": "test@test.com"
        }
        res3 = client.post("/transactions/decide", json=payload2, headers={
            "X-API-Key": "legacy_secret",
            "Idempotency-Key": "test_idemp_key_1"
        })
        assert res3.status_code == 400
        assert "already used" in res3.json()["error"]["message"]

def test_request_size_limit(temp_db, monkeypatch):
    monkeypatch.setenv("RAZORBRAIN_DB_PATH", temp_db)
    monkeypatch.setenv("RAZORBRAIN_TEST_MODE", "0")
    app.state.razor_state.db_path = temp_db
    monkeypatch.setenv("RAZORBRAIN_API_KEY", "legacy_secret")
    with TestClient(app) as client:
        large_payload = {"key": "x" * 2000000}
        res = client.post("/transactions/decide", json=large_payload, headers={"X-API-Key": "legacy_secret"})
        assert res.status_code == 413
        assert res.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"
