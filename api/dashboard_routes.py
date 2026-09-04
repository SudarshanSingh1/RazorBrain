import json
from typing import Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException, Query, Depends, Request

from api.schemas import SimulationRequest
from api.security import get_api_key
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
    unresolved_only: bool = False,
    limit: int = Query(50, le=100),
    offset: int = 0
):
    conn = get_db(request)
    try:
        cursor = conn.cursor()
        
        query = '''
            SELECT 
                r.assessment_id, r.transaction_id, r.timestamp, r.primary_risk_probability, r.confidence_in_probability,
                d.decision, t.amount, t.customer_id, t.merchant_id, e.provider, e.grounded,
                (
                    CASE 
                        WHEN r.primary_risk_probability >= 0.30 THEN 3
                        WHEN EXISTS (SELECT 1 FROM rule_evidence re WHERE re.assessment_id = r.assessment_id AND re.severity = 'CRITICAL') THEN 3
                        WHEN r.primary_risk_probability >= 0.20 THEN 2
                        WHEN EXISTS (SELECT 1 FROM rule_evidence re WHERE re.assessment_id = r.assessment_id AND re.severity = 'HIGH') THEN 2
                        ELSE 1
                    END
                ) as priority_tier_num
            FROM risk_assessments r
            JOIN decisions d ON r.assessment_id = d.assessment_id
            JOIN transactions t ON r.transaction_id = t.transaction_id
            LEFT JOIN explanations e ON r.assessment_id = e.assessment_id
        '''
        
        params = []
        conditions = []
        if decision:
            conditions.append("d.decision = ?")
            params.append(decision)
        if unresolved_only:
            conditions.append("r.assessment_id NOT IN (SELECT assessment_id FROM evaluation_feedback)")
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)

            
        if decision == 'REVIEW':
            query += " ORDER BY priority_tier_num DESC, r.primary_risk_probability DESC NULLS LAST, r.timestamp ASC LIMIT ? OFFSET ?"
        else:
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
            SELECT r.*, d.*, t.amount, t.customer_id, t.merchant_id, t.context_data, e.explanation_text, e.provider, e.grounded, e.limitations,
                   f.ground_truth, f.label_source, f.evaluation_outcome, f.labeled_at
            FROM risk_assessments r
            JOIN decisions d ON r.assessment_id = d.assessment_id
            JOIN transactions t ON r.transaction_id = t.transaction_id
            LEFT JOIN explanations e ON r.assessment_id = e.assessment_id
            LEFT JOIN evaluation_feedback f ON r.assessment_id = f.assessment_id
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
        

        if row["decision"] == "REVIEW":
            from model.review_priority import calculate_review_priority
            probability = row.get("primary_risk_probability")
            confidence = row.get("confidence_in_probability")
            rules = row.get("rule_evidence", [])
            row["review_priority"] = calculate_review_priority(probability, confidence, rules)
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


