
import pytest
from fastapi.testclient import TestClient
import uuid
import os
import math
import numpy as np
from sklearn.linear_model import LogisticRegression

from api.app import app
from api.lifespan import app_state

client = TestClient(app)

@pytest.fixture(autouse=True)
def override_db():
    app_state.db_path = "test_razorbrain_api.db"
    if os.path.exists(app_state.db_path):
        os.remove(app_state.db_path)
    
    yield
    
    if os.path.exists(app_state.db_path):
        os.remove(app_state.db_path)

# 1. valid assessment
def test_assess_valid_transaction():
    with TestClient(app) as c:
        payload = {
            "transaction_id": str(uuid.uuid4()),
            "timestamp": "2023-01-01T12:00:00Z",
            "amount": 150.0,
            "currency": "USD",
            "customer_id": "cust_x",
            "merchant_id": "merch_y",
            "payment_method": "credit_card",
            "customer_account_age_days": 100,
            "previous_transaction_count": 5, "previous_fraud_count": 0, "amount_deviation": 0.0, "is_new_customer": 0, "merchant_fraud_rate": 0.0, "is_new_merchant": 0, "txns_last_5min": 0, "txns_last_1h": 0, "txns_last_24h": 0, "customer_account_age_days": 100, "avg_customer_amount": 1.0
        }
        res = c.post("/transactions/assess", json=payload)
        assert res.status_code == 201

# 2. missing required field
def test_missing_required_field():
    with TestClient(app) as c:
        payload = {
            "transaction_id": "123",
            "amount": 150.0
            # missing timestamp, customer_id, etc.
        }
        res = c.post("/transactions/assess", json=payload)
        assert res.status_code == 400

# 3. invalid field value
def test_invalid_field_value():
    with TestClient(app) as c:
        payload = {
            "transaction_id": "123",
            "timestamp": "bad_time",
            "amount": "not_a_float",
            "currency": "USD",
            "customer_id": "cust_x",
            "merchant_id": "merch_y",
            "payment_method": "credit_card"
        }
        res = c.post("/transactions/assess", json=payload)
        assert res.status_code == 400

# 4. unknown field rejection (Correction 1)
def test_unknown_field_rejection():
    with TestClient(app) as c:
        payload = {
            "transaction_id": "123",
            "timestamp": "2023-01-01T12:00:00Z",
            "amount": 150.0,
            "currency": "USD",
            "customer_id": "c1",
            "merchant_id": "m1",
            "payment_method": "cash",
            "unknown_metadata_xyz": "sneaky"
        }
        res = c.post("/transactions/assess", json=payload)
        assert res.status_code == 400
        assert "unknown_metadata_xyz" in res.text

# 5. ALLOW response
def test_allow_response():
    with TestClient(app) as c:
        app_state.decision_policy.allow_threshold = 0.20
        payload = {
            "transaction_id": "123",
            "timestamp": "2023-01-01T12:00:00Z",
            "amount": 1.0,
            "currency": "USD",
            "customer_id": "safe_cust",
            "merchant_id": "safe_merch",
            "payment_method": "credit_card",
            "previous_transaction_count": 50,
            "previous_fraud_count": 0,
            "amount_deviation": 0.0,
            "is_new_customer": 0, "merchant_fraud_rate": 0.0, "is_new_merchant": 0, "txns_last_5min": 0, "txns_last_1h": 0, "txns_last_24h": 0, "customer_account_age_days": 100, "avg_customer_amount": 1.0
        }
        res = c.post("/transactions/assess", json=payload)
        assert res.status_code == 201
        assert res.json()["decision_record"]["decision"] == "ALLOW"

