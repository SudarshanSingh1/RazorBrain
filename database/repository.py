import json
import uuid
import datetime
import sqlite3
from typing import Dict, Any, Optional

class DuplicateEventError(Exception):
    pass

def reserve_event(conn: sqlite3.Connection, event_id: str, correlation_id: str) -> None:
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO processed_events (event_id, status, correlation_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (event_id, "PROCESSING", correlation_id, now, now))
        conn.commit()
    except sqlite3.IntegrityError:
        raise DuplicateEventError(f"Event {event_id} has already been processed or is processing.")

def update_event_status(conn: sqlite3.Connection, event_id: str, status: str, assessment_id: Optional[str] = None) -> None:
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE processed_events
        SET status = ?, assessment_id = COALESCE(?, assessment_id), updated_at = ?
        WHERE event_id = ?
    ''', (status, assessment_id, now, event_id))
    conn.commit()

class DuplicateAssessmentError(Exception):
    pass

def save_assessment(
    conn: sqlite3.Connection,
    transaction_data: Dict[str, Any],
    decision_result: Dict[str, Any],
    explanation_result: Optional[Dict[str, Any]] = None
) -> str:
    """
    Persists a risk assessment, decision, rules, model evidence, and explanation.
    Idempotent checks ensure append-only audit semantics without silent overwriting.
    """
    cursor = conn.cursor()
    
    # 1. Identity & Idempotency
    tid = decision_result.get("transaction_id", str(uuid.uuid4()))
    # We require an assessment_id. If missing, generate one.
    aid = decision_result.get("assessment_id")
    if not aid:
        aid = str(uuid.uuid4())
        
    cursor.execute("SELECT 1 FROM risk_assessments WHERE assessment_id = ?", (aid,))
    if cursor.fetchone():
        raise DuplicateAssessmentError(f"Assessment {aid} already exists.")
        
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    
    # 2. Transaction
    cursor.execute("SELECT 1 FROM transactions WHERE transaction_id = ?", (tid,))
    if not cursor.fetchone():
        cursor.execute("""
            INSERT INTO transactions (transaction_id, timestamp, amount, customer_id, merchant_id, context_data)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            tid,
            transaction_data.get("timestamp", now),
            transaction_data.get("amount"),
            transaction_data.get("customer_id"),
            transaction_data.get("merchant_id"),
            json.dumps(transaction_data)
        ))
        
    # 3. Risk Assessment
    summary = decision_result.get("evidence_summary", {})
    cursor.execute("""
        INSERT INTO risk_assessments (
            assessment_id, transaction_id, timestamp, primary_risk_probability, 
            confidence_in_probability, model_metadata
        ) VALUES (?, ?, ?, ?, ?, ?)
    """, (
        aid,
        tid,
        now,
        decision_result.get("primary_risk_probability"),
        decision_result.get("confidence_in_probability"),
        json.dumps(decision_result.get("policy_metadata", {}))
    ))
    
    # 4. Decision
    cursor.execute("""
        INSERT INTO decisions (
            assessment_id, decision, decision_reason, 
            blocking_guardrail_status, policy_metadata
        ) VALUES (?, ?, ?, ?, ?)
    """, (
        aid,
        decision_result.get("decision"),
        decision_result.get("decision_reason"),
        decision_result.get("blocking_guardrail_status"),
        json.dumps(decision_result.get("policy_metadata", {}))
    ))
    
    # 5. Rule Evidence
    rule_ev = summary.get("rule_evidence", {}) if summary else {}
    for rule in rule_ev.get("triggered_rules", []):
        cursor.execute("""
            INSERT INTO rule_evidence (assessment_id, rule_id, severity)
            VALUES (?, ?, ?)
        """, (aid, rule.get("rule_id"), rule.get("severity")))
        
    # 6. Model Evidence (SHAP)
    model_ev = summary.get("model_evidence", {}) if summary else decision_result.get("model_evidence", {})
    if model_ev:
        for contrib in model_ev.get("top_positive_contributors", []):
            cursor.execute("""
                INSERT INTO model_evidence (assessment_id, feature_name, shap_contribution)
                VALUES (?, ?, ?)
            """, (aid, contrib.get("feature"), contrib.get("shap_contribution")))
            
    # 7. Explanation (if provided)
    if explanation_result:
        cursor.execute("""
            INSERT INTO explanations (
                assessment_id, explanation_text, provider, 
                grounded, limitations, generation_timestamp
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (
            aid,
            explanation_result.get("explanation"),
            explanation_result.get("provider"),
            bool(explanation_result.get("grounded", False)),
            json.dumps(explanation_result.get("limitations", [])),
            now
        ))
        
    # We do NOT commit here. The session manager commits to ensure transactional consistency.
    return aid


def get_assessment(conn: sqlite3.Connection, assessment_id: str) -> Dict[str, Any]:
    """Retrieves an immutable assessment record with its decision and evidence."""
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM risk_assessments WHERE assessment_id = ?", (assessment_id,))
    ra_row = cursor.fetchone()
    if not ra_row:
        return None
        
    result = dict(ra_row)
    
    cursor.execute("SELECT * FROM decisions WHERE assessment_id = ?", (assessment_id,))
    dec_row = cursor.fetchone()
    if dec_row:
        result["decision_record"] = dict(dec_row)
        
    cursor.execute("SELECT rule_id, severity FROM rule_evidence WHERE assessment_id = ?", (assessment_id,))
    result["rule_evidence"] = [dict(r) for r in cursor.fetchall()]
    
    cursor.execute("SELECT feature_name, shap_contribution FROM model_evidence WHERE assessment_id = ?", (assessment_id,))
    result["model_evidence"] = [dict(r) for r in cursor.fetchall()]
    
    cursor.execute("SELECT * FROM explanations WHERE assessment_id = ?", (assessment_id,))
    exp_row = cursor.fetchone()
    if exp_row:
        result["explanation_record"] = dict(exp_row)
        
    return result

def get_assessments_paginated(conn: sqlite3.Connection, limit: int = 50, offset: int = 0):
    cursor = conn.cursor()
    cursor.execute("""
        SELECT assessment_id, transaction_id, timestamp, primary_risk_probability, confidence_in_probability 
        FROM risk_assessments 
        ORDER BY timestamp DESC 
        LIMIT ? OFFSET ?
    """, (limit, offset))
    return [dict(r) for r in cursor.fetchall()]
