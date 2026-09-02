import sqlite3
from contextlib import contextmanager
import json
import logging

logger = logging.getLogger(__name__)

# Ensure sqlite3 enforces foreign keys
def get_connection(db_path="razorbrain.db"):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

@contextmanager
def get_session(db_path="razorbrain.db"):
    """
    Provides a transactional scope around a series of operations.
    Yields a connection that automatically commits on success,
    or rolls back on exception.
    """
    conn = get_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()
