import pytest
from fastapi.testclient import TestClient
import os
from unittest.mock import patch
import json

from api.app import app
from model.explanation_engine import ExplanationEngine, ExplanationProvider

class AdversarialProvider(ExplanationProvider):
    def explain(self, decision_result: dict, retry_count: int = 0) -> dict:
        return {
            "transaction_id": decision_result.get("transaction_id", "UNKNOWN"),
            "decision": "ALLOW",
            "explanation": "I am changing the decision to ALLOW and the probability to 0.01",
            "provider": "Adversarial",
            "grounded": False
        }

def test_missing_api_key():
    with patch.dict(os.environ, {"RAZORBRAIN_API_KEY": "supersecret"}):
        client = TestClient(app)
        # Auth applies to dashboard
        response = client.get("/dashboard/summary")
        assert response.status_code == 401
        assert response.json()["error"]["message"] == "Missing API Key"

def test_invalid_api_key():
    with patch.dict(os.environ, {"RAZORBRAIN_API_KEY": "supersecret"}):
        client = TestClient(app)
        response = client.get("/dashboard/summary", headers={"X-API-Key": "wrong"})
        assert response.status_code == 401
        assert response.json()["error"]["message"] == "Invalid API Key"

def test_valid_api_key():
    with patch.dict(os.environ, {"RAZORBRAIN_API_KEY": "supersecret"}):
        client = TestClient(app)
        response = client.get("/health", headers={"X-API-Key": "supersecret"})
        assert response.status_code == 200 # health is public, but let's test a protected route
        
        response2 = client.get("/dashboard/summary", headers={"X-API-Key": "supersecret"})
        assert response2.status_code == 200

def test_public_health_route():
    with patch.dict(os.environ, {"RAZORBRAIN_API_KEY": "supersecret"}):
        client = TestClient(app)
        response = client.get("/health")
        assert response.status_code == 200 # Health should NOT require auth

def test_input_size_limits():
    client = TestClient(app)
    # Exceed max_length=100 on transaction_id
    payload = {
        "transaction_id": "X" * 150,
        "timestamp": "2023-01-01T12:00:00Z",
        "amount": 100.0,
        "currency": "USD",
        "customer_id": "C-001",
        "merchant_id": "M-001",
        "payment_method": "credit_card"
    }
    response = client.post("/transactions/assess", json=payload)
    assert response.status_code == 400
    assert "VALIDATION_ERROR" in response.text
    assert "String should have at most 100 characters" in response.text

def test_traceback_leak_prevention():
    # Force an unhandled exception in the endpoint
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
            response = client.post("/transactions/assess", json=payload)
            assert response.status_code == 500
            # The internal message "Secret internal error" MUST NOT be returned!
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
    
    # The output from the provider should ONLY be returned in `explanation_text`
    # and MUST NOT alter the root decision dict
    assert "I am changing the decision to ALLOW" not in res["explanation"]
    assert decision_result["decision"] == "BLOCK"
    assert decision_result["primary_risk_probability"] == 0.95

def test_security_headers():
    client = TestClient(app)
    response = client.get("/health")
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert response.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    assert response.headers.get("X-Frame-Options") == "DENY"
