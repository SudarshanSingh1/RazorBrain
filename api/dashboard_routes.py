import sqlite3
import json
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Query, Depends
from api.security import get_api_key
from fastapi import Request

from database.connection import get_connection

router = APIRouter(prefix="/dashboard", tags=["Dashboard"], dependencies=[Depends(get_api_key)])

def dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d

def get_db(request: Request):
    db_path = request.app.state.razor_state.db_path
    conn = get_connection(db_path)
    conn.row_factory = dict_factory
    return conn

@router.get("/summary")
def get_summary(request: Request):
    conn = get_db(request)
    try:
        cursor = conn.cursor()
        
        # Total assessments
        cursor.execute("SELECT COUNT(*) as cnt FROM risk_assessments")
        total = cursor.fetchone()["cnt"]
        
        # Decision breakdown
        cursor.execute("SELECT decision, COUNT(*) as cnt FROM decisions GROUP BY decision")
        decisions_raw = cursor.fetchall()
        decision_counts = { "ALLOW": 0, "REVIEW": 0, "BLOCK": 0 }
        for row in decisions_raw:
            decision_counts[row["decision"]] = row["cnt"]
            
        # Evidence availability
        cursor.execute("SELECT confidence_in_probability as conf, COUNT(*) as cnt FROM risk_assessments GROUP BY confidence_in_probability")
        conf_raw = cursor.fetchall()
        confidence_counts = { row["conf"]: row["cnt"] for row in conf_raw }
        
        return {
            "total_assessments": total,
            "decisions": decision_counts,
            "confidence": confidence_counts
        }
    finally:
        conn.close()

@router.get("/risk-distribution")
def get_risk_distribution(request: Request):
    conn = get_db(request)
    try:
        cursor = conn.cursor()
        # Fetch all probabilities (not a huge table in our prototype, but in prod we'd group them in SQL)
        cursor.execute("SELECT primary_risk_probability as prob FROM risk_assessments WHERE primary_risk_probability IS NOT NULL")
        rows = cursor.fetchall()
        
        # Create bins 0.0 to 1.0 (e.g. 20 bins)
        bins = [0]*20
        for r in rows:
            p = r["prob"]
            b = min(19, int(p * 20))
            bins[b] += 1
            
        labels = [f"{(i*5)}-{((i+1)*5)}%" for i in range(20)]
        
        return {
            "labels": labels,
            "counts": bins
        }
    finally:
        conn.close()

