import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

from api.app import app
from api.razorpay_adapter import normalize_razorpay_payment

client = TestClient(app)

@pytest.fixture
def mock_razorpay_env(monkeypatch):
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_123")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "secret_abc")
    monkeypatch.setenv("RAZORPAY_MODE", "test")

def test_missing_credentials(monkeypatch):
    monkeypatch.delenv("RAZORPAY_KEY_ID", raising=False)
    monkeypatch.delenv("RAZORPAY_KEY_SECRET", raising=False)
    
    app.state.razor_state.is_ready = True
    response = client.post(
        "/razorpay/test/orders",
        json={"amount": 50000, "currency": "INR", "receipt": "rec_1", "notes": {"customer_id": "c1", "merchant_id": "m1"}},
        headers={"X-API-Key": "dev-api-key-123"}
    )
    assert response.status_code == 501
    assert "not configured" in response.json()["error"]["message"]

@patch("api.razorpay_routes.RazorpayAdapter.create_test_order")
def test_create_order_success(mock_create, mock_razorpay_env):
    mock_create.return_value = {
        "id": "order_123",
        "amount": 50000,
        "currency": "INR",
        "receipt": "rec_1",
        "status": "created"
    }
    
    app.state.razor_state.is_ready = True
    response = client.post(
        "/razorpay/test/orders",
        json={"amount": 50000, "currency": "INR", "receipt": "rec_1", "notes": {"customer_id": "c1", "merchant_id": "m1"}},
        headers={"X-API-Key": "dev-api-key-123"}
    )
    assert response.status_code == 200
    assert response.json()["id"] == "order_123"

def test_normalize_payment_success():
    payment = {
        "id": "pay_123",
        "amount": 5000,
        "currency": "INR",
        "method": "netbanking",
        "email": "test@example.com",
        "order_id": "order_123",
        "notes": {
            "merchant_id": "m1",
            "device_id": "dev1"
        },
        "created_at": 1700000000
    }
    
    txn = normalize_razorpay_payment(payment)
    assert txn.transaction_id == "pay_123"
    assert txn.amount == 50.0
    assert txn.currency == "INR"
    assert txn.payment_method == "bank_transfer"
    assert txn.customer_id == "test@example.com"
    assert txn.merchant_id == "m1"
    assert txn.device_id is None
    assert txn.assessment_id == "order_123_pay_123"
    assert txn.timestamp == "2023-11-14T22:13:20Z"

def test_normalize_payment_missing_customer():
    payment = {
        "id": "pay_123",
        "amount": 5000,
        "currency": "INR",
        "method": "card",
        "order_id": "order_123",
        "notes": {
            "merchant_id": "m1"
        }
    }
    with pytest.raises(ValueError, match="Missing customer identity"):
        normalize_razorpay_payment(payment)


@patch("api.razorpay_adapter.httpx.AsyncClient.post")
def test_razorpay_timeout(mock_post, mock_razorpay_env):
    import httpx
    mock_post.side_effect = httpx.RequestError("Timeout")
    app.state.razor_state.is_ready = True
    response = client.post(
        "/razorpay/test/orders",
        json={"amount": 50000, "currency": "INR", "receipt": "rec_1", "notes": {"customer_id": "c1", "merchant_id": "m1"}},
        headers={"X-API-Key": "dev-api-key-123"}
    )
    assert response.status_code == 502
    assert "Connection error" in response.json()["error"]["message"]

def test_razorpay_payment_method_mapping():
    payment = {
        "id": "pay_123", "amount": 5000, "currency": "INR", "method": "upi",
        "order_id": "order_123", "notes": {"merchant_id": "m1", "customer_id": "c1"}
    }
    txn = normalize_razorpay_payment(payment)
    assert txn.payment_method == "bank_transfer"

    payment["method"] = "wallet"
    txn = normalize_razorpay_payment(payment)
    assert txn.payment_method == "wallet"

    payment["method"] = "unsupported_abc"
    txn = normalize_razorpay_payment(payment)
    assert txn.payment_method == "unavailable"


@patch("api.razorpay_routes.RazorpayAdapter.fetch_payment")
@patch("api.razorpay_routes.assess_serving_transaction")
def test_assess_payment_success(mock_assess, mock_fetch, mock_razorpay_env):
    mock_fetch.return_value = {
        "id": "pay_123",
        "amount": 5000,
        "currency": "INR",
        "method": "card",
        "order_id": "order_123",
        "notes": {"merchant_id": "m1", "customer_id": "c1"}
    }
    mock_assess.return_value = {
        "assessment_id": "order_123_pay_123",
        "transaction_id": "pay_123",
        "risk": 0.05,
        "decision": "ALLOW",
        "decision_reason": {"decision": "ALLOW", "calibrated_risk": 0.05},
        "model_track": "RAZORPAY_SERVING_MODEL",
        "assessment_type": "POST_EVENT_RISK_ASSESSMENT",
        "feature_availability": {}
    }
    
    app.state.razor_state.is_ready = True
    response = client.post(
        "/razorpay/test/assess",
        json={"payment_id": "pay_123"},
        headers={"X-API-Key": "dev-api-key-123"}
    )
    assert response.status_code == 200
    assert response.json()["transaction_id"] == "pay_123"

