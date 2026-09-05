import pytest
from fastapi.testclient import TestClient
import json
from api.app import app

client = TestClient(app)

@pytest.fixture
def mock_razorpay_env(monkeypatch):
    monkeypatch.setenv("RAZORPAY_KEY_ID", "test_key_id")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "test_key_secret")

def test_investigate_serving_assessment(mock_razorpay_env):
    db_path = app.state.razor_state.db_path
    from database.connection import get_session
    
    assessment_id = "order_inv123_pay_inv123"
    txn_id = "pay_inv123"
    
    with get_session(db_path) as conn:
        c = conn.cursor()
        c.execute('''
            INSERT OR IGNORE INTO transactions (transaction_id, timestamp, amount, customer_id, merchant_id, context_data)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (txn_id, "2024-01-01T00:00:00Z", 70.0, "inv@test.com", "m1", json.dumps({"currency": "INR", "payment_method": "card"})))
        
        c.execute('''
            INSERT OR IGNORE INTO serving_assessments (
                assessment_id, transaction_id, assessment_type, model_track,
                timestamp, risk, decision, decision_reason, feature_snapshot,
                feature_availability, shap_snapshot, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            assessment_id, txn_id, "POST_EVENT_RISK_ASSESSMENT", "RAZORPAY_SERVING_MODEL",
            "2024-01-01T00:00:00Z", 0.25, "REVIEW",
            json.dumps({"decision": "REVIEW", "calibrated_risk": 0.25}),
            json.dumps({"amount": 70.0}),
            json.dumps({"amount": True}),
            json.dumps({"features_contributions": [{"feature": "amount", "contribution": 0.1}]}),
            "2024-01-01T00:00:00Z"
        ))
        conn.commit()
    
    app.state.razor_state.is_ready = True
    response = client.get(f"/razorpay/test/investigate/{assessment_id}", headers={"X-API-Key": "dev-api-key-123"})
    assert response.status_code == 200
    data = response.json()
    assert data["assessment_id"] == assessment_id
    assert data["transaction_id"] == txn_id
    assert data["amount"] == 70.0
    assert data["customer_id"] == "inv@test.com"
    assert data["merchant_id"] == "m1"
    assert data["risk"] == 0.25
    assert data["decision"] == "REVIEW"
    assert data["model_track"] == "RAZORPAY_SERVING_MODEL"
    assert "amount" in data["feature_snapshot"]
    assert "amount" in data["feature_availability"]
    assert data["shap"]["features_contributions"][0]["feature"] == "amount"

def test_investigate_serving_assessment_not_found(mock_razorpay_env):
    app.state.razor_state.is_ready = True
    response = client.get("/razorpay/test/investigate/nonexistent", headers={"X-API-Key": "dev-api-key-123"})
    assert response.status_code == 404
    assert "not found" in response.json()["error"]["message"].lower()