@router.get("/rule-intelligence")
def get_rule_intelligence(request: Request):
    conn = get_db(request)
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT rule_id, severity, COUNT(*) as count 
            FROM rule_evidence 
            GROUP BY rule_id, severity
            ORDER BY count DESC
        """)
        return cursor.fetchall()
    finally:
        conn.close()

@router.get("/transactions")
def get_transactions(
    request: Request,
    decision: Optional[str] = None,
    limit: int = Query(50, le=100),
    offset: int = 0
):
    conn = get_db(request)
    try:
        cursor = conn.cursor()
        
        query = """
            SELECT r.assessment_id, r.transaction_id, r.timestamp, r.primary_risk_probability, r.confidence_in_probability,
                   d.decision, t.amount, t.customer_id, t.merchant_id, e.provider, e.grounded
            FROM risk_assessments r
            JOIN decisions d ON r.assessment_id = d.assessment_id
            JOIN transactions t ON r.transaction_id = t.transaction_id
            LEFT JOIN explanations e ON r.assessment_id = e.assessment_id
        """
        
        params = []
        if decision:
            query += " WHERE d.decision = ?"
            params.append(decision)
            
        query += " ORDER BY r.timestamp DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        cursor.execute(query, params)
        data = cursor.fetchall()
        
        # get total count for pagination
        count_query = """
            SELECT COUNT(*) as total
            FROM risk_assessments r
            JOIN decisions d ON r.assessment_id = d.assessment_id
        """
        count_params = []
        if decision:
            count_query += " WHERE d.decision = ?"
            count_params.append(decision)
            
        cursor.execute(count_query, count_params)
        total = cursor.fetchone()["total"]
        
        return {
            "data": data,
            "total": total,
            "limit": limit,
            "offset": offset
        }
    finally:
        conn.close()

@router.get("/transactions/{assessment_id}")
def get_transaction_detail(request: Request, assessment_id: str):
    conn = get_db(request)
    try:
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT r.*, d.*, t.amount, t.customer_id, t.merchant_id, t.context_data, e.explanation_text, e.provider, e.grounded, e.limitations
            FROM risk_assessments r
            JOIN decisions d ON r.assessment_id = d.assessment_id
            JOIN transactions t ON r.transaction_id = t.transaction_id
            LEFT JOIN explanations e ON r.assessment_id = e.assessment_id
            WHERE r.assessment_id = ?
        """, (assessment_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Assessment not found")
            
        # Context data is JSON
        if row.get("context_data"):
            row["context_data"] = json.loads(row["context_data"])
            row["payment_method"] = row["context_data"].get("payment_method")
            
        if row.get("policy_metadata"):
            row["policy_metadata"] = json.loads(row["policy_metadata"])
            
        if row.get("limitations"):
            row["limitations"] = json.loads(row["limitations"])
            
        # Get rules
        cursor.execute("SELECT rule_id, severity FROM rule_evidence WHERE assessment_id = ?", (assessment_id,))
        row["rule_evidence"] = cursor.fetchall()
        
        # Get model evidence
        cursor.execute("SELECT feature_name, shap_contribution FROM model_evidence WHERE assessment_id = ?", (assessment_id,))
        row["model_evidence"] = cursor.fetchall()
        
        return row
    finally:
        conn.close()


@router.get("/trends")
def get_trends(request: Request):
    conn = get_db(request)
    try:
        cursor = conn.cursor()
        
        # SQLite datetime function is required to bucket.
        # We'll bucket by day to keep it simple, since we have limited data.
        # Format: YYYY-MM-DD
        cursor.execute('''
            SELECT 
                date(r.timestamp) as bucket,
                d.decision,
                COUNT(*) as cnt
            FROM risk_assessments r
            JOIN decisions d ON r.assessment_id = d.assessment_id
            GROUP BY date(r.timestamp), d.decision
            ORDER BY bucket ASC
        ''')
        rows = cursor.fetchall()
        
        # Structure the data
        buckets = {}
        for r in rows:
            b = r["bucket"]
            if b not in buckets:
                buckets[b] = {"ALLOW": 0, "REVIEW": 0, "BLOCK": 0, "TOTAL": 0}
            buckets[b][r["decision"]] = r["cnt"]
            buckets[b]["TOTAL"] += r["cnt"]
            
        res = []
        for b, counts in buckets.items():
            res.append({"date": b, **counts})
            
        return res
    finally:
        conn.close()

@router.get("/probability-amount")
def get_probability_amount(request: Request):
    conn = get_db(request)
    try:
        cursor = conn.cursor()
        # Fetch non-null probability and amount, bounded to 1000 records for performance
        cursor.execute('''
            SELECT r.primary_risk_probability as prob, t.amount
            FROM risk_assessments r
            JOIN transactions t ON r.transaction_id = t.transaction_id
            WHERE r.primary_risk_probability IS NOT NULL AND t.amount IS NOT NULL
            ORDER BY r.timestamp DESC
            LIMIT 1000
        ''')
        return cursor.fetchall()
    finally:
        conn.close()

@router.get("/shap-intelligence")
def get_shap_intelligence(request: Request):
    conn = get_db(request)
    try:
        cursor = conn.cursor()
        # Calculate mean absolute SHAP magnitude per feature
        cursor.execute('''
            SELECT feature_name, AVG(ABS(shap_contribution)) as mean_abs_shap
            FROM model_evidence
            GROUP BY feature_name
            ORDER BY mean_abs_shap DESC
            LIMIT 15
        ''')
        return cursor.fetchall()
    finally:
        conn.close()
