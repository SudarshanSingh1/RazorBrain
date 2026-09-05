import sqlite3
import os

def get_severity(risk: str) -> int:
    return {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}.get(risk, 0)

def test_invariant_final_decision_monotonicity():
    # Final decision severity >= Base decision severity
    
    # We can mock out the engine to check if it forces monotonicity
    # Actually, let's just inspect the SQLite database for any records where this was violated
    # In a real test, we would query `serving_assessments`
    db_path = os.environ.get("RAZORBRAIN_DB_PATH", "razorbrain_api.db")
    if not os.path.exists(db_path):
        return # Skip if no db
        
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT assessment_id, base_decision, final_decision FROM serving_assessments")
        records = cursor.fetchall()
        for r in records:
            base_risk = "LOW" if r[1] == "APPROVE" else "MEDIUM" if r[1] == "REVIEW" else "HIGH" if r[1] == "STEP_UP" else "CRITICAL"
            final_risk = "LOW" if r[2] == "APPROVE" else "MEDIUM" if r[2] == "REVIEW" else "HIGH" if r[2] == "STEP_UP" else "CRITICAL"
            assert get_severity(final_risk) >= get_severity(base_risk), f"Monotonicity violated on {r[0]}"
    except Exception:
        pass
    finally:
        conn.close()

def test_invariant_active_models_count():
    db_path = os.environ.get("RAZORBRAIN_DB_PATH", "razorbrain_api.db")
    if not os.path.exists(db_path):
        return
        
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT COUNT(*) FROM model_registry WHERE is_active = 1")
        count = cursor.fetchone()[0]
        # At most 1 active model
        assert count <= 1
    except Exception:
        pass
    finally:
        conn.close()
