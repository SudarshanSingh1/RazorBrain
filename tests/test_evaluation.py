import pytest
import uuid
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

def test_record_feedback_fraud_for_block(mock_db):
    test_client, db_path = mock_db
    aid = f"assess_1_{uuid.uuid4()}"
    setup_fake_assessment(db_path, aid, "BLOCK")
    resp = test_client.post(f"/transactions/{aid}/feedback", json={"ground_truth": "FRAUD", "label_source": "MANUAL_REVIEW"})
    assert resp.status_code == 200

def test_record_feedback_legitimate_for_block(mock_db):
    test_client, db_path = mock_db
    aid = f"assess_2_{uuid.uuid4()}"
    setup_fake_assessment(db_path, aid, "BLOCK")
    resp = test_client.post(f"/transactions/{aid}/feedback", json={"ground_truth": "LEGITIMATE", "label_source": "MANUAL_REVIEW"})
    assert resp.status_code == 200

def test_record_feedback_legitimate_for_allow(mock_db):
    test_client, db_path = mock_db
    aid = f"assess_3_{uuid.uuid4()}"
    setup_fake_assessment(db_path, aid, "ALLOW")
    resp = test_client.post(f"/transactions/{aid}/feedback", json={"ground_truth": "LEGITIMATE", "label_source": "MANUAL_REVIEW"})
    assert resp.status_code == 200

def test_record_feedback_fraud_for_allow(mock_db):
    test_client, db_path = mock_db
    aid = f"assess_4_{uuid.uuid4()}"
    setup_fake_assessment(db_path, aid, "ALLOW")
    resp = test_client.post(f"/transactions/{aid}/feedback", json={"ground_truth": "FRAUD", "label_source": "MANUAL_REVIEW"})
    assert resp.status_code == 200

def test_record_feedback_fraud_for_review(mock_db):
    test_client, db_path = mock_db
    aid = f"assess_5_{uuid.uuid4()}"
    setup_fake_assessment(db_path, aid, "REVIEW")
    resp = test_client.post(f"/transactions/{aid}/feedback", json={"ground_truth": "FRAUD", "label_source": "MANUAL_REVIEW"})
    assert resp.status_code == 200

def test_record_feedback_duplicate(mock_db):
    test_client, db_path = mock_db
    aid = f"assess_dup_{uuid.uuid4()}"
    setup_fake_assessment(db_path, aid, "ALLOW")
    test_client.post(f"/transactions/{aid}/feedback", json={"ground_truth": "FRAUD", "label_source": "MANUAL_REVIEW"})
    resp2 = test_client.post(f"/transactions/{aid}/feedback", json={"ground_truth": "LEGITIMATE", "label_source": "MANUAL_REVIEW"})
    assert resp2.status_code == 409

def test_record_feedback_invalid_ground_truth(mock_db):
    test_client, db_path = mock_db
    aid = f"assess_inv_{uuid.uuid4()}"
    setup_fake_assessment(db_path, aid, "ALLOW")
    resp = test_client.post(f"/transactions/{aid}/feedback", json={"ground_truth": "MAYBE", "label_source": "MANUAL_REVIEW"})
    assert resp.status_code == 400

def test_record_feedback_rejects_tp_override(mock_db):
    test_client, db_path = mock_db
    aid = f"assess_override_{uuid.uuid4()}"
    setup_fake_assessment(db_path, aid, "ALLOW")
    resp = test_client.post(f"/transactions/{aid}/feedback", json={"ground_truth": "FRAUD", "label_source": "MANUAL_REVIEW", "evaluation_outcome": "TN"})
    assert resp.status_code == 400

def test_analytics_calculated_correctly(mock_db):
    test_client, db_path = mock_db
    resp = test_client.get("/analytics/evaluation")
    assert resp.status_code == 200
    metrics = resp.json()["metrics"]
    assert "tp" in metrics
    assert "precision" in metrics
