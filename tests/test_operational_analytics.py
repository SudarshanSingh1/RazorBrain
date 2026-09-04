import pytest
import uuid
import time
from fastapi.testclient import TestClient
from api.app import app
from database.connection import get_session

client = TestClient(app)

@pytest.fixture
def mock_db():
    with TestClient(app) as local_client:
        state = app.state.razor_state
        yield local_client, state.db_path

def setup_fake_assessment(db_path, assessment_id, decision="ALLOW"):
    with get_session(db_path) as conn:
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO transactions (transaction_id, timestamp, amount, customer_id, merchant_id, context_data) VALUES (?, ?, ?, ?, ?, ?)", (f"txn_{assessment_id}", "2023-01-01T00:00:00Z", 100.0, "c1", "m1", "{}"))
        c.execute("INSERT OR IGNORE INTO risk_assessments (assessment_id, transaction_id, timestamp, primary_risk_probability) VALUES (?, ?, ?, ?)", (assessment_id, f"txn_{assessment_id}", "2023-01-01T00:00:00Z", 0.0))
        c.execute("INSERT OR IGNORE INTO decisions (assessment_id, decision) VALUES (?, ?)", (assessment_id, decision))
        conn.commit()

def test_no_assessments(mock_db):
    # Depending on previous tests this might have data. Let's just check the structure.
    test_client, db_path = mock_db
    resp = test_client.get("/dashboard/operational-analytics")
    assert resp.status_code == 200
    data = resp.json()
    assert "decision_distribution" in data
    assert "review_workload" in data

def test_review_workload_pending_and_resolved(mock_db):
    test_client, db_path = mock_db
    
    aid1 = f"assess_{uuid.uuid4()}"
    setup_fake_assessment(db_path, aid1, "REVIEW")
    
    aid2 = f"assess_{uuid.uuid4()}"
    setup_fake_assessment(db_path, aid2, "REVIEW")
    
    test_client.post(f"/transactions/{aid2}/feedback", json={"ground_truth": "FRAUD", "label_source": "MANUAL_REVIEW"})
    
    resp = test_client.get("/dashboard/operational-analytics")
    rw = resp.json()["review_workload"]
    
    # Just checking it counts them, we know it's at least >0 for both pending and resolved.
    assert rw["total_review"] >= 2
    assert rw["feedback_recorded"] >= 1
    assert rw["pending"] >= 1

def test_evaluation_unresolved(mock_db):
    test_client, db_path = mock_db
    aid = f"assess_{uuid.uuid4()}"
    setup_fake_assessment(db_path, aid, "REVIEW")
    test_client.post(f"/transactions/{aid}/feedback", json={"ground_truth": "FRAUD", "label_source": "MANUAL_REVIEW"})
    
    resp = test_client.get("/dashboard/operational-analytics")
    ev = resp.json()["evaluation"]
    assert ev["unresolved"] >= 1
    
def test_evaluation_tp(mock_db):
    test_client, db_path = mock_db
    aid = f"assess_{uuid.uuid4()}"
    setup_fake_assessment(db_path, aid, "BLOCK")
    test_client.post(f"/transactions/{aid}/feedback", json={"ground_truth": "FRAUD", "label_source": "MANUAL_REVIEW"})
    
    resp = test_client.get("/dashboard/operational-analytics")
    ev = resp.json()["evaluation"]
    assert ev["tp"] >= 1