@router.get("/operational-analytics")
def get_operational_analytics(request: Request):
    conn = get_db(request)
    try:
        cursor = conn.cursor()

        # Total assessments
        cursor.execute("SELECT COUNT(*) as cnt FROM risk_assessments")
        total = cursor.fetchone()["cnt"]

        # Decisions
        cursor.execute("SELECT decision, COUNT(*) as cnt FROM decisions GROUP BY decision")
        decisions_raw = cursor.fetchall()
        decision_counts = { "ALLOW": 0, "REVIEW": 0, "BLOCK": 0 }
        for row in decisions_raw:
            decision_counts[row["decision"]] = row["cnt"]

        allow_cnt = decision_counts["ALLOW"]
        review_cnt = decision_counts["REVIEW"]
        block_cnt = decision_counts["BLOCK"]

        def pct(part, total):
            if total == 0:
                return "NOT MEASURED"
            return f"{(part / total) * 100:.1f}%"

        decision_distribution = {
            "total": total,
            "allow": allow_cnt,
            "review": review_cnt,
            "block": block_cnt,
            "allow_pct": pct(allow_cnt, total),
            "review_pct": pct(review_cnt, total),
            "block_pct": pct(block_cnt, total)
        }

        # Review Workload
        cursor.execute('''
            SELECT 
                COUNT(*) as feedback_recorded,
                SUM(CASE WHEN f.ground_truth = 'FRAUD' THEN 1 ELSE 0 END) as confirmed_fraud,
                SUM(CASE WHEN f.ground_truth = 'LEGITIMATE' THEN 1 ELSE 0 END) as confirmed_legitimate
            FROM decisions d
            JOIN evaluation_feedback f ON d.assessment_id = f.assessment_id
            WHERE d.decision = 'REVIEW'
        ''')
        rw = cursor.fetchone()
        feedback_recorded = rw["feedback_recorded"] or 0
        confirmed_fraud = rw["confirmed_fraud"] or 0
        confirmed_legitimate = rw["confirmed_legitimate"] or 0
        pending = review_cnt - feedback_recorded

        # Evaluation Analytics - from repository.py logic, but quick aggregate
        cursor.execute('''
            SELECT 
                COUNT(*) as labeled_assessments,
                SUM(CASE WHEN evaluation_outcome = 'TP' THEN 1 ELSE 0 END) as tp,
                SUM(CASE WHEN evaluation_outcome = 'FP' THEN 1 ELSE 0 END) as fp,
                SUM(CASE WHEN evaluation_outcome = 'TN' THEN 1 ELSE 0 END) as tn,
                SUM(CASE WHEN evaluation_outcome = 'FN' THEN 1 ELSE 0 END) as fn,
                SUM(CASE WHEN evaluation_outcome = 'UNRESOLVED' THEN 1 ELSE 0 END) as unresolved
            FROM evaluation_feedback
        ''')
        ev = cursor.fetchone()
        labeled_assessments = ev["labeled_assessments"] or 0
        tp = ev["tp"] or 0
        fp = ev["fp"] or 0
        tn = ev["tn"] or 0
        fn = ev["fn"] or 0
        unresolved = ev["unresolved"] or 0

        predicted_positives = tp + fp
        actual_positives = tp + fn

        precision = "NOT MEASURED"
        if predicted_positives > 0:
            precision = f"{(tp / predicted_positives):.4f}"

        recall = "NOT MEASURED"
        if actual_positives > 0:
            recall = f"{(tp / actual_positives):.4f}"

        f1 = "NOT MEASURED"
        if predicted_positives > 0 and actual_positives > 0 and tp > 0:
            p = tp / predicted_positives
            r = tp / actual_positives
            f1 = f"{(2 * p * r / (p + r)):.4f}"
            
        evaluation = {
            "labeled_assessments": labeled_assessments,
            "tp": tp,
            "fp": fp,
            "tn": tn,
            "fn": fn,
            "unresolved": unresolved,
            "precision": precision,
            "recall": recall,
            "f1": f1
        }

        # Priority Distribution
        cursor.execute('''
            SELECT 
                SUM(CASE 
                    WHEN r.primary_risk_probability >= 0.30 THEN 1
                    WHEN EXISTS (SELECT 1 FROM rule_evidence re WHERE re.assessment_id = r.assessment_id AND re.severity = 'CRITICAL') THEN 1
                    ELSE 0 
                END) as critical_cnt,
                SUM(CASE 
                    WHEN r.primary_risk_probability >= 0.30 THEN 0
                    WHEN EXISTS (SELECT 1 FROM rule_evidence re WHERE re.assessment_id = r.assessment_id AND re.severity = 'CRITICAL') THEN 0
                    WHEN r.primary_risk_probability >= 0.20 THEN 1
                    WHEN EXISTS (SELECT 1 FROM rule_evidence re WHERE re.assessment_id = r.assessment_id AND re.severity = 'HIGH') THEN 1
                    ELSE 0 
                END) as high_cnt
            FROM risk_assessments r
            JOIN decisions d ON r.assessment_id = d.assessment_id
            LEFT JOIN evaluation_feedback f ON d.assessment_id = f.assessment_id
            WHERE d.decision = 'REVIEW' AND f.assessment_id IS NULL
        ''')
        p_row = cursor.fetchone()
        critical_cnt = p_row["critical_cnt"] or 0
        high_cnt = p_row["high_cnt"] or 0
        normal_cnt = pending - critical_cnt - high_cnt
        
        priority_distribution = {
            "critical": critical_cnt,
            "high": high_cnt,
            "normal": normal_cnt
        }

        review_workload = {
            "total_review": review_cnt,
            "pending": pending,
            "feedback_recorded": feedback_recorded,
            "unresolved_labeled": feedback_recorded,
            "confirmed_fraud": confirmed_fraud,
            "confirmed_legitimate": confirmed_legitimate,
            "resolution_rate": pct(feedback_recorded, review_cnt),
            "priority_distribution": priority_distribution
        }


        # Timestamps / Assessment-to-label time
        cursor.execute('''
            SELECT CAST(strftime('%s', f.labeled_at) - strftime('%s', r.timestamp) AS INTEGER) as elapsed
            FROM evaluation_feedback f
            JOIN risk_assessments r ON f.assessment_id = r.assessment_id
            WHERE f.labeled_at IS NOT NULL AND r.timestamp IS NOT NULL
            ORDER BY elapsed ASC
        ''')
        times = [row["elapsed"] for row in cursor.fetchall() if row["elapsed"] is not None]
        
        timing = {
            "observations": len(times),
            "min_seconds": "NOT MEASURED",
            "median_seconds": "NOT MEASURED",
            "max_seconds": "NOT MEASURED"
        }
        if times:
            import statistics
            timing["min_seconds"] = str(min(times))
            timing["median_seconds"] = str(int(statistics.median(times)))
            timing["max_seconds"] = str(max(times))

        # Timeseries
        # We need volume by day. Let's do daily buckets.
        cursor.execute('''
            SELECT 
                date(r.timestamp) as dt,
                COUNT(r.assessment_id) as total,
                SUM(CASE WHEN d.decision = 'ALLOW' THEN 1 ELSE 0 END) as allow_cnt,
                SUM(CASE WHEN d.decision = 'REVIEW' THEN 1 ELSE 0 END) as review_cnt,
                SUM(CASE WHEN d.decision = 'BLOCK' THEN 1 ELSE 0 END) as block_cnt,
                SUM(CASE WHEN f.assessment_id IS NOT NULL THEN 1 ELSE 0 END) as feedback_cnt
            FROM risk_assessments r
            JOIN decisions d ON r.assessment_id = d.assessment_id
            LEFT JOIN evaluation_feedback f ON r.assessment_id = f.assessment_id
            GROUP BY date(r.timestamp)
            ORDER BY dt ASC
            LIMIT 90
        ''')
        ts_rows = cursor.fetchall()
        timeseries = []
        for row in ts_rows:
            timeseries.append({
                "date": row["dt"],
                "total": row["total"],
                "allow": row["allow_cnt"],
                "review": row["review_cnt"],
                "block": row["block_cnt"],
                "feedback": row["feedback_cnt"]
            })

        return {
            "decision_distribution": decision_distribution,
            "review_workload": review_workload,
            "evaluation": evaluation,
            "timing": timing,
            "timeseries": timeseries
        }
    finally:
        conn.close()



