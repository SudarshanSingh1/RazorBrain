import pytest
import asyncio
import uuid
from fastapi.testclient import TestClient

from api.app import app
from database.connection import get_session

@pytest.fixture(autouse=True)
def run_migrations():
    # Make sure we run migrations (lifespan does this on app startup, but TestClient handles that)
    pass

@pytest.mark.anyio
async def test_same_event_id_delivered_twice():
    """Test Event-Level Idempotency."""
    with TestClient(app): # triggers lifespan
        state = app.state.razor_state
        processor = state.processor
        
        event_dict = {
            "metadata": {
                "event_id": "EXPLICIT-DUP-1",
                "event_type": "transaction.received",
                "correlation_id": "corr-dup"
            },
            "payload": {
                "transaction_id": "IDEMP-9999",
                "timestamp": "2023-10-27T10:00:00Z",
                "amount": 250.0,
                "customer_id": "C-IDEMP-1",
                "merchant_id": "M-IDEMP-1",
                "payment_method": "credit_card"
            }
        }
        
        # First delivery
        await processor._handle_transaction_received(event_dict)
        
        # Second delivery
        await processor._handle_transaction_received(event_dict)
        
        with get_session(state.db_path) as conn:
            c = conn.cursor()
            c.execute("SELECT status FROM processed_events WHERE event_id = ?", ("EXPLICIT-DUP-1",))
            s1 = c.fetchone()[0]
            assert s1 in ("PERSISTED", "PUBLISHED")

def test_different_events_same_assessment_id():
    """Test Assessment-Level Idempotency."""
    with TestClient(app) as client:
        shared_id = f"SHARED-{uuid.uuid4()}"
        txn1 = {
            "transaction_id": f"IDEMP-{uuid.uuid4()}",
            "assessment_id": shared_id,
            "timestamp": "2023-10-27T10:00:00Z",
            "amount": 100.0,
            "customer_id": "C-IDEMP-2",
            "merchant_id": "M-IDEMP-2",
            "payment_method": "credit_card"
        }
        txn2 = {
            "transaction_id": f"IDEMP-{uuid.uuid4()}",
            "assessment_id": shared_id,
            "timestamp": "2023-10-27T10:00:00Z",
            "amount": 500.0,
            "customer_id": "C-IDEMP-2",
            "merchant_id": "M-IDEMP-2",
            "payment_method": "credit_card"
        }
        
        res1 = client.post("/transactions/events", json=txn1)
        res2 = client.post("/transactions/events", json=txn2)
        
        assert res1.status_code == 202
        assert res2.status_code == 202
        
        import time
        time.sleep(1.0) # wait for background processing
        
        # We can check the DB directly to see statuses
        state = app.state.razor_state
        event1_id = res1.json()["event_id"]
        event2_id = res2.json()["event_id"]
        
        with get_session(state.db_path) as conn:
            c = conn.cursor()
            c.execute("SELECT status FROM processed_events WHERE event_id = ?", (event1_id,))
            s1 = c.fetchone()[0]
            
            c.execute("SELECT status FROM processed_events WHERE event_id = ?", (event2_id,))
            s2 = c.fetchone()[0]
            
            assert s1 in ("PERSISTED", "PUBLISHED")
            assert s2 == "DUPLICATE_ASSESSMENT"

@pytest.mark.anyio
async def test_concurrent_duplicate_events():
    """Test concurrent delivery of the exact same event_id to the processor."""
    import uuid
    with TestClient(app):
        state = app.state.razor_state
        processor = state.processor
        evt_id = "CONCURRENT-" + str(uuid.uuid4())
        
        event_dict = {
            "metadata": {
                "event_id": evt_id,
                "event_type": "transaction.received",
                "correlation_id": "corr-1"
            },
            "payload": {
                "transaction_id": "IDEMP-3001",
                "assessment_id": "ASSESS-" + str(uuid.uuid4()),
                "timestamp": "2023-10-27T10:00:00Z",
                "amount": 100.0,
                "customer_id": "C-IDEMP-3",
                "merchant_id": "M-IDEMP-3",
                "payment_method": "credit_card"
            }
        }
        
        # We'll dispatch two concurrently
        task1 = asyncio.create_task(processor._handle_transaction_received(event_dict))
        task2 = asyncio.create_task(processor._handle_transaction_received(event_dict))
        
        await asyncio.gather(task1, task2)
        
        with get_session(state.db_path) as conn:
            c = conn.cursor()
            c.execute("SELECT status FROM processed_events WHERE event_id = ?", (evt_id,))
            row = c.fetchone()
            assert row is not None
            assert row[0] in ("PERSISTED", "PUBLISHED")
