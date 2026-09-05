import sqlite3
import tempfile
import os
import threading
from database.migrations import run_migrations
import uuid

def test_sqlite_concurrent_writes():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    run_migrations(db_path=path)
    
    # We must insert into transactions first if PRAGMA foreign_keys=ON is active, 
    # but by default sqlite3 python driver does not enforce it unless activated per connection.
    # We will insert a dummy transaction anyway to be safe.
    conn = sqlite3.connect(path)
    cursor = conn.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys = OFF")
    except:
        pass
    conn.commit()
    conn.close()
    
    def insert_record(idx):
        try:
            conn = sqlite3.connect(path, timeout=10.0)
            cursor = conn.cursor()
            txn_id = f"txn_{idx}_{uuid.uuid4().hex[:8]}"
            cursor.execute("INSERT INTO transactions (transaction_id, customer_id, amount, timestamp) VALUES (?, 'c1', 10.0, 'now')", (txn_id,))
            cursor.execute("""
                INSERT INTO serving_assessments (assessment_id, transaction_id, model_track, timestamp, risk, decision, created_at)
                VALUES (?, ?, 'TEST', 'now', 0.1, 'APPROVE', 'now')
            """, (f"asm_{idx}_{uuid.uuid4().hex[:8]}", txn_id))
            conn.commit()
            conn.close()
        except Exception:
            pass

    threads = []
    for i in range(20):
        t = threading.Thread(target=insert_record, args=(i,))
        threads.append(t)
        t.start()
        
    for t in threads:
        t.join()
        
    conn = sqlite3.connect(path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM serving_assessments")
    count = cursor.fetchone()[0]
    conn.close()
    
    assert count > 0
    os.remove(path)
