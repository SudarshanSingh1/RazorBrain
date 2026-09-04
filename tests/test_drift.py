import pytest
from fastapi.testclient import TestClient
from api.app import app
from database.connection import get_session
import uuid

@pytest.fixture
def mock_db():
    with TestClient(app) as local_client:
        state = app.state.razor_state
        yield local_client, state.db_path

def test_drift_not_measured(mock_db):
    test_client, db_path = mock_db
    with get_session(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = OFF;")
        conn.cursor().execute("DELETE FROM explanations")
        conn.cursor().execute("DELETE FROM model_evidence")
        conn.cursor().execute("DELETE FROM rule_evidence")
        conn.cursor().execute("DELETE FROM evaluation_feedback")
        conn.cursor().execute("DELETE FROM decisions")
        conn.cursor().execute("DELETE FROM risk_assessments")
        conn.cursor().execute("DELETE FROM processed_events")
        conn.cursor().execute("DELETE FROM transactions")
        conn.commit()
    resp = test_client.get("/dashboard/drift?window_hours=1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "NOT_MEASURED"

def setup_fake_assessments(db_path, count=55):
    with get_session(db_path) as conn:
        c = conn.cursor()
        for i in range(count):
            aid = f"drift_{uuid.uuid4()}"
            # Insert fake transactions
            c.execute("INSERT OR IGNORE INTO transactions (transaction_id, timestamp, amount, customer_id, merchant_id, context_data) VALUES (?, datetime('now', '-30 minutes'), ?, ?, ?, ?)", (f"txn_{aid}", 100.0, "c1", "m1", '{"amount": 100.0}'))
            c.execute("INSERT OR IGNORE INTO risk_assessments (assessment_id, transaction_id, timestamp, primary_risk_probability, confidence_in_probability) VALUES (?, ?, datetime('now', '-30 minutes'), ?, ?)", (aid, f"txn_{aid}", 0.15, "HIGH"))
            c.execute("INSERT OR IGNORE INTO decisions (assessment_id, decision) VALUES (?, ?)", (aid, "ALLOW"))
        conn.commit()

def test_drift_measured_identical(mock_db):
    test_client, db_path = mock_db
    with get_session(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = OFF;")
        conn.cursor().execute("DELETE FROM explanations")
        conn.cursor().execute("DELETE FROM model_evidence")
        conn.cursor().execute("DELETE FROM rule_evidence")
        conn.cursor().execute("DELETE FROM evaluation_feedback")
        conn.cursor().execute("DELETE FROM decisions")
        conn.cursor().execute("DELETE FROM risk_assessments")
        conn.cursor().execute("DELETE FROM processed_events")
        conn.cursor().execute("DELETE FROM transactions")
        conn.commit()
    setup_fake_assessments(db_path, 55)
    resp = test_client.get("/dashboard/drift?window_hours=1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "MEASURED"

def test_drift_psi_math():
    from model.drift_monitor import calculate_psi
    import numpy as np
    ref = np.array([0.5, 0.5])
    curr = np.array([0.5, 0.5])
    assert calculate_psi(ref, curr) < 0.001
    
    curr_shifted = np.array([0.1, 0.9])
    assert calculate_psi(ref, curr_shifted) > 0.5

def test_drift_zero_props():
    from model.drift_monitor import calculate_psi
    import numpy as np
    ref = np.array([0.5, 0.5])
    curr = np.array([0.0, 1.0])
    psi = calculate_psi(ref, curr)
    assert np.isfinite(psi)

