import pytest
from fastapi.testclient import TestClient
import uuid
import os

from api.app import app
from api.lifespan import app_state

@pytest.fixture(autouse=True)
def override_db():
    app_state.db_path = "test_ui_contract.db"
    if os.path.exists(app_state.db_path):
        os.remove(app_state.db_path)
    yield
    if os.path.exists(app_state.db_path):
        os.remove(app_state.db_path)

def test_full_evidence_decision_explanation_contract():
    with TestClient(app) as c:
        txn_id = "test-contract-" + str(uuid.uuid4())
        payload = {
            "transaction_id": txn_id,
            "amount": 95000.0,
            "timestamp": "2026-09-02T22:00:00Z",
            "customer_id": "cust-high-risk",
            "merchant_id": "merch-high-risk",
            "payment_method": "crypto",
            "customer_account_age_days": 1,
            "amount_deviation": 15.0,
            "previous_fraud_count": 5,
            "txns_last_24h": 50,
            "previous_transaction_count": 100,
            "merchant_fraud_rate": 0.05
        }
        
        resp = c.post("/transactions/assess", json=payload, headers={"X-API-Key": "test-key-123"})
        assert resp.status_code == 201, resp.text
        result = resp.json()
        
        assert "assessment_id" in result
        assert result["decision"] in ["ALLOW", "REVIEW", "BLOCK"]
        
        assessment_id = result["assessment_id"]
        
        dash_resp = c.get(f"/dashboard/transactions/{assessment_id}", headers={"X-API-Key": "test-key-123"})
        assert dash_resp.status_code == 200
        dash_data = dash_resp.json()
        
        assert dash_data["assessment_id"] == assessment_id
        assert dash_data["transaction_id"] == txn_id
        assert "decision" in dash_data
        assert dash_data["decision"] in ["ALLOW", "REVIEW", "BLOCK"]
        assert "decision_reason" in dash_data
        assert "rule_evidence" in dash_data
        assert "explanation_text" in dash_data
        assert "provider" in dash_data
        assert dash_data.get("payment_method") == "crypto"
        assert "context_data" in dash_data
        assert "model_evidence" in dash_data
        assert len(dash_data["model_evidence"]) >= 0