@router.post("/review-capacity/simulate")
def simulate_review_capacity(request: Request, sim_req: SimulationRequest):
    conn = get_db(request)
    try:
        arrival_rate = sim_req.arrival_rate_per_hour
        if sim_req.use_observed_arrival:
            cursor = conn.cursor()
            # calculate observed hourly arrival rate for REVIEW decisions over the last 7 days
            cursor.execute('''
                SELECT COUNT(*) as cnt
                FROM risk_assessments r
                JOIN decisions d ON r.assessment_id = d.assessment_id
                WHERE d.decision = 'REVIEW'
            ''')
            row = cursor.fetchone()
            # If we don't have enough temporal data in our test set, just divide total by 24h as a fallback observed rate for the prototype.
            arrival_rate = (row["cnt"] / 24.0) if row["cnt"] else 0.0
        elif arrival_rate is None:
            raise HTTPException(status_code=400, detail="Must provide arrival_rate_per_hour or use_observed_arrival=True")

        timeseries = []
        current_backlog = float(sim_req.initial_backlog)
        total_arrivals = 0.0
        total_completed = 0.0
        max_backlog = current_backlog

        for hr in range(1, sim_req.horizon_hours + 1):
            arrivals = arrival_rate
            available_capacity = float(sim_req.capacity_per_hour)
            
            # Discrete step
            total_work = current_backlog + arrivals
            completed = min(total_work, available_capacity)
            current_backlog = total_work - completed
            
            total_arrivals += arrivals
            total_completed += completed
            max_backlog = max(max_backlog, current_backlog)
            
            timeseries.append({
                "hour": hr,
                "arrivals": round(arrivals, 2),
                "completed": round(completed, 2),
                "backlog": round(current_backlog, 2)
            })

        average_backlog = sum(t["backlog"] for t in timeseries) / len(timeseries) if timeseries else 0.0

        if arrival_rate > sim_req.capacity_per_hour:
            interpretation = "Backlog grows under this scenario."
        elif arrival_rate < sim_req.capacity_per_hour:
            interpretation = "Capacity exceeds modeled arrivals under this scenario."
        else:
            interpretation = "Modeled arrival and service capacity are balanced."

        return {
            "mode": "WHAT_IF",
            "assumptions": {
                "horizon_hours": sim_req.horizon_hours,
                "capacity_per_hour": sim_req.capacity_per_hour,
                "arrival_rate_per_hour": round(arrival_rate, 2),
                "initial_backlog": sim_req.initial_backlog,
                "used_observed_arrival": sim_req.use_observed_arrival
            },
            "results": {
                "total_arrivals": round(total_arrivals, 2),
                "total_completed": round(total_completed, 2),
                "ending_backlog": round(current_backlog, 2),
                "maximum_backlog": round(max_backlog, 2),
                "average_backlog": round(average_backlog, 2)
            },
            "timeseries": timeseries,
            "interpretation": interpretation,
            "disclaimer": "SIMULATION ONLY: This is a what-if scenario. It does not represent observed production performance or queue state."
        }
    finally:
        conn.close()




