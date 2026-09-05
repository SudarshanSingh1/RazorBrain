"""
Tests for Phase 12 Database + Audit Trail.
Ensures relational schema integrity, idempotency, round-trip retrieval,
and independence from ML recalculations.
"""

import pytest
import os
import sqlite3
from database.connection import get_session
from database.migrations import run_migrations
from database.repository import save_assessment, get_assessment, DuplicateAssessmentError

@pytest.fixture
def test_db():
    db_path = "test_razorbrain.db"
    if os.path.exists(db_path):
        os.remove(db_path)
        
    # Run migrations
    run_migrations(db_path=db_path)
    
    yield db_path
    
    if os.path.exists(db_path):
        os.remove(db_path)

@pytest.fixture
def sample_data():
    txn_data = {
        "transaction_id": "txn_test_1",
        "timestamp": "2023-01-01T12:00:00Z",
        "amount": 100.5,
        "customer_id": "cust_1",
        "merchant_id": "merch_1"
    }
    dec_result = {
        "assessment_id": "assess_1",
        "transaction_id": "txn_test_1",
        "primary_risk_probability": 0.05,
        "confidence_in_probability": "HIGH",
        "decision": "ALLOW",
        "decision_reason": "Low risk.",
        "blocking_guardrail_status": "NOT_EVALUATED",
        "policy_metadata": {"allow": 0.1, "block": 0.4},
        "evidence_summary": {
            "rule_evidence": {
                "triggered_rules": [
                    {"rule_id": "velocity_new_device", "severity": "HIGH"}
                ]
            },
            "model_evidence": {
                "top_positive_contributors": [
                    {"feature": "f1", "shap_contribution": 0.4}
                ]
            }
        }
    }
    exp_result = {
        "transaction_id": "txn_test_1",
        "decision": "ALLOW",
        "explanation": "Decision: ALLOW.",
        "provider": "deterministic_fallback",
        "grounded": True,
        "limitations": []
    }
    return txn_data, dec_result, exp_result

def test_database_initialization_and_migrations(test_db):
    with get_session(test_db) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
        
    assert "transactions" in tables
    assert "risk_assessments" in tables
    assert "decisions" in tables
    assert "rule_evidence" in tables
    assert "model_evidence" in tables
    assert "explanations" in tables

def test_round_trip_integrity(test_db, sample_data):
    txn_data, dec_result, exp_result = sample_data
    
    with get_session(test_db) as conn:
        aid = save_assessment(conn, txn_data, dec_result, exp_result)
        
    with get_session(test_db) as conn:
        retrieved = get_assessment(conn, aid)
        
    assert retrieved is not None
    assert retrieved["assessment_id"] == "assess_1"
    assert retrieved["primary_risk_probability"] == 0.05
    assert retrieved["confidence_in_probability"] == "HIGH"
    
    assert retrieved["decision"] == "ALLOW"
    assert retrieved["decision_reason"] == "Low risk."
    
    assert len(retrieved["rule_evidence"]) == 1
    assert retrieved["rule_evidence"][0]["rule_id"] == "velocity_new_device"
    assert retrieved["rule_evidence"][0]["severity"] == "HIGH"
    
    assert len(retrieved["model_evidence"]) == 1
    assert retrieved["model_evidence"][0]["feature_name"] == "f1"
    assert retrieved["model_evidence"][0]["shap_contribution"] == 0.4
    
    assert retrieved["explanation_record"]["provider"] == "deterministic_fallback"
    assert retrieved["explanation_record"]["grounded"] == 1

def test_idempotency_duplicate_rejection(test_db, sample_data):
    txn_data, dec_result, exp_result = sample_data
    
    with get_session(test_db) as conn:
        save_assessment(conn, txn_data, dec_result, exp_result)
        
    with pytest.raises(DuplicateAssessmentError):
        with get_session(test_db) as conn:
            save_assessment(conn, txn_data, dec_result, exp_result)

def test_foreign_key_integrity(test_db, sample_data):
    txn_data, dec_result, exp_result = sample_data
    
    # Try inserting decision without risk_assessment -> handled by save_assessment correctly,
    # but let's test pure SQL constraints
    with pytest.raises(sqlite3.IntegrityError):
        with get_session(test_db) as conn:
            conn.execute("INSERT INTO decisions (assessment_id, decision) VALUES ('fake', 'ALLOW')")

