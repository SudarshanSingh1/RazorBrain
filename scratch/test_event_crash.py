import pytest
import asyncio
from unittest.mock import patch, MagicMock
from api.events import EventProcessor, TransactionEvent
from api.service import assess_transaction
from database.connection import get_session

@pytest.mark.asyncio
async def test_crash_after_db_before_publish():
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
    # First consume yields event, next consume blocks forever (we'll cancel it)
    async def mock_consume():
        if getattr(mock_consume, 'called', False):
            await asyncio.sleep(999)
            return None
        mock_consume.called = True
        return {"topic": "transaction.received", "data": event_dict}
        
    consumer.consume = mock_consume
    publisher = MagicMock()
    
    # We want publisher.publish to raise an Exception or crash
    async def crash_publish(*args, **kwargs):
        raise SystemExit("Simulated Crash")
    publisher.publish = crash_publish
    
    # Needs valid state
    from api.lifespan import RazorBrainState
    import sqlite3
    from database.migrations import run_migrations
    import tempfile
    
    with tempfile.NamedTemporaryFile() as tmp:
        run_migrations(tmp.name)
        state = RazorBrainState(db_path=tmp.name, model_dir="", explanation_provider=None, rule_engine=None, is_ready=True)
        # Mock assess_transaction to just return a dummy
        with patch('api.events.assess_transaction', return_value={"assessment_id": "A-CRASH-1"}):
            processor = EventProcessor(consumer, publisher, state)
            
            with pytest.raises(SystemExit):
                await processor.start()
                
            # Check state
            with get_session(state.db_path) as conn:
                c = conn.cursor()
                c.execute("SELECT status FROM processed_events WHERE event_id = ?", ("TEST-CRASH-1",))
                row = c.fetchone()
                # Status should be PERSISTED because the crash occurred during publisher.publish()
                assert row is not None
                assert row["status"] == "PERSISTED"

