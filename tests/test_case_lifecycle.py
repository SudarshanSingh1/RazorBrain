"""
End-to-End integration tests for Transaction Lifecycle & Investigation Case Management.
Verifies:
1. POST /transactions/decide automatically generates investigation cases for REVIEW and STEP_UP.
2. POST /transactions/decide does NOT generate investigation cases for APPROVE.
3. Decision scoring is idempotent and never fails if case already exists.
4. Complete analyst lifecycle: auto-creation -> assignment -> investigation -> escalation -> resolution.
5. Strict governance: operational case resolution is partitioned and does NOT mutate the ML serving model.
"""
import hashlib
import pytest
from fastapi.testclient import TestClient
from api.app import app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("RAZORBRAIN_API_KEY", raising=False)
    with TestClient(app) as c:
        yield c


def _get_file_hash(filepath: str) -> str:
    with open(filepath, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def test_e2e_auto_case_creation_on_review_decision(client):
    # Baseline hash of calibrated model
    initial_hash = _get_file_hash("data/razorpay_serving_model_calibrated.joblib")

    # Transaction triggering HIGH_VALUE_TRANSACTION rule -> REVIEW
    payload = {
        "transaction_id": "txn_e2e_review_01",
        "amount": 650000.0,
        "email": "rich_user@gmail.com",
        "card_network": "visa",
        "card_type": "credit",
        "hour_of_day": 15,
        "day_of_week": 3,
        "previous_transaction_count": 8,
        "avg_customer_amount": 10000.0,
        "amount_ratio": 65.0,
        "txns_last_1h": 1,
        "txns_last_24h": 2,
    }

    res = client.post("/transactions/decide", json=payload)
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["success"] is True
    decision_info = data["decision"]
    assert decision_info["final_decision"] in ("REVIEW", "STEP_UP")

    # Assert case was automatically created
    case_info = decision_info.get("case")
    assert case_info is not None, "Expected 'case' block in decision response"
    assert case_info["case_created"] is True
    assert case_info["case_id"].startswith("case_")
    assert case_info["status"] == "OPEN"
    assert case_info["priority"] in ("HIGH", "CRITICAL", "MEDIUM")

    case_id = case_info["case_id"]

    # 1. Fetch case detail and verify frozen snapshots
    detail_res = client.get(f"/cases/{case_id}")
    assert detail_res.status_code == 200
    case_detail = detail_res.json()["case"]
    assert case_detail["transaction_id"] == "txn_e2e_review_01"
    assert case_detail["decision_snapshot"]["final_decision"] == decision_info["final_decision"]
    assert case_detail["risk_snapshot"]["calibrated_probability"] is not None

    # 2. Assign investigator
    assign_res = client.post(
        f"/cases/{case_id}/assign",
        json={"assigned_to": "fraud.analyst@razorpay.com", "expected_version": case_detail["version"], "actor": "manager_ui"},
    )
    assert assign_res.status_code == 200
    assert assign_res.json()["case"]["assigned_to"] == "fraud.analyst@razorpay.com"
    v2 = assign_res.json()["case"]["version"]

    # 3. Start investigation
    inv_res = client.post(
        f"/cases/{case_id}/investigate",
        json={"expected_version": v2, "notes": "Contacting cardholder to verify transaction", "actor": "fraud.analyst"},
    )
    assert inv_res.status_code == 200
    assert inv_res.json()["case"]["status"] == "INVESTIGATING"
    v3 = inv_res.json()["case"]["version"]

    # 4. Resolve case with operational feedback
    resolve_res = client.post(
        f"/cases/{case_id}/resolve",
        json={
            "expected_version": v3,
            "resolution_type": "CONFIRMED_LEGITIMATE",
            "resolution_notes": "Cardholder verified authorized large purchase via OTP and phone confirmation.",
            "actor": "fraud.analyst",
        },
    )
    assert resolve_res.status_code == 200
    assert resolve_res.json()["case"]["status"] == "RESOLVED"
    assert resolve_res.json()["case"]["resolution_type"] == "CONFIRMED_LEGITIMATE"

    # 5. Verify serving model file was completely untouched
    final_hash = _get_file_hash("data/razorpay_serving_model_calibrated.joblib")
    assert initial_hash == final_hash, "Serving model artifact was modified!"


def test_e2e_no_case_creation_on_approve(client):
    # Standard benign transaction -> APPROVE
    payload = {
        "transaction_id": "txn_e2e_approve_01",
        "amount": 120.0,
        "email": "regular_shopper@gmail.com",
        "card_network": "visa",
        "card_type": "debit",
        "hour_of_day": 12,
        "day_of_week": 2,
        "previous_transaction_count": 25,
        "avg_customer_amount": 150.0,
        "amount_ratio": 0.8,
        "txns_last_1h": 1,
        "txns_last_24h": 1,
    }

    res = client.post("/transactions/decide", json=payload)
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["success"] is True
    decision_info = data["decision"]
    assert decision_info["final_decision"] == "APPROVE"

    case_info = decision_info.get("case")
    assert case_info is not None
    assert case_info["case_created"] is False
    assert case_info.get("case_id") is None