def test_missing_optional_evidence(test_db, sample_data):
    txn_data, dec_result, exp_result = sample_data
    del dec_result["evidence_summary"]
    dec_result["assessment_id"] = "assess_2"
    
    with get_session(test_db) as conn:
        aid = save_assessment(conn, txn_data, dec_result, None)
        retrieved = get_assessment(conn, aid)
        
    assert retrieved["assessment_id"] == "assess_2"
    assert len(retrieved["rule_evidence"]) == 0
    assert len(retrieved["model_evidence"]) == 0
    assert "explanation_record" not in retrieved

def test_transaction_rollback_on_failure(test_db, sample_data):
    txn_data, dec_result, exp_result = sample_data
    dec_result["assessment_id"] = "assess_error"
    
    try:
        with get_session(test_db) as conn:
            save_assessment(conn, txn_data, dec_result, exp_result)
            # Force an error
            raise ValueError("Simulated failure")
    except ValueError:
        pass
        
    # Transaction should be rolled back
    with get_session(test_db) as conn:
        retrieved = get_assessment(conn, "assess_error")
        assert retrieved is None

def test_repeated_fraud_preservation(test_db, sample_data):
    txn_data, dec_result, exp_result = sample_data
    dec_result["assessment_id"] = "assess_rf"
    dec_result["evidence_summary"]["rule_evidence"]["triggered_rules"] = [
        {"rule_id": "repeated_fraud", "severity": "HIGH"}
    ]
    
    with get_session(test_db) as conn:
        aid = save_assessment(conn, txn_data, dec_result, exp_result)
        retrieved = get_assessment(conn, aid)
        
    rules = retrieved["rule_evidence"]
    assert len(rules) == 1
    assert rules[0]["rule_id"] == "repeated_fraud"
    assert rules[0]["severity"] == "HIGH" # Stored categorically

def test_repeated_migrations(test_db):
    # Running migrations again should be a no-op and not raise errors
    run_migrations(db_path=test_db)
    
    with get_session(test_db) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM migrations")
        count = cursor.fetchone()[0]
        assert count > 0

def test_paginated_retrieval(test_db, sample_data):
    txn_data, dec_result, exp_result = sample_data
    
    with get_session(test_db) as conn:
        for i in range(5):
            txn = txn_data.copy()
            txn["transaction_id"] = f"txn_page_{i}"
            dec = dec_result.copy()
            dec["assessment_id"] = f"assess_page_{i}"
            dec["transaction_id"] = f"txn_page_{i}"
            save_assessment(conn, txn, dec, exp_result)
            
    with get_session(test_db) as conn:
        # Fetch page 1 (size 2)
        from database.repository import get_assessments_paginated
        page1 = get_assessments_paginated(conn, limit=2, offset=0)
        assert len(page1) == 2
        
        # Fetch page 2 (size 2)
        page2 = get_assessments_paginated(conn, limit=2, offset=2)
        assert len(page2) == 2
        assert page1[0]["assessment_id"] != page2[0]["assessment_id"]
        
        # Fetch boundary page (size 2, but only 1 left)
        page3 = get_assessments_paginated(conn, limit=2, offset=4)
        assert len(page3) == 1
        
        # Empty page
        page4 = get_assessments_paginated(conn, limit=2, offset=10)
        assert len(page4) == 0

def test_retrieval_does_not_recompute(test_db, sample_data):
    txn_data, dec_result, exp_result = sample_data
    with get_session(test_db) as conn:
        aid = save_assessment(conn, txn_data, dec_result, exp_result)
        retrieved = get_assessment(conn, aid)
        
    # The retrieved object is a plain dictionary containing strictly the historical strings/floats.
    # No ML objects (like xgb.Booster or shap.Explainer) are attached or executed.
    assert isinstance(retrieved["primary_risk_probability"], float)
    assert isinstance(retrieved["decision"], str)
    assert retrieved["decision"] == dec_result["decision"]
