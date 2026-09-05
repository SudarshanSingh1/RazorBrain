import pytest
from model.decision_engine_v2 import DecisionPolicyV2, DecisionEngineV2

def test_decision_engine_basic_approve():
    policy = DecisionPolicyV2()
    engine = DecisionEngineV2(policy)
    
    # 0.10 < 0.1213 -> APPROVE
    decision, reason, trace = engine.evaluate(0.10, {"amount": 1000, "is_new_customer": 0, "card_network": "visa"})
    assert decision == "APPROVE"
    assert trace[0]["decision"] == "APPROVE"

def test_decision_engine_review():
    policy = DecisionPolicyV2()
    engine = DecisionEngineV2(policy)
    
    # 0.14 is between 0.1213 and 0.1600
    decision, reason, trace = engine.evaluate(0.14, {"amount": 1000, "is_new_customer": 0, "card_network": "visa"})
    assert decision == "REVIEW"

def test_decision_engine_step_up():
    policy = DecisionPolicyV2()
    engine = DecisionEngineV2(policy)
    
    # 0.18 is between 0.1600 and 0.2053
    decision, reason, trace = engine.evaluate(0.18, {"amount": 1000, "is_new_customer": 0, "card_network": "visa"})
    assert decision == "STEP_UP"

def test_decision_engine_decline():
    policy = DecisionPolicyV2()
    engine = DecisionEngineV2(policy)
    
    # 0.25 > 0.2053
    decision, reason, trace = engine.evaluate(0.25, {"amount": 1000, "is_new_customer": 0, "card_network": "visa"})
    assert decision == "DECLINE"

def test_hard_override_force_review():
    policy = DecisionPolicyV2()
    engine = DecisionEngineV2(policy)
    
    # 0.10 would normally be APPROVE, but amount = 600,000 > 500,000 forces REVIEW
    decision, reason, trace = engine.evaluate(0.10, {"amount": 600000, "is_new_customer": 0, "card_network": "visa"})
    assert decision == "REVIEW"
    assert reason == "HIGH_VALUE_TRANSACTION"
    assert trace[1]["applied"] == "YES - Increased severity"

def test_hard_override_force_decline():
    policy = DecisionPolicyV2()
    engine = DecisionEngineV2(policy)
    
    # normally APPROVE, but test card forces DECLINE
    decision, reason, trace = engine.evaluate(0.10, {"amount": 1000, "is_new_customer": 0, "card_network": "TEST"})
    assert decision == "DECLINE"
    assert reason == "TEST_CARD_NOT_ALLOWED"

def test_hard_override_cannot_downgrade():
    policy = DecisionPolicyV2()
    engine = DecisionEngineV2(policy)
    
    # Model returns DECLINE. Override says REVIEW (for high value). It should stay DECLINE.
    decision, reason, trace = engine.evaluate(0.25, {"amount": 600000, "is_new_customer": 0, "card_network": "visa"})
    assert decision == "DECLINE"
    assert "Cannot downgrade severity" in trace[1]["applied"]

def test_invalid_probability_safe_fallback():
    policy = DecisionPolicyV2()
    engine = DecisionEngineV2(policy)
    
    decision, reason, trace = engine.evaluate(float("nan"), {"amount": 1000, "is_new_customer": 0, "card_network": "visa"})
    assert decision == "DECLINE"
    assert reason == "INVALID_PROBABILITY"


from fastapi.testclient import TestClient
from api.app import app
import sqlite3

@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("RAZORBRAIN_API_KEY", raising=False)
    with TestClient(app) as c:
        yield c

def test_api_decide_endpoint_success(client):
    payload = {
        "transaction_id": "txn_decide_test_01",
        "amount": 2500.0,
        "email": "customer@gmail.com",
        "card_network": "visa",
        "card_type": "credit",
        "hour_of_day": 14,
        "day_of_week": 2,
        "previous_transaction_count": 5,
        "avg_customer_amount": 1800.0,
        "txns_last_1h": 1,
        "txns_last_24h": 3,
    }
    res = client.post("/transactions/decide", json=payload)
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["success"] is True
    dec = data["decision"]
    assert dec["transaction_id"] == "txn_decide_test_01"
    assert dec["final_decision"] in ("APPROVE", "REVIEW", "STEP_UP", "DECLINE")
    assert "decision_reason" in dec
    assert isinstance(dec["decision_trace"], list)
    assert len(dec["decision_trace"]) > 0
    assert "approve_max" in dec["thresholds"]
    assert dec["thresholds"]["approve_max"] == 0.1213

def test_api_decide_hard_override_high_value(client):
    payload = {
        "transaction_id": "txn_decide_high_val",
        "amount": 600000.0,
        "card_network": "visa",
        "card_type": "credit"
    }
    res = client.post("/transactions/decide", json=payload)
    assert res.status_code == 200
    data = res.json()
    dec = data["decision"]
    # Even if ML model predicts low probability, amount > 500k forces at least REVIEW
    assert dec["final_decision"] in ("REVIEW", "STEP_UP", "DECLINE")
    # Verify trace mentions HARD_OVERRIDE
    traces = [t for t in dec["decision_trace"] if t.get("stage") == "HARD_OVERRIDE"]
    assert len(traces) > 0

def test_api_decide_hard_override_test_card(client):
    payload = {
        "transaction_id": "txn_decide_test_card",
        "amount": 100.0,
        "card_network": "TEST",
        "card_type": "credit"
    }
    res = client.post("/transactions/decide", json=payload)
    assert res.status_code == 200
    data = res.json()
    dec = data["decision"]
    assert dec["final_decision"] == "DECLINE"
    assert dec["decision_reason"] == "TEST_CARD_NOT_ALLOWED"

def test_api_decide_persists_to_db(client):
    txn_id = "txn_db_persist_verify"
    payload = {
        "transaction_id": txn_id,
        "amount": 1500.0,
        "card_network": "mastercard",
        "card_type": "debit"
    }
    res = client.post("/transactions/decide", json=payload)
    assert res.status_code == 200
    
    # Check DB record
    with sqlite3.connect("razorbrain_api.db") as conn:
        c = conn.cursor()
        c.execute("SELECT decision, decision_reason, decision_trace FROM serving_assessments WHERE transaction_id = ?", (txn_id,))
        row = c.fetchone()
        assert row is not None
        assert row[0] in ("APPROVE", "REVIEW", "STEP_UP", "DECLINE")
        assert row[2] is not None  # decision_trace