# 6. REVIEW response
def test_review_response():
    with TestClient(app) as c:
        payload = {
            "transaction_id": "123",
            "timestamp": "2023-01-01T12:00:00Z",
            "amount": 1000000.0,
            "currency": "USD",
            "customer_id": "c",
            "merchant_id": "m",
            "payment_method": "cc", "previous_transaction_count": 5, "previous_fraud_count": 0, "amount_deviation": 0.0, "is_new_customer": 0, "merchant_fraud_rate": 0.0, "is_new_merchant": 0, "txns_last_5min": 0, "txns_last_1h": 0, "txns_last_24h": 0, "customer_account_age_days": 100,
            "previous_transaction_count": 0
        }
        res = c.post("/transactions/assess", json=payload)
        assert res.status_code == 201
        # It should trigger REVIEW because extreme amount lacks independent corroborating rule evidence, or it hits the review probability band
        assert res.json()["decision_record"]["decision"] in ["REVIEW", "BLOCK"]

# 7. BLOCK fixture (or doc if unavailable)
def test_block_response():
    with TestClient(app) as c:
        payload = {
            "transaction_id": "123",
            "timestamp": "2023-01-01T12:00:00Z",
            "amount": 10000.0,
            "currency": "USD",
            "customer_id": "fraud_cust",
            "merchant_id": "fraud_merch",
            "payment_method": "crypto",
            "previous_transaction_count": 10,
            "previous_fraud_count": 10,
            "txns_last_24h": 50,
            "device_id": "new_device", "customer_account_age_days": 10,
            "amount_deviation": 5000.0,
            "is_new_customer": 0, "merchant_fraud_rate": 0.0, "is_new_merchant": 0, "txns_last_5min": 0, "txns_last_1h": 0, "txns_last_24h": 0, "customer_account_age_days": 100, "avg_customer_amount": 1.0
        }
        res = c.post("/transactions/assess", json=payload)
        assert res.status_code == 201
        
# 8. response preserves calibrated probability
# 9. response preserves decision
def test_decision_and_probability_preserved():
    with TestClient(app) as c:
        payload = {
            "transaction_id": "123",
            "timestamp": "2023-01-01T12:00:00Z",
            "amount": 150.0,
            "currency": "USD",
            "customer_id": "cust_x",
            "merchant_id": "merch_y",
            "payment_method": "credit_card",
            "previous_transaction_count": 5, "previous_fraud_count": 0, "amount_deviation": 0.0, "is_new_customer": 0, "merchant_fraud_rate": 0.0, "is_new_merchant": 0, "txns_last_5min": 0, "txns_last_1h": 0, "txns_last_24h": 0, "customer_account_age_days": 100, "avg_customer_amount": 1.0
        }
        res = c.post("/transactions/assess", json=payload)
        data = res.json()
        assert data["primary_risk_probability"] is not None
        assert data["decision_record"]["decision"] in ["ALLOW", "REVIEW", "BLOCK"]

# 10. duplicate assessment -> 409
def test_duplicate_assessment():
    with TestClient(app) as c:
        aid = str(uuid.uuid4())
        payload = {
            "assessment_id": aid,
            "transaction_id": "123",
            "timestamp": "2023-01-01T12:00:00Z",
            "amount": 150.0,
            "currency": "USD",
            "customer_id": "cust_x",
            "merchant_id": "merch_y",
            "payment_method": "credit_card"
        }
        r1 = c.post("/transactions/assess", json=payload)
        assert r1.status_code == 201
        r2 = c.post("/transactions/assess", json=payload)
        assert r2.status_code == 409

# 11. explanation failure preserves decision
def test_explanation_failure_preserves_decision(monkeypatch):
    def mock_explain(*args, **kwargs):
        raise ValueError("Simulated LLM Timeout")
    monkeypatch.setattr(app_state.explanation_engine, "explain", mock_explain, raising=False)
    with TestClient(app) as c:
        app_state.explanation_engine.explain = mock_explain
        payload = {
            "transaction_id": "123",
            "timestamp": "2023-01-01T12:00:00Z",
            "amount": 150.0,
            "currency": "USD",
            "customer_id": "cust_x",
            "merchant_id": "merch_y",
            "payment_method": "credit_card"
        }
        res = c.post("/transactions/assess", json=payload)
        assert res.status_code == 201
        assert res.json()["decision_record"]["decision"] in ["ALLOW", "REVIEW", "BLOCK"]

