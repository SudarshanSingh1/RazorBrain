import sqlite3
from api.lifespan import app_state

with sqlite3.connect(app_state.db_path) as conn:
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM risk_assessments")
    print("Risk Assessments in DB:", cursor.fetchone()[0])
    
    cursor.execute("SELECT COUNT(*) FROM processed_events")
    print("Processed events in DB:", cursor.fetchone()[0])
    
    cursor.execute("SELECT status, COUNT(*) FROM processed_events GROUP BY status")
    print("Event statuses:")
    for row in cursor.fetchall():
        print(f"  {row[0]}: {row[1]}")
