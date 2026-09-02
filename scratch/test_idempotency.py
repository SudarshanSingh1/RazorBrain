import pytest
import sqlite3
from database.repository import reserve_event, update_event_status, DuplicateEventError, save_assessment, DuplicateAssessmentError

def test_event_idempotency_vs_assessment_uniqueness():
    conn = sqlite3.connect(":memory:")
    # Create tables for testing
    conn.execute('''CREATE TABLE processed_events (event_id TEXT UNIQUE, status TEXT, correlation_id TEXT, assessment_id TEXT, created_at TEXT, updated_at TEXT)''')
    conn.execute('''CREATE TABLE transactions (transaction_id TEXT, timestamp TEXT, amount REAL, customer_id TEXT, merchant_id TEXT, context_data TEXT)''')
    conn.execute('''CREATE TABLE risk_assessments (assessment_id TEXT UNIQUE, transaction_id TEXT, timestamp TEXT, primary_risk_probability REAL, confidence_in_probability TEXT, model_metadata TEXT)''')
    conn.execute('''CREATE TABLE decisions (assessment_id TEXT, decision TEXT, decision_reason TEXT, blocking_guardrail_status TEXT, policy_metadata TEXT)''')
    conn.commit()

    # 1. Event Idempotency
    reserve_event(conn, "EV-1", "C-1")
    with pytest.raises(DuplicateEventError):
        # Same event_id throws immediately
        reserve_event(conn, "EV-1", "C-2")

    # 2. Assessment Uniqueness
    # First valid assessment saves correctly
    save_assessment(conn, {}, {"assessment_id": "A-1", "decision": "ALLOW", "transaction_id": "TX-1"})
    
    # New event ID comes in...
    reserve_event(conn, "EV-2", "C-3")
    
    with pytest.raises(DuplicateAssessmentError):
        # ...but attempts to save an existing assessment_id
        save_assessment(conn, {}, {"assessment_id": "A-1", "decision": "BLOCK", "transaction_id": "TX-2"})
        
    # The new event is marked DUPLICATE_ASSESSMENT
    update_event_status(conn, "EV-2", "DUPLICATE_ASSESSMENT")
    
    c = conn.cursor()
    c.execute("SELECT status FROM processed_events WHERE event_id = 'EV-2'")
    assert c.fetchone()[0] == "DUPLICATE_ASSESSMENT"