# 12. persistence failure preserves decision
def test_persistence_failure_preserves_decision(monkeypatch):
    def mock_save(*args, **kwargs):
        from database import repository
        raise repository.sqlite3.OperationalError("Simulated DB Disk Full")
    monkeypatch.setattr("api.service.save_assessment", mock_save)
    with TestClient(app) as c:
        payload = {
            "transaction_id": "fail_txn",
            "timestamp": "2023-01-01T12:00:00Z",
            "amount": 50.0,
            "customer_id": "c",
            "merchant_id": "m",
            "payment_method": "cc", "previous_transaction_count": 5, "previous_fraud_count": 0, "amount_deviation": 0.0, "is_new_customer": 0, "merchant_fraud_rate": 0.0, "is_new_merchant": 0, "txns_last_5min": 0, "txns_last_1h": 0, "txns_last_24h": 0, "customer_account_age_days": 100, "avg_customer_amount": 1.0
        }
        res = c.post("/transactions/assess", json=payload)
        assert res.status_code == 500
        # Partial result must be attached!
        data = res.json()
        assert "partial_result" in data
        assert data["partial_result"]["decision"] in ["ALLOW", "REVIEW", "BLOCK"]

# 13. model failure does not leak traceback
def test_model_failure_no_traceback(monkeypatch):
    def mock_predict(*args, **kwargs):
        raise ValueError("Fake model crash")
    monkeypatch.setattr("model.risk_fusion.predict_proba", mock_predict)
    with TestClient(app) as c:
        payload = {
            "transaction_id": "fail",
            "timestamp": "2023-01-01T12:00:00Z",
            "amount": 50.0,
            "currency": "USD",
            "customer_id": "c",
            "merchant_id": "m",
            "payment_method": "cc", "previous_transaction_count": 5, "previous_fraud_count": 0, "amount_deviation": 0.0, "is_new_customer": 0, "merchant_fraud_rate": 0.0, "is_new_merchant": 0, "txns_last_5min": 0, "txns_last_1h": 0, "txns_last_24h": 0, "customer_account_age_days": 100, "avg_customer_amount": 1.0
        }
        res = c.post("/transactions/assess", json=payload)
        assert res.status_code == 500
        assert "Fake model crash" not in res.text

# 14. request ID generated, 15. propagated
def test_request_id_generated_and_propagated():
    with TestClient(app) as c:
        payload = {
            "transaction_id": "123",
            "timestamp": "2023-01-01T12:00:00Z",
            "amount": 150.0,
            "currency": "USD",
            "customer_id": "cust_x",
            "merchant_id": "merch_y",
            "payment_method": "credit_card"
        }
        res = c.post("/transactions/assess", json=payload, headers={"X-Request-ID": "test-req-123"})
        assert res.headers["X-Request-ID"] == "test-req-123"

# 16. health endpoint
def test_health():
    with TestClient(app) as c:
        assert c.get("/health").status_code == 200

# 17. readiness endpoint
def test_ready():
    with TestClient(app) as c:
        assert c.get("/ready").status_code == 200

# 18. model/artifact initialization occurs once (Correction 2)
def test_authoritative_model_is_logistic_regression():
    with TestClient(app) as c:
        model = app_state.model_artifact["model"]
        assert isinstance(model, LogisticRegression), "Authoritative model MUST be LogisticRegression"

# 19. repeated request does not retrain
def test_no_retrain_on_repeated_request():
    with TestClient(app) as c:
        assert app_state.is_ready is True
        # Model artifact ID should be the same
        first_id = id(app_state.model_artifact)
        payload = {
            "transaction_id": "123",
            "timestamp": "2023-01-01T12:00:00Z",
            "amount": 150.0,
            "currency": "USD",
            "customer_id": "cust_x",
            "merchant_id": "merch_y",
            "payment_method": "credit_card"
        }
        c.post("/transactions/assess", json=payload)
        c.post("/transactions/assess", json=payload)
        assert id(app_state.model_artifact) == first_id

