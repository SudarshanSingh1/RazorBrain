import pytest
import sqlite3
import asyncio
from unittest.mock import patch, MagicMock

from database.repository import reserve_event, update_event_status, DuplicateEventError, save_assessment, DuplicateAssessmentError
from api.events import EventProcessor, TransactionEvent, AssessmentResultEvent

def test_event_idempotency_vs_assessment_uniqueness():
    conn = sqlite3.connect(":memory:")
    conn.execute('''CREATE TABLE processed_events (event_id TEXT UNIQUE, status TEXT, correlation_id TEXT, assessment_id TEXT, created_at TEXT, updated_at TEXT)''')
    conn.execute('''CREATE TABLE transactions (transaction_id TEXT, timestamp TEXT, amount REAL, customer_id TEXT, merchant_id TEXT, context_data TEXT)''')
    conn.execute('''CREATE TABLE risk_assessments (assessment_id TEXT UNIQUE, transaction_id TEXT, timestamp TEXT, primary_risk_probability REAL, confidence_in_probability TEXT, model_metadata TEXT)''')
    conn.execute('''CREATE TABLE decisions (assessment_id TEXT, decision TEXT, decision_reason TEXT, blocking_guardrail_status TEXT, policy_metadata TEXT)''')
    conn.commit()

    reserve_event(conn, "EV-1", "C-1")
    with pytest.raises(DuplicateEventError):
        reserve_event(conn, "EV-1", "C-2")

    save_assessment(conn, {}, {"assessment_id": "A-1", "decision": "ALLOW", "transaction_id": "TX-1"})
    
    reserve_event(conn, "EV-2", "C-3")
    with pytest.raises(DuplicateAssessmentError):
        save_assessment(conn, {}, {"assessment_id": "A-1", "decision": "BLOCK", "transaction_id": "TX-2"})
        
    update_event_status(conn, "EV-2", "DUPLICATE_ASSESSMENT")
    
    c = conn.cursor()
    c.execute("SELECT status FROM processed_events WHERE event_id = 'EV-2'")
    assert c.fetchone()[0] == "DUPLICATE_ASSESSMENT"

def test_publication_failure_leaves_persisted():
    asyncio.run(_test_publication_failure_leaves_persisted())

async def _test_publication_failure_leaves_persisted():
    consumer = MagicMock()
    # Provide an event that triggers the flow
    event_dict = {
        "metadata": {"event_id": "TEST-CRASH-1", "correlation_id": "C-1", "event_type": "transaction.received"},
        "payload": {
            "transaction_id": "TX-CRASH-1",
            "timestamp": "2023-01-01T00:00:00Z",
            "amount": 100,
            "currency": "USD",
            "customer_id": "C-1",
            "merchant_id": "M-1",
            "payment_method": "cc"
        }
    }
    
    async def mock_consume():
        if getattr(mock_consume, 'called', False):
            await asyncio.sleep(0.1)
            raise asyncio.CancelledError()
        mock_consume.called = True
        return {"topic": "transaction.received", "data": event_dict}
        
    consumer.consume = mock_consume
    publisher = MagicMock()
    
    async def fail_publish(*args, **kwargs):
        raise ValueError("Simulated Publish Failure")
    publisher.publish = fail_publish
    
    from api.lifespan import AppState
    from database.migrations import run_migrations
    import tempfile
    
    with tempfile.NamedTemporaryFile() as tmp:
        run_migrations(tmp.name)
        state = AppState()
        state.db_path=tmp.name
        state.is_ready=True
        
        with patch('api.service.assess_transaction', return_value={"assessment_id": "A-CRASH-1"}):
            processor = EventProcessor(consumer, publisher, state)
            
            await processor.start()
                
            from database.connection import get_session
            with get_session(state.db_path) as conn:
                c = conn.cursor()
                c.execute("SELECT status FROM processed_events WHERE event_id = ?", ("TEST-CRASH-1",))
                row = c.fetchone()
                assert row is not None
                assert row["status"] == "PUBLICATION_FAILED"