class DriftRequest(BaseModel):
    window_hours: int = Field(24, ge=1, le=720)

@router.get("/drift")
def get_drift_monitoring(request: Request, window_hours: int = Query(24, ge=1, le=720)):
    conn = get_db(request)
    try:
        cursor = conn.cursor()
        
        # 1. Fetch current window transactions
        import pandas as pd
        import json
        from model.feature_engineering import compute_historical_features, transform_features, get_feature_matrix
        from model.drift_monitor import evaluate_drift
        
        # We need transactions and their corresponding predictions and decisions
        query = '''
            SELECT t.transaction_id, t.timestamp, t.amount, t.customer_id, t.merchant_id, t.context_data,
                   r.primary_risk_probability, d.decision
            FROM transactions t
            JOIN risk_assessments r ON t.transaction_id = r.transaction_id
            JOIN decisions d ON r.assessment_id = d.assessment_id
            WHERE t.timestamp >= datetime('now', '-' || ? || ' hours')
        '''
        cursor.execute(query, (window_hours,))
        rows = cursor.fetchall()
        
        if not rows:
            return {"status": "NOT_MEASURED", "reason": f"No observations in the last {window_hours} hours"}
            
        # 2. Reconstruct features
        records = []
        probabilities = []
        decisions = []
        for row in rows:
            # Base record
            rec = {
                "transaction_id": row["transaction_id"],
                "timestamp": row["timestamp"],
                "amount": row["amount"],
                "customer_id": row["customer_id"],
                "merchant_id": row["merchant_id"]
            }
            if row["context_data"]:
                ctx = json.loads(row["context_data"])
                # Merge context data, giving precedence to base record
                for k, v in ctx.items():
                    if k not in rec:
                        rec[k] = v
            records.append(rec)
            probabilities.append(row["primary_risk_probability"])
            decisions.append(row["decision"])
            
        current_df = pd.DataFrame(records)
        
        # Fix timestamp format to match what compute_historical_features expects (ISO8601)
        # SQLite often returns 'YYYY-MM-DD HH:MM:SS'. Pandas can parse it if we let it.
        # But compute_historical_features doesn't specify format, it just calls pd.to_datetime.
        # Wait, if to_datetime crashes on SQLite's format in feature_engineering, we can fix it by formatting it here.
        current_df["timestamp"] = pd.to_datetime(current_df["timestamp"], format="mixed", utc=True).dt.strftime('%Y-%m-%dT%H:%M:%SZ')
        
        # Ensure all necessary keys are present
        required_keys = ["payment_method", "device_id", "ip_address", "location", "customer_account_age_days"]
        for c in ["previous_transaction_count", "previous_fraud_count", "avg_customer_amount", "amount_deviation", "is_new_customer", "merchant_fraud_rate", "is_new_merchant", "txns_last_5min", "txns_last_1h", "txns_last_24h"]:
            required_keys.append(c)
        for k in required_keys:
            if k not in current_df.columns:
                current_df[k] = None
        
        # Also payment_method must be filled
        current_df["payment_method"] = current_df["payment_method"].fillna("credit_card")
        
        df_hist = compute_historical_features(current_df)

        
        app_state = request.app.state.razor_state
        state = app_state.feature_encoder_state
        ref = app_state.reference_distribution
        
        if not ref:
            return {"status": "NOT_MEASURED", "reason": "Reference distribution not found. Was it built during lifespan?"}
            
        val_feat = transform_features(df_hist, state)
        X_curr = get_feature_matrix(val_feat)
        
        # 3. Evaluate drift
        import numpy as np
        drift_result = evaluate_drift(
            X_curr, 
            np.array(probabilities), 
            decisions, 
            ref, 
            min_samples=50
        )
        
        # Add metadata
        if drift_result.get("status") == "MEASURED":
            drift_result["window_hours"] = window_hours
            
        return drift_result
    finally:
        conn.close()
