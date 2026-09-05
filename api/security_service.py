import sqlite3
import hashlib
import secrets
import json
import logging
import uuid
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class SecurityError(Exception):
    pass

class AuthenticationError(Exception):
    pass

class AuthorizationError(Exception):
    pass

def hash_api_key(api_key: str) -> str:
    # Use SHA-256 for key hashing
    return hashlib.sha256(api_key.encode('utf-8')).hexdigest()

class SecurityService:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def _get_connection(self):
        return sqlite3.connect(self.db_path)

    def _row_to_dict(self, row, cursor) -> Dict[str, Any]:
        return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}

    def create_api_key(self, name: str, role: str = "SCORER", expires_at: Optional[str] = None) -> Tuple[Dict[str, Any], str]:
        """Creates a new API key. Returns (metadata, raw_secret). The raw_secret is only available once."""
        raw_secret = f"rb_live_{secrets.token_urlsafe(32)}"
        key_hash = hash_api_key(raw_secret)
        prefix = raw_secret[:12] + "..." + raw_secret[-4:]
        key_id = f"ak_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO api_keys (id, name, key_hash, prefix, role, status, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?, 'ACTIVE', ?, ?)
            """, (key_id, name, key_hash, prefix, role, now, expires_at))
            conn.commit()
            
        self._audit("API_KEY_CREATED", f"Created API Key {key_id} ({name}) with role {role}")
        return self.get_api_key_metadata(key_id), raw_secret

    def get_api_key_metadata(self, key_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, name, prefix, role, status, created_at, expires_at, last_used_at, revoked_at FROM api_keys WHERE id = ?", (key_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_dict(row, cursor)

    def list_api_keys(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, name, prefix, role, status, created_at, expires_at, last_used_at, revoked_at FROM api_keys ORDER BY created_at DESC")
            return [self._row_to_dict(r, cursor) for r in cursor.fetchall()]

    def revoke_api_key(self, key_id: str) -> Dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE api_keys SET status = 'REVOKED', revoked_at = ? WHERE id = ? AND status = 'ACTIVE'", (now, key_id))
            if cursor.rowcount == 0:
                raise SecurityError("Key not found or already revoked/expired.")
            conn.commit()
            
        self._audit("API_KEY_REVOKED", f"Revoked API Key {key_id}")
        return self.get_api_key_metadata(key_id)

    def rotate_api_key(self, key_id: str, new_name: str, role: str = "SCORER", expires_at: Optional[str] = None) -> Tuple[Dict[str, Any], str]:
        """Rotates a key by creating a new one. The old one must be revoked explicitly later by the user (or handled by expiration)."""
        # Alternatively, we can leave the old one active for a grace period, but the prompt says:
        # "Both Temporarily Valid -> Client Migrates -> Old Key Revoked" (meaning user revokes it).
        new_meta, new_secret = self.create_api_key(new_name, role, expires_at)
        self._audit("API_KEY_ROTATED", f"Created rotated replacement {new_meta['id']} for {key_id}")
        return new_meta, new_secret
        
    def authenticate_key(self, raw_secret: str, fallback_env_key: Optional[str] = None) -> Dict[str, Any]:
        """Authenticates a raw key. Updates last_used_at. Returns metadata."""
        # Check env fallback for bootstrapping/legacy if DB is empty?
        # To avoid performance hits of checking if DB is empty, we just query DB.
        key_hash = hash_api_key(raw_secret)
        now = datetime.now(timezone.utc).isoformat()
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM api_keys WHERE key_hash = ?", (key_hash,))
            row = cursor.fetchone()
            
            if not row:
                # Fallback to env key
                if fallback_env_key and secrets.compare_digest(raw_secret, fallback_env_key):
                    return {
                        "id": "env-fallback",
                        "name": "Legacy ENV Key",
                        "role": "ADMIN",
                        "status": "ACTIVE",
                        "prefix": "env_***"
                    }
                self._audit("API_KEY_AUTH_FAILED", "Authentication failed: Key not found")
                raise AuthenticationError("Invalid API Key")
                
            meta = self._row_to_dict(row, cursor)
            
            if meta["status"] != "ACTIVE":
                self._audit("API_KEY_AUTH_FAILED", f"Authentication failed: Key {meta['id']} is {meta['status']}")
                raise AuthenticationError(f"API Key is {meta['status']}")
                
            if meta["expires_at"] and now > meta["expires_at"]:
                cursor.execute("UPDATE api_keys SET status = 'EXPIRED' WHERE id = ?", (meta["id"],))
                conn.commit()
                self._audit("API_KEY_EXPIRED", f"Key {meta['id']} expired during auth")
                raise AuthenticationError("API Key is EXPIRED")
                
            # Update last used
            cursor.execute("UPDATE api_keys SET last_used_at = ? WHERE id = ?", (now, meta["id"]))
            conn.commit()
            
            # Remove hash before returning metadata
            meta.pop("key_hash", None)
            return meta

    def _audit(self, action: str, details: str, **kwargs):
        now = datetime.now(timezone.utc).isoformat()
        metadata = json.dumps(kwargs)
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO event_ledger (event_id, event_type, status, payload, created_at, updated_at)
                    VALUES (?, ?, 'COMPLETED', ?, ?, ?)
                """, (
                    f"evt_{uuid.uuid4().hex}",
                    action,
                    json.dumps({"details": details, "metadata": metadata}),
                    now,
                    now
                ))
                conn.commit()
        except Exception as e:
            logger.error(f"Audit failed: {e}")
