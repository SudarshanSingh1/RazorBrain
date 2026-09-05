"""
Integration tests for the operational hardening layer.
Tests the health endpoints, review queue, feedback loop, metrics, and drift monitoring.
"""

import pytest

pytestmark = pytest.mark.skip(reason="Operations API endpoints replaced by Dashboard API endpoints.")

import os
import sqlite3
from fastapi.testclient import TestClient

import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from api.app import app

# Override the DB path for testing to use in-memory/temp DB
# FastAPI app accesses app.state.razor_state.db_path
# The TestClient starts lifespan, which will run migrations on the db_path.
# We will use the default test DB from razor_state but ensure it's clean.

@pytest.fixture(scope="module")
def client():
    # Use a specific test database
    os.environ["RAZORBRAIN_DB_PATH"] = "test_ops_api.db"
    if os.path.exists("test_ops_api.db"):
        os.remove("test_ops_api.db")
        
    with TestClient(app) as c:
        yield c
        
    # Cleanup
    if os.path.exists("test_ops_api.db"):
        os.remove("test_ops_api.db")
    if "RAZORBRAIN_API_KEY" in os.environ:
        del os.environ["RAZORBRAIN_API_KEY"]


def test_health_liveness(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_health_readiness(client):
    response = client.get("/ready")
    # If the serving model artifacts are present locally, this should be 200
    if response.status_code == 200:
        data = response.json()
        assert data["status"] == "ready"
        assert data["serving_model_ready"] is True
    else:
        # If missing artifacts, it should gracefully fail with 503
        assert response.status_code == 503


def test_overview_metrics_empty(client):
    response = client.get("/ops/overview", headers={"X-API-Key": "test-key"})
    if response.status_code == 401:
        # Override the auth dependency for testing if needed, or assume no auth in test if key is right.
        # Actually, get_api_key uses RAZORBRAIN_API_KEY env var.
        pass
        
    # Let's set the env var for tests
    os.environ["RAZORBRAIN_API_KEY"] = "test-key"
    response = client.get("/ops/overview", headers={"X-API-Key": "test-key"})
    
    assert response.status_code == 200
    data = response.json()
    assert data["total_assessments"] >= 0
    assert "financial_exposure" in data
    assert "definition_note" in data["financial_exposure"]
    assert "ground_truth_metrics" in data


def test_drift_insufficient_data(client):
    response = client.get("/ops/drift", headers={"X-API-Key": "test-key"})
    assert response.status_code == 200
    assert response.json()["status"] == "INSUFFICIENT_DATA"


def test_review_queue_and_feedback(client):
    os.environ["RAZORBRAIN_API_KEY"] = "test-key"
    import uuid
    uid = str(uuid.uuid4())
    
    # 1. Insert a mock serving assessment into the DB manually to test queue
    db_path = app.state.razor_state.db_path
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO transactions (transaction_id, timestamp, amount, customer_id, merchant_id, context_data) "
            "VALUES (?, '2024-01-01T00:00:00Z', 100, 'cust_1', 'merch', '{}')",
            (f"txn_{uid}",)
        )
        conn.execute(
            "INSERT INTO serving_assessments (assessment_id, transaction_id, assessment_type, model_track, timestamp, risk, decision, feature_snapshot, processing_status, created_at, review_status) "
            "VALUES (?, ?, 'POST_EVENT_RISK_ASSESSMENT', 'RAZORPAY_SERVING_MODEL', '2024-01-01T00:00:00Z', 0.15, 'REVIEW', '{\"amount\": 100}', 'COMPLETED', '2024-01-01T00:00:00Z', 'PENDING')",
            (f"asm_{uid}", f"txn_{uid}")
        )
        conn.commit()
        
    # 2. Check Review Queue
    resp = client.get("/ops/review-queue", headers={"X-API-Key": "test-key"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    found = any(x["assessment_id"] == f"asm_{uid}" for x in data["data"])
    assert found is True
    
    # 3. Submit Feedback
    fb_resp = client.post(
        f"/ops/review-queue/asm_{uid}/feedback", 
        json={"ground_truth": "FRAUD", "label_source": "MANUAL_REVIEW"},
        headers={"X-API-Key": "test-key"}
    )
    assert fb_resp.status_code == 200
    
    # 4. Verify Assessment is no longer in queue (review_status = REVIEWED)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT review_status, decision FROM serving_assessments WHERE assessment_id = ?", (f"asm_{uid}",)).fetchone()
        assert row["review_status"] == "REVIEWED"
        assert row["decision"] == "REVIEW"  # Decision must NEVER change automatically
        
    # 5. Check duplicate feedback prevents overwrites
    fb_resp2 = client.post(
        f"/ops/review-queue/asm_{uid}/feedback", 
        json={"ground_truth": "LEGITIMATE", "label_source": "MANUAL_REVIEW"},
        headers={"X-API-Key": "test-key"}
    )
    assert fb_resp2.status_code == 409


def test_model_info_explicitly_labels_metrics(client):
    resp = client.get("/ops/model-info", headers={"X-API-Key": "test-key"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["model_track"] == "RAZORPAY_SERVING_MODEL"
    assert "note" in data
    assert "Validation metrics and held-out test metrics" in data["note"]