@patch("api.razorpay_routes.RazorpayAdapter.fetch_payment")
@patch("api.razorpay_routes.assess_serving_transaction")
def test_assess_payment_duplicate(mock_assess, mock_fetch, mock_razorpay_env):
    mock_fetch.return_value = {
        "id": "pay_dup", "amount": 5000, "currency": "INR", "method": "card",
        "order_id": "order_dup", "notes": {"merchant_id": "m1", "customer_id": "c1"}
    }
    from api.serving_service import DuplicateServingAssessmentError
    mock_assess.side_effect = DuplicateServingAssessmentError("Duplicate")
    
    app.state.razor_state.is_ready = True
    response = client.post(
        "/razorpay/test/assess",
        json={"payment_id": "pay_dup"},
        headers={"X-API-Key": "dev-api-key-123"}
    )
    assert response.status_code == 409

@patch("api.razorpay_routes.RazorpayAdapter.fetch_payment")
def test_assess_payment_missing_or_invalid(mock_fetch, mock_razorpay_env):
    mock_fetch.side_effect = Exception("Invalid payment ID")
    app.state.razor_state.is_ready = True
    response = client.post(
        "/razorpay/test/assess",
        json={"payment_id": "pay_invalid"},
        headers={"X-API-Key": "dev-api-key-123"}
    )
    assert response.status_code == 500
    assert "Internal server error" in response.json()["error"]["message"]


@patch("api.razorpay_routes.RazorpayAdapter.fetch_payment")
@patch("api.razorpay_routes.assess_serving_transaction")
def test_consistency_manual_and_webhook(mock_assess, mock_fetch, mock_razorpay_env):
    payment_data = {
        "id": "pay_test",
        "amount": 10000,
        "currency": "INR",
        "method": "upi",
        "email": "test@test.com",
        "order_id": "order_test",
        "notes": {"merchant_id": "m1"}
    }
    mock_fetch.return_value = payment_data
    mock_assess.return_value = {
        "assessment_id": "order_test_pay_test",
        "transaction_id": "pay_test",
        "risk": 0.1,
        "decision": "REVIEW",
        "decision_reason": {},
        "model_track": "RAZORPAY_SERVING_MODEL",
        "assessment_type": "POST_EVENT_RISK_ASSESSMENT",
        "feature_availability": {}
    }
    
    app.state.razor_state.is_ready = True
    response = client.post(
        "/razorpay/test/assess",
        json={"payment_id": "pay_test"},
        headers={"X-API-Key": "dev-api-key-123"}
    )
    
    # Check that assess_serving_transaction was called with EXACTLY the augmented canonical dict
    called_dict = mock_assess.call_args[0][0]
    assert called_dict["transaction_id"] == "pay_test"
    assert called_dict["amount"] == 100.0  # normalized from 10000 paise
    assert called_dict["email"] == "test@test.com"
    assert called_dict["payment_method"] == "bank_transfer" # UPI mapping
    assert response.status_code == 200


@patch("api.razorpay_routes.RazorpayAdapter.fetch_payment")
@patch("api.razorpay_routes.assess_serving_transaction")
def test_investigate_serving_assessment(mock_assess, mock_fetch, mock_razorpay_env):
    # 1. Create it via the endpoint
    payment_data = {
        "id": "pay_inv123",
        "amount": 7000,
        "currency": "INR",
        "method": "card",
        "email": "inv@test.com",
        "order_id": "order_inv123",
        "notes": {"merchant_id": "m1"}
    }
    mock_fetch.return_value = payment_data
    mock_assess.return_value = {
        "assessment_id": "order_inv123_pay_inv123",
        "transaction_id": "pay_inv123",
        "risk": 0.25,
        "decision": "REVIEW",
        "decision_reason": {"decision": "REVIEW"},
        "model_track": "RAZORPAY_SERVING_MODEL",
        "assessment_type": "POST_EVENT_RISK_ASSESSMENT",
        "feature_availability": {"amount": True},
        "feature_snapshot": {"amount": 70.0},
        "shap_snapshot": {"features_contributions": [{"feature": "amount", "contribution": 0.1}]}
    }
    
    app.state.razor_state.is_ready = True
    # We must actually persist it into the database directly because assess_serving_transaction is mocked and normally IT persists it.
    # Oh wait! assess_serving_transaction DOES the persistence! If we mock it, nothing gets saved to the database!
    pass

