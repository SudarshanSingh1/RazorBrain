import sqlite3
import json
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

class IdempotencyError(Exception):
    pass

class IdempotencyService:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def _get_connection(self):
        return sqlite3.connect(self.db_path)

    def check_or_store(self, idempotency_key: str, payload_hash: str) -> Optional[Dict[str, Any]]:
        """
        Checks if the idempotency key exists.
        If it exists and payload matches, returns the stored response.
        If it exists and payload differs, raises IdempotencyError.
        If it doesn't exist, returns None (caller must process and then call `save_response`).
        """
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT request_payload_hash, response_payload, status_code, expires_at FROM idempotency_keys WHERE idempotency_key = ?", (idempotency_key,))
            row = cursor.fetchone()
            
            if row:
                stored_hash, response_payload, status_code, expires_at = row
                if expires_at < now:
                    # Expired, we can overwrite it
                    cursor.execute("DELETE FROM idempotency_keys WHERE idempotency_key = ?", (idempotency_key,))
                    conn.commit()
                    return None
                    
                if stored_hash != payload_hash:
                    raise IdempotencyError("Idempotency key already used with a different payload.")
                    
                return {
                    "response": json.loads(response_payload),
                    "status_code": status_code
                }
            return None

    def save_response(self, idempotency_key: str, payload_hash: str, response: Dict[str, Any], status_code: int, ttl_hours: int = 24):
        now = datetime.now(timezone.utc)
        expires_at = (now + timedelta(hours=ttl_hours)).isoformat()
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    INSERT OR REPLACE INTO idempotency_keys (idempotency_key, request_payload_hash, response_payload, status_code, created_at, expires_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    idempotency_key,
                    payload_hash,
                    json.dumps(response),
                    status_code,
                    now.isoformat(),
                    expires_at
                ))
                conn.commit()
            except Exception as e:
                logger.error(f"Failed to save idempotency key: {e}")
