import pytest
import hmac
import hashlib
import json
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from api.app import app

client = TestClient(app)

@pytest.fixture
def mock_webhook_env(monkeypatch):
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", "test_webhook_secret")
    monkeypatch.setenv("RAZORPAY_MODE", "test")

def create_signature(body_bytes: bytes, secret: str) -> str:
    return hmac.new(secret.encode('utf-8'), body_bytes, hashlib.sha256).hexdigest()

def test_missing_signature(mock_webhook_env):
    response = client.post("/webhooks/razorpay", data=b"{}")
    assert response.status_code == 401
    assert "Missing signature" in response.json()["error"]["message"]

def test_invalid_signature(mock_webhook_env):
    response = client.post(
        "/webhooks/razorpay", 
        data=b"{}", 
        headers={"x-razorpay-signature": "invalid_sig"}
    )
    assert response.status_code == 401
    assert "Invalid signature" in response.json()["error"]["message"]

def test_unsupported_event(mock_webhook_env):
    payload = {
        "event": "payment.failed",
        "payload": {}
    }
    body = json.dumps(payload).encode('utf-8')
    sig = create_signature(body, "test_webhook_secret")
    
    response = client.post(
        "/webhooks/razorpay", 
        data=body, 
        headers={"x-razorpay-signature": sig}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ignored"

def test_valid_webhook_success(mock_webhook_env):
    payload = {
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_123",
                    "amount": 5000,
                    "currency": "INR",
                    "method": "card",
                    "order_id": "order_123",
                    "notes": {"merchant_id": "m1", "customer_id": "c1"},
                    "created_at": 1700000000
                }
            }
        }
    }
    body = json.dumps(payload).encode('utf-8')
    sig = create_signature(body, "test_webhook_secret")
    
    # We must ensure broker is initialized because we bypass lifespan with TestClient
    app.state.razor_state.is_ready = True
    # We will mock the broker publish to check if it's called
    mock_broker = MagicMock()
    # It's an async method
    from unittest.mock import AsyncMock
    mock_broker.publish = AsyncMock(return_value=True)
    app.state.razor_state.broker = mock_broker
    
    response = client.post(
        "/webhooks/razorpay", 
        data=body, 
        headers={
            "x-razorpay-signature": sig,
            "x-razorpay-event-id": "evt_abc123"
        }
    )
    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
    assert response.json()["event_id"] == "evt_abc123"
    
    # Verify the event published correctly
    mock_broker.publish.assert_called_once()
    topic, published_event = mock_broker.publish.call_args[0]
    assert topic == "transaction.received"
    assert published_event["metadata"]["event_id"] == "evt_abc123"
    assert published_event["payload"]["transaction_id"] == "pay_123"
    
def test_valid_webhook_broker_full(mock_webhook_env):
    payload = {
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_123",
                    "amount": 5000,
                    "currency": "INR",
                    "method": "card",
                    "order_id": "order_123",
                    "notes": {"merchant_id": "m1", "customer_id": "c1"},
                    "created_at": 1700000000
                }
            }
        }
    }
    body = json.dumps(payload).encode('utf-8')
    sig = create_signature(body, "test_webhook_secret")
    
    app.state.razor_state.is_ready = True
    mock_broker = MagicMock()
    from unittest.mock import AsyncMock
    mock_broker.publish = AsyncMock(return_value=False)
    app.state.razor_state.broker = mock_broker
    
    response = client.post(
        "/webhooks/razorpay", 
        data=body, 
        headers={
            "x-razorpay-signature": sig,
            "x-razorpay-event-id": "evt_abc123"
        }
    )
    assert response.status_code == 503
    assert "queue is full" in response.json()["error"]["message"]


def test_valid_webhook_e2e_idempotency(mock_webhook_env):
    payload = {
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_dup_test",
                    "amount": 6000,
                    "currency": "INR",
                    "method": "card",
                    "order_id": "order_dup_test",
                    "notes": {"merchant_id": "m1", "customer_id": "c1"},
                    "created_at": 1700000000
                }
            }
        }
    }
    body = json.dumps(payload).encode('utf-8')
    sig = create_signature(body, "test_webhook_secret")
    
    with TestClient(app) as local_client:
        # First call
        res1 = local_client.post(
            "/webhooks/razorpay", 
            data=body, 
            headers={
                "x-razorpay-signature": sig,
                "x-razorpay-event-id": "evt_duplicate_test"
            }
        )
        assert res1.status_code == 200
        
        # Second call
        res2 = local_client.post(
            "/webhooks/razorpay", 
            data=body, 
            headers={
                "x-razorpay-signature": sig,
                "x-razorpay-event-id": "evt_duplicate_test"
            }
        )
        assert res2.status_code == 200
        
        # Give it a moment to process background tasks
        import time
        time.sleep(1.0)
        
        # Verify in DB
        state = app.state.razor_state
        from database.connection import get_session
        with get_session(state.db_path) as conn:
            c = conn.cursor()
            c.execute("SELECT status FROM processed_events WHERE event_id = ?", ("evt_duplicate_test",))
            # There should only be one row since reserve_event creates one row
            rows = c.fetchall()
            assert len(rows) == 1
            assert rows[0][0] in ("PERSISTED", "PUBLISHED")
            
            # Check the actual assessment
            c.execute("SELECT transaction_id FROM risk_assessments WHERE assessment_id = ?", ("order_dup_test_pay_dup_test",))
            assessments = c.fetchall()
            assert len(assessments) == 1

def test_valid_webhook_different_event_same_payment(mock_webhook_env):
    payload = {
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_dup_payment",
                    "amount": 7000,
                    "currency": "INR",
                    "method": "card",
                    "order_id": "order_dup_payment",
                    "notes": {"merchant_id": "m1", "customer_id": "c1"},
                    "created_at": 1700000000
                }
            }
        }
    }
    body = json.dumps(payload).encode('utf-8')
    sig = create_signature(body, "test_webhook_secret")
    
    with TestClient(app) as local_client:
        # First call with event_1
        res1 = local_client.post(
            "/webhooks/razorpay", 
            data=body, 
            headers={
                "x-razorpay-signature": sig,
                "x-razorpay-event-id": "evt_different_1"
            }
        )
        assert res1.status_code == 200
        
        # Second call with event_2 but SAME PAYMENT payload
        res2 = local_client.post(
            "/webhooks/razorpay", 
            data=body, 
            headers={
                "x-razorpay-signature": sig,
                "x-razorpay-event-id": "evt_different_2"
            }
        )
        assert res2.status_code == 200
        
        import time
        time.sleep(1.0)
        
        # Verify in DB
        state = app.state.razor_state
        from database.connection import get_session
        with get_session(state.db_path) as conn:
            c = conn.cursor()
            
            c.execute("SELECT status FROM processed_events WHERE event_id = ?", ("evt_different_1",))
            assert c.fetchone()[0] in ("PERSISTED", "PUBLISHED")
            
            # The second event is technically valid as an event but it fails assessment uniqueness
            c.execute("SELECT status FROM processed_events WHERE event_id = ?", ("evt_different_2",))
            assert c.fetchone()[0] == "DUPLICATE_ASSESSMENT"
            
            # Only one risk assessment should exist
            c.execute("SELECT transaction_id FROM risk_assessments WHERE assessment_id = ?", ("order_dup_payment_pay_dup_payment",))
            assessments = c.fetchall()
            assert len(assessments) == 1