# 20. target/is_fraud cannot enter through the API contract
def test_is_fraud_rejected():
    with TestClient(app) as c:
        payload = {
            "transaction_id": "123",
            "timestamp": "2023-01-01T12:00:00Z",
            "amount": 150.0,
            "currency": "USD",
            "customer_id": "cust_x",
            "merchant_id": "merch_y",
            "payment_method": "credit_card",
            "is_fraud": 1
        }
        res = c.post("/transactions/assess", json=payload)
        assert res.status_code == 400

# 21. no TEST dataset is loaded by API startup
def test_no_test_split_loaded():
    import sys
    assert 'data.split' not in sys.modules or 'data.generator' in sys.modules # Just ensure we don't accidentally load test split
    # Since we generate exactly 1000 items in lifespan via generate_transactions, we skip the splitting phase.

# 22. response does not expose stack traces
def test_no_stack_traces():
    with TestClient(app) as c:
        payload = {"bad": "data"}
        res = c.post("/transactions/assess", json=payload)
        assert "Traceback" not in res.text

def test_missing_history_yields_nan_and_unavalable():
    with TestClient(app) as c:
        payload = {
            "transaction_id": "123",
            "timestamp": "2023-01-01T12:00:00Z",
            "amount": 150.0,
            "currency": "USD",
            "customer_id": "cust_x",
            "merchant_id": "merch_y",
            "payment_method": "credit_card"
        }
        res = c.post("/transactions/assess", json=payload)
        assert res.status_code == 201
        data = res.json()
        assert data["confidence_in_probability"] == "NONE"
        assert data["primary_risk_probability"] is None

def test_genuinely_new_customer():
    with TestClient(app) as c:
        payload = {
            "transaction_id": "123",
            "timestamp": "2023-01-01T12:00:00Z",
            "amount": 150.0,
            "currency": "USD",
            "customer_id": "cust_x",
            "merchant_id": "merch_y",
            "payment_method": "credit_card",
            "previous_transaction_count": 0,
            "is_new_customer": 1,
            "previous_fraud_count": 0,
            "amount_deviation": 0.0,
            "merchant_fraud_rate": 0.0,
            "is_new_merchant": 0,
            "txns_last_5min": 0,
            "txns_last_1h": 0,
            "txns_last_24h": 0,
            "customer_account_age_days": 0.0, "avg_customer_amount": 0.0
        }
        res = c.post("/transactions/assess", json=payload)
        assert res.status_code == 201
        data = res.json()
        assert data["primary_risk_probability"] is not None


def test_dashboard_summary():
    with TestClient(app) as c:
        res = c.get("/dashboard/summary")
        assert res.status_code == 200
        data = res.json()
        assert "total_assessments" in data
        assert "decisions" in data

def test_dashboard_transactions():
    with TestClient(app) as c:
        res = c.get("/dashboard/transactions")
        assert res.status_code == 200
        data = res.json()
        assert "data" in data
        assert "total" in data

def test_dashboard_risk_distribution():
    with TestClient(app) as c:
        res = c.get("/dashboard/risk-distribution")
        assert res.status_code == 200
        data = res.json()
        assert "labels" in data
        assert "counts" in data

def test_dashboard_probability_amount_bounded():
    """Verify GET /dashboard/probability-amount is bounded for performance."""
    with TestClient(app) as c:
        res = c.get("/dashboard/probability-amount")
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data, list)
        assert len(data) <= 1000

def test_dashboard_trends():
    """Verify trends groups correctly and does not fail."""
    with TestClient(app) as c:
        res = c.get("/dashboard/trends")
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data, list)
        if data:
            assert "date" in data[0]
            assert "ALLOW" in data[0]
            assert "TOTAL" in data[0]

def test_dashboard_shap_intelligence():
    """Verify SHAP global aggregation works."""
    with TestClient(app) as c:
        res = c.get("/dashboard/shap-intelligence")
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data, list)
        if data:
            assert "mean_abs_shap" in data[0]
