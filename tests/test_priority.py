import pytest
import uuid
from fastapi.testclient import TestClient
from api.app import app
from database.connection import get_session
from model.review_priority import calculate_review_priority

@pytest.fixture
def mock_db():
    with TestClient(app) as local_client:
        state = app.state.razor_state
        yield local_client, state.db_path

def setup_fake_assessment(db_path, aid, decision, probability=0.15, rules=None):
    if rules is None:
        rules = []
    with get_session(db_path) as conn:
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO transactions (transaction_id, timestamp, amount, customer_id, merchant_id, context_data) VALUES (?, ?, ?, ?, ?, ?)", (f"txn_{aid}", "2030-01-01T00:00:00Z", 100.0, "c1", "m1", "{}"))
        c.execute("INSERT OR IGNORE INTO risk_assessments (assessment_id, transaction_id, timestamp, primary_risk_probability, confidence_in_probability) VALUES (?, ?, ?, ?, ?)", (aid, f"txn_{aid}", "2030-01-01T00:00:00Z", probability, "HIGH"))
        c.execute("INSERT OR IGNORE INTO decisions (assessment_id, decision) VALUES (?, ?)", (aid, decision))
        for r in rules:
            c.execute("INSERT INTO rule_evidence (assessment_id, rule_id, severity) VALUES (?, ?, ?)", (aid, r['rule_id'], r['severity']))
        conn.commit()

def test_priority_logic_allow_block(mock_db):
    test_client, db_path = mock_db
    aid = f"assess_{uuid.uuid4()}"
    setup_fake_assessment(db_path, aid, "ALLOW")
    resp = test_client.get(f"/dashboard/transactions/{aid}")
    assert "review_priority" not in resp.json()

def test_priority_logic_review_deterministic(mock_db):
    test_client, db_path = mock_db
    aid = f"assess_{uuid.uuid4()}"
    # probability >= 0.30 -> CRITICAL
    setup_fake_assessment(db_path, aid, "REVIEW", probability=0.35)
    resp = test_client.get(f"/dashboard/transactions/{aid}")
    assert resp.json()["review_priority"]["tier"] == "CRITICAL"

def test_priority_logic_high_rule(mock_db):
    test_client, db_path = mock_db
    aid = f"assess_{uuid.uuid4()}"
    # probability 0.15, but has CRITICAL rule
    setup_fake_assessment(db_path, aid, "REVIEW", probability=0.15, rules=[{"rule_id": "foo", "severity": "CRITICAL"}])
    resp = test_client.get(f"/dashboard/transactions/{aid}")
    assert resp.json()["review_priority"]["tier"] == "CRITICAL"
    
def test_priority_logic_normal(mock_db):
    test_client, db_path = mock_db
    aid = f"assess_{uuid.uuid4()}"
    setup_fake_assessment(db_path, aid, "REVIEW", probability=0.15, rules=[])
    resp = test_client.get(f"/dashboard/transactions/{aid}")
    assert resp.json()["review_priority"]["tier"] == "NORMAL"

def test_get_transactions_ordering(mock_db):
    test_client, db_path = mock_db
    aid_normal = f"assess_{uuid.uuid4()}"
    setup_fake_assessment(db_path, aid_normal, "REVIEW", probability=0.15)
    
    aid_critical = f"assess_{uuid.uuid4()}"
    setup_fake_assessment(db_path, aid_critical, "REVIEW", probability=0.35)
    
    resp = test_client.get("/dashboard/transactions?decision=REVIEW")
    data = resp.json()["data"]
    
    # Critical should be before Normal
    critical_idx = next(i for i, x in enumerate(data) if x["assessment_id"] == aid_critical)
    normal_idx = next(i for i, x in enumerate(data) if x["assessment_id"] == aid_normal)
    
    assert critical_idx < normal_idx

def test_ground_truth_isolation(mock_db):
    test_client, db_path = mock_db
    aid = f"assess_{uuid.uuid4()}"
    setup_fake_assessment(db_path, aid, "REVIEW", probability=0.15)
    
    test_client.post(f"/transactions/{aid}/feedback", json={"ground_truth": "FRAUD", "label_source": "MANUAL_REVIEW"})
    
    # Priority is deterministic regardless of the FRAUD feedback
    resp = test_client.get(f"/dashboard/transactions/{aid}")
    assert resp.json()["review_priority"]["tier"] == "NORMAL"

def test_priority_model_directly():
    res = calculate_review_priority(0.15, "HIGH", [{"rule_id": "new_device", "severity": "LOW"}])
    assert res["tier"] == "NORMAL"  # single weak signal doesn't dominate

