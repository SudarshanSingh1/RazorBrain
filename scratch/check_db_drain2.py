import sqlite3
from api.lifespan import app_state

with sqlite3.connect(app_state.db_path) as conn:
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM assessments")
    print("Assessments in DB:", cursor.fetchone()[0])
    
    cursor.execute("SELECT COUNT(*) FROM processed_events")
    print("Processed events in DB:", cursor.fetchone()[0])
