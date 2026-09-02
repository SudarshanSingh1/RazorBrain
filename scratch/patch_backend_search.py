import re

with open("api/dashboard_routes.py", "r") as f:
    text = f.read()

# Replace the def get_transactions signature and query logic
search_func = """def get_transactions(
    request: Request,
    decision: Optional[str] = None,
    limit: int = Query(50, le=100),
    offset: int = 0
):
    conn = get_db(request)
    try:
        cursor = conn.cursor()
        
        query = \"\"\"
            SELECT r.assessment_id, r.transaction_id, r.timestamp, r.primary_risk_probability, r.confidence_in_probability,
                   d.decision, t.amount, t.customer_id, t.merchant_id, e.provider, e.grounded
            FROM risk_assessments r
            JOIN decisions d ON r.assessment_id = d.assessment_id
            JOIN transactions t ON r.transaction_id = t.transaction_id
            LEFT JOIN explanations e ON r.assessment_id = e.assessment_id
        \"\"\"
        
        params = []
        
        if decision:
            query += " WHERE d.decision = ?"
            params.append(decision)
            
        query += " ORDER BY r.timestamp DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])"""

replace_func = """def get_transactions(
    request: Request,
    decision: Optional[str] = None,
    transaction_id: Optional[str] = None,
    limit: int = Query(50, le=100),
    offset: int = 0
):
    conn = get_db(request)
    try:
        cursor = conn.cursor()
        
        query = \"\"\"
            SELECT r.assessment_id, r.transaction_id, r.timestamp, r.primary_risk_probability, r.confidence_in_probability,
                   d.decision, t.amount, t.customer_id, t.merchant_id, e.provider, e.grounded
            FROM risk_assessments r
            JOIN decisions d ON r.assessment_id = d.assessment_id
            JOIN transactions t ON r.transaction_id = t.transaction_id
            LEFT JOIN explanations e ON r.assessment_id = e.assessment_id
        \"\"\"
        
        params = []
        conditions = []
        
        if decision:
            conditions.append("d.decision = ?")
            params.append(decision)
            
        if transaction_id:
            conditions.append("r.transaction_id LIKE ?")
            params.append(f"%{transaction_id}%")
            
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
            
        query += " ORDER BY r.timestamp DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])"""

if search_func in text:
    text = text.replace(search_func, replace_func)

# Also fix the count query right after it
search_count = """        count_query = "SELECT COUNT(*) FROM risk_assessments r JOIN decisions d ON r.assessment_id = d.assessment_id"
        count_params = []
        if decision:
            count_query += " WHERE d.decision = ?"
            count_params.append(decision)"""

replace_count = """        count_query = "SELECT COUNT(*) FROM risk_assessments r JOIN decisions d ON r.assessment_id = d.assessment_id JOIN transactions t ON r.transaction_id = t.transaction_id"
        count_params = []
        if conditions:
            count_query += " WHERE " + " AND ".join(conditions)
            count_params.extend(params[:-2]) # excluding limit and offset"""

if search_count in text:
    text = text.replace(search_count, replace_count)

with open("api/dashboard_routes.py", "w") as f:
    f.write(text)

print("Patched backend for search.")
