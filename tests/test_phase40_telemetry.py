import pytest
from fastapi.testclient import TestClient
from api.app import app
import os
from unittest.mock import AsyncMock
from api.razorpay_adapter import RazorpayAdapter
from api.razorpay_routes import get_razorpay_adapter

os.environ["RAZORPAY_KEY_ID"] = "rzp_test_telemetry"
os.environ["RAZORPAY_KEY_SECRET"] = "secret123"

client = TestClient(app)

@pytest.fixture
def mock_adapter():
    mock_instance = AsyncMock(spec=RazorpayAdapter)
    mock_instance.create_test_order.return_value = {
        "id": "order_test_123",
        "amount": 1000,
        "currency": "INR",
        "receipt": "rcpt",
        "status": "created"
    }
    
    app.dependency_overrides[get_razorpay_adapter] = lambda: mock_instance
    yield mock_instance
    app.dependency_overrides = {}

def test_telemetry_valid_session(mock_adapter):
    headers = {
        "X-API-Key": "test-key-1",
        "X-Session-ID": "sess_valid123",
        "X-Forwarded-For": "203.0.113.5"
    }
    payload = {
        "amount": 1000,
        "currency": "INR",
        "receipt": "rcpt",
        "notes": {
            "customer_id": "cust1",
            "merchant_id": "merch1"
        }
    }
    
    response = client.post("/razorpay/test/orders", json=payload, headers=headers)
    assert response.status_code == 200
    
    # Verify the mock adapter received the injected telemetry in notes
    mock_adapter.create_test_order.assert_called_once()
    called_args, called_kwargs = mock_adapter.create_test_order.call_args
    notes = called_kwargs.get("notes", {})
    
    # IP address injected from X-Forwarded-For
    assert notes["ip_address"] == "203.0.113.5"
    # Session ID injected from X-Session-ID header
    assert notes["session_id"] == "sess_valid123"

def test_untrusted_client_fields(mock_adapter):
    # Client tries to spoof ip_address and session_id in the body notes
    headers = {
        "X-API-Key": "test-key-1",
        "X-Session-ID": "real_sess_123"
    }
    payload = {
        "amount": 1000,
        "currency": "INR",
        "receipt": "rcpt",
        "notes": {
            "customer_id": "cust1",
            "merchant_id": "merch1",
            "ip_address": "8.8.8.8",
            "session_id": "fake_sess_456"
        }
    }
    
    response = client.post("/razorpay/test/orders", json=payload, headers=headers)
    assert response.status_code == 200
    
    called_kwargs = mock_adapter.create_test_order.call_args[1]
    notes = called_kwargs.get("notes", {})
    
    # Should be overwritten by server's observed testclient IP (testclient usually passes "testclient")
    assert notes["ip_address"] == "testclient"
    # Should use the header session, not the body note
    assert notes["session_id"] == "real_sess_123"

def test_missing_telemetry(mock_adapter):
    headers = {
        "X-API-Key": "test-key-1"
    }
    payload = {
        "amount": 1000,
        "currency": "INR",
        "receipt": "rcpt",
        "notes": {
            "customer_id": "cust1",
            "merchant_id": "merch1"
        }
    }
    response = client.post("/razorpay/test/orders", json=payload, headers=headers)
    assert response.status_code == 200
    
    notes = mock_adapter.create_test_order.call_args[1].get("notes", {})
    assert "ip_address" in notes
    assert "session_id" not in notes

def test_oversized_session_id(mock_adapter):
    headers = {
        "X-API-Key": "test-key-1",
        "X-Session-ID": "a" * 100 # Oversized
    }
    payload = {
        "amount": 1000,
        "currency": "INR",
        "receipt": "rcpt",
        "notes": {
            "customer_id": "cust1",
            "merchant_id": "merch1"
        }
    }
    response = client.post("/razorpay/test/orders", json=payload, headers=headers)
    assert response.status_code == 200
    
    notes = mock_adapter.create_test_order.call_args[1].get("notes", {})
    assert "session_id" not in notes

def test_normalization_adapter_mapping():
    from api.razorpay_adapter import normalize_razorpay_payment
    rzp_payment = {
        "id": "pay_test123",
        "amount": 5000,
        "currency": "INR",
        "method": "card",
        "notes": {
            "merchant_id": "merch1",
            "customer_id": "cust1",
            "ip_address": "192.168.1.1",
            "session_id": "sess_123"
        }
    }
    txn = normalize_razorpay_payment(rzp_payment)
    assert txn.ip_address == "192.168.1.1"
    assert txn.device_id == "sess_123"

