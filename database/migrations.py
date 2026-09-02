import os
import sqlite3
import logging
from database.connection import get_connection

logger = logging.getLogger(__name__)

def run_migrations(db_path="razorbrain.db", migrations_dir="database/migrations"):
    """
    Explicit, reproducible migration runner.
    Applies .sql files sequentially based on their numeric prefix.
    """
    conn = get_connection(db_path)
    cursor = conn.cursor()
    
    # Check if migrations table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='migrations'")
    has_migrations_table = cursor.fetchone() is not None
    
    if not has_migrations_table:
        # We assume 001_initial_schema.sql will create this table.
        # But we need to bootstrap to know what's applied. 
        # Actually, 001_initial_schema creates it, so we'll just track memory.
        applied = set()
    else:
        cursor.execute("SELECT version FROM migrations")
        applied = {row["version"] for row in cursor.fetchall()}
        
    migration_files = []
    if os.path.exists(migrations_dir):
        for f in os.listdir(migrations_dir):
            if f.endswith(".sql"):
                try:
                    version = int(f.split("_")[0])
                    migration_files.append((version, f))
                except ValueError:
                    pass
                    
    migration_files.sort()
    
    for version, filename in migration_files:
        if version not in applied:
            logger.info(f"Applying migration: {filename}")
            filepath = os.path.join(migrations_dir, filename)
            with open(filepath, "r") as f:
                sql = f.read()
            
            try:
                # We execute script to allow multiple statements
                cursor.executescript(sql)
                # Record migration
                cursor.execute("INSERT INTO migrations (version) VALUES (?)", (version,))
                conn.commit()
            except sqlite3.Error as e:
                conn.rollback()
                logger.error(f"Migration {filename} failed: {str(e)}")
                raise
                
    conn.close()
