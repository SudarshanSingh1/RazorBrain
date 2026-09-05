import pytest
import uuid
from fastapi.testclient import TestClient
from api.app import app
from database.connection import get_session

@pytest.fixture
def mock_db():
    with TestClient(app) as local_client:
        state = app.state.razor_state
        yield local_client, state.db_path

def setup_fake_assessment(db_path, assessment_id, decision="ALLOW"):
    with get_session(db_path) as conn:
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO transactions (transaction_id, timestamp, amount, customer_id, merchant_id, context_data) VALUES (?, ?, ?, ?, ?, ?)", (f"txn_{assessment_id}", "2030-01-01T00:00:00Z", 100.0, "c1", "m1", "{}"))
        c.execute("INSERT OR IGNORE INTO risk_assessments (assessment_id, transaction_id, timestamp, primary_risk_probability) VALUES (?, ?, ?, ?)", (assessment_id, f"txn_{assessment_id}", "2030-01-01T00:00:00Z", 0.0))
        c.execute("INSERT OR IGNORE INTO decisions (assessment_id, decision) VALUES (?, ?)", (assessment_id, decision))
        conn.commit()

def test_dashboard_transaction_detail_shows_feedback(mock_db):
    test_client, db_path = mock_db
    aid = f"assess_{uuid.uuid4()}"
    setup_fake_assessment(db_path, aid, "REVIEW")
    
    # initially no feedback
    resp = test_client.get(f"/dashboard/transactions/{aid}")
    assert resp.status_code == 200
    assert resp.json().get("ground_truth") is None
    
    # submit feedback
    res = test_client.post(f"/transactions/{aid}/feedback", json={"ground_truth": "FRAUD", "label_source": "MANUAL_REVIEW"})
    assert res.status_code == 200
    
    # fetch again
    resp2 = test_client.get(f"/dashboard/transactions/{aid}")
    assert resp2.status_code == 200
    data = resp2.json()
    assert data["ground_truth"] == "FRAUD"
    assert data["evaluation_outcome"] == "UNRESOLVED"
    assert data["label_source"] == "MANUAL_REVIEW"

def test_dashboard_review_queue_hides_resolved(mock_db):
    test_client, db_path = mock_db
    aid = f"assess_{uuid.uuid4()}"
    setup_fake_assessment(db_path, aid, "REVIEW")
    
    resp = test_client.get("/dashboard/transactions?decision=REVIEW&unresolved_only=true&limit=100")
    assert resp.status_code == 200
    
    initial_count = sum(1 for tx in resp.json()["data"] if tx["assessment_id"] == aid)
    assert initial_count == 1
    
    test_client.post(f"/transactions/{aid}/feedback", json={"ground_truth": "LEGITIMATE", "label_source": "MANUAL_REVIEW"})
    
    resp2 = test_client.get("/dashboard/transactions?decision=REVIEW&unresolved_only=true&limit=100")
    final_count = sum(1 for tx in resp2.json()["data"] if tx["assessment_id"] == aid)
    assert final_count == 0

