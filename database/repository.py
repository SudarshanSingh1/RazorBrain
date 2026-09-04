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
        json.dumps(decision_result.get("decision_reason", {})),
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
    model_ev = decision_result.get("model_evidence", {})
    if not model_ev and summary:
        model_ev = summary.get("model_evidence", {})
    if model_ev:
        if isinstance(model_ev, dict):
            contribs = model_ev.get("top_positive_contributors", [])
        else:
            contribs = []
        for contrib in contribs:
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


def calculate_evaluation_outcome(decision: str, ground_truth: str) -> str:
    """
    Deterministic evaluation semantics:
    Predicted positive = BLOCK
    Predicted negative = ALLOW
    """
    decision = decision.upper()
    ground_truth = ground_truth.upper()
    
    if decision == "BLOCK" and ground_truth == "FRAUD":
        return "TP"
    elif decision == "BLOCK" and ground_truth == "LEGITIMATE":
        return "FP"
    elif decision == "ALLOW" and ground_truth == "LEGITIMATE":
        return "TN"
    elif decision == "ALLOW" and ground_truth == "FRAUD":
        return "FN"
    else:
        return "UNRESOLVED"

def record_evaluation_feedback(conn: sqlite3.Connection, assessment_id: str, ground_truth: str, label_source: str, notes: Optional[str] = None) -> dict:
    c = conn.cursor()
    c.execute("SELECT r.transaction_id, d.decision FROM risk_assessments r JOIN decisions d ON r.assessment_id = d.assessment_id WHERE r.assessment_id = ?", (assessment_id,))
    row = c.fetchone()
    if not row:
        raise ValueError("Assessment not found.")
        
    transaction_id = row[0]
    decision = row[1]
    
    outcome = calculate_evaluation_outcome(decision, ground_truth)
    labeled_at = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
    
    try:
        c.execute("""
            INSERT INTO evaluation_feedback (assessment_id, transaction_id, ground_truth, label_source, evaluation_outcome, notes, labeled_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (assessment_id, transaction_id, ground_truth, label_source, outcome, notes, labeled_at))
        conn.commit()
    except sqlite3.IntegrityError:
        raise ValueError("Feedback already exists for this assessment.")
        
    return {
        "assessment_id": assessment_id,
        "transaction_id": transaction_id,
        "ground_truth": ground_truth,
        "label_source": label_source,
        "evaluation_outcome": outcome,
        "labeled_at": labeled_at
    }

def get_evaluation_analytics(conn: sqlite3.Connection) -> dict:
    c = conn.cursor()
    c.execute("""
        SELECT evaluation_outcome, COUNT(*) 
        FROM evaluation_feedback 
        GROUP BY evaluation_outcome
    """)
    counts = {row[0]: row[1] for row in c.fetchall()}
    
    tp = counts.get("TP", 0)
    fp = counts.get("FP", 0)
    tn = counts.get("TN", 0)
    fn = counts.get("FN", 0)
    unresolved = counts.get("UNRESOLVED", 0)
    
    fraud_labels = tp + fn + (counts.get("UNRESOLVED", 0)) # wait, unresolved could be legit or fraud
    # actually better to just query ground truth directly
    c.execute("""
        SELECT ground_truth, COUNT(*) 
        FROM evaluation_feedback 
        GROUP BY ground_truth
    """)
    gt_counts = {row[0]: row[1] for row in c.fetchall()}
    fraud_labels = gt_counts.get("FRAUD", 0)
    legit_labels = gt_counts.get("LEGITIMATE", 0)
    total = fraud_labels + legit_labels
    
    if total == 0:
        return {
            "labeled_volume": 0,
            "fraud_labels": 0,
            "legitimate_labels": 0,
            "tp": 0, "fp": 0, "tn": 0, "fn": 0, "unresolved": 0,
            "precision": "NOT MEASURED",
            "recall": "NOT MEASURED",
            "f1": "NOT MEASURED",
            "specificity": "NOT MEASURED",
            "fpr": "NOT MEASURED",
            "fnr": "NOT MEASURED"
        }
        
    def safe_div(n, d): return f"{(n/d):.4f}" if d > 0 else "NOT MEASURED"
    
    return {
        "labeled_volume": total,
        "fraud_labels": fraud_labels,
        "legitimate_labels": legit_labels,
        "tp": tp, "fp": fp, "tn": tn, "fn": fn, "unresolved": unresolved,
        "precision": safe_div(tp, tp + fp),
        "recall": safe_div(tp, tp + fn),
        "f1": safe_div(2 * tp, 2 * tp + fp + fn),
        "specificity": safe_div(tn, tn + fp),
        "fpr": safe_div(fp, tn + fp),
        "fnr": safe_div(fn, tp + fn)
    }

def get_evaluation_timeseries(conn: sqlite3.Connection) -> list:
    c = conn.cursor()
    # Bucket by day YYYY-MM-DD
    c.execute("""
        SELECT substr(labeled_at, 1, 10) as day, 
               ground_truth,
               evaluation_outcome,
               COUNT(*) 
        FROM evaluation_feedback
        GROUP BY day, ground_truth, evaluation_outcome
        ORDER BY day ASC
    """)
    
    days = {}
    for row in c.fetchall():
        day, gt, outcome, count = row
        if day not in days:
            days[day] = {"date": day, "labeled_volume": 0, "FRAUD": 0, "LEGITIMATE": 0, "TP": 0, "FP": 0, "TN": 0, "FN": 0, "UNRESOLVED": 0}
        
        days[day]["labeled_volume"] += count
        days[day][gt] += count
        if outcome in days[day]:
            days[day][outcome] += count
            
    return list(days.values())


def get_live_historical_features(conn: sqlite3.Connection, customer_id: str, merchant_id: str, current_timestamp: str, current_amount: float, current_device_id: str = None, current_ip_address: str = None, account_creation_timestamp: str = None) -> dict[str, Any]:
    """
    Computes time-aware historical features for a live transaction from the database.
    Strictly adheres to the 17-feature Phase 33 contract.
    """
    c = conn.cursor()
    
    # 1. Customer history
    # Only fetch transactions strictly before current_timestamp
    c.execute("""
        SELECT t.amount, t.timestamp, ef.ground_truth, ef.labeled_at
        FROM transactions t
        LEFT JOIN risk_assessments ra ON t.transaction_id = ra.transaction_id
        LEFT JOIN evaluation_feedback ef ON ra.assessment_id = ef.assessment_id
        WHERE t.customer_id = ? AND t.timestamp < ?
        ORDER BY t.timestamp ASC
    """, (customer_id, current_timestamp))
    cust_rows = c.fetchall()
    
    prev_txn_count = len(cust_rows)
    is_new_customer = 1 if prev_txn_count == 0 else 0
    
    # previous_fraud_count: only count fraud where label was submitted before scoring timestamp
    prev_fraud_count = 0
    for r in cust_rows:
        gt, labeled_at = r[2], r[3]
        if gt == 'FRAUD' and labeled_at and labeled_at <= current_timestamp:
            prev_fraud_count += 1
            
    avg_cust_amount = sum(r[0] for r in cust_rows) / prev_txn_count if prev_txn_count > 0 else 0.0
    amount_deviation = abs(current_amount - avg_cust_amount) if prev_txn_count > 0 else 0.0
    
    import datetime
    ts = datetime.datetime.fromisoformat(current_timestamp.replace("Z", "+00:00"))
    
    # Account age
    if account_creation_timestamp:
        try:
            creation_ts = datetime.datetime.fromisoformat(account_creation_timestamp.replace("Z", "+00:00"))
            customer_account_age_days = max(0, (ts - creation_ts).days)
        except Exception:
            customer_account_age_days = None
    elif prev_txn_count > 0:
        first_txn_ts = datetime.datetime.fromisoformat(cust_rows[0][1].replace("Z", "+00:00"))
        customer_account_age_days = max(0, (ts - first_txn_ts).days)
    else:
        customer_account_age_days = 0
    
    # 2. Velocity
    txns_5m = sum(1 for r in cust_rows if ts - datetime.datetime.fromisoformat(r[1].replace("Z", "+00:00")) <= datetime.timedelta(minutes=5))
    txns_1h = sum(1 for r in cust_rows if ts - datetime.datetime.fromisoformat(r[1].replace("Z", "+00:00")) <= datetime.timedelta(hours=1))
    txns_24h = sum(1 for r in cust_rows if ts - datetime.datetime.fromisoformat(r[1].replace("Z", "+00:00")) <= datetime.timedelta(hours=24))
    
    # 3. Merchant history
    c.execute("""
        SELECT ef.ground_truth, ef.labeled_at
        FROM transactions t
        LEFT JOIN risk_assessments ra ON t.transaction_id = ra.transaction_id
        LEFT JOIN evaluation_feedback ef ON ra.assessment_id = ef.assessment_id
        WHERE t.merchant_id = ? AND t.timestamp < ?
    """, (merchant_id, current_timestamp))
    merch_rows = c.fetchall()
    
    is_new_merchant = 1 if len(merch_rows) == 0 else 0
    
    # merchant_fraud_rate: numerator and denominator from labeled rows only
    labeled_count = 0
    fraud_count = 0
    for r in merch_rows:
        gt, labeled_at = r[0], r[1]
        if gt in ('FRAUD', 'LEGITIMATE') and labeled_at and labeled_at <= current_timestamp:
            labeled_count += 1
            if gt == 'FRAUD':
                fraud_count += 1
                
    merch_fraud_rate = fraud_count / labeled_count if labeled_count > 0 else 0.0

    return {
        "previous_transaction_count": prev_txn_count,
        "previous_fraud_count": prev_fraud_count,
        "avg_customer_amount": avg_cust_amount,
        "amount_deviation": amount_deviation,
        "is_new_customer": is_new_customer,
        "txns_last_5min": txns_5m,
        "txns_last_1h": txns_1h,
        "txns_last_24h": txns_24h,
        "is_new_merchant": is_new_merchant,
        "merchant_fraud_rate": merch_fraud_rate,
        "customer_account_age_days": customer_account_age_days
    }


