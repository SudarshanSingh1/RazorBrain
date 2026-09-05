import sqlite3
import json
import uuid
import os
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class ManagementError(Exception):
    pass

class ModelManagementService:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def _get_connection(self):
        return sqlite3.connect(self.db_path)

    def _row_to_dict(self, row, cursor) -> Dict[str, Any]:
        return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}

    def get_active_model(self) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM model_registry WHERE status = 'ACTIVE'")
            rows = cursor.fetchall()
            if len(rows) > 1:
                logger.error("CRITICAL: Multiple active models detected in registry.")
                # We return the most recently activated one to prevent crashing
                rows = sorted(rows, key=lambda x: x[12] or "", reverse=True)
            
            if not rows:
                return None
            return self._row_to_dict(rows[0], cursor)

    def get_model(self, model_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM model_registry WHERE id = ?", (model_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_dict(row, cursor)

    def list_models(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM model_registry ORDER BY created_at DESC")
            return [self._row_to_dict(r, cursor) for r in cursor.fetchall()]

    def register_model(self, data: Dict[str, Any]) -> Dict[str, Any]:
        model_id = f"m-{uuid.uuid4().hex[:8]}"
        now = datetime.now(timezone.utc).isoformat()
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    INSERT INTO model_registry (
                        id, model_name, model_version, status, artifact_path, 
                        artifact_checksum, feature_contract_version, model_type, 
                        calibration_version, training_metadata, description, 
                        created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    model_id,
                    data.get("model_name"),
                    data.get("model_version"),
                    "INACTIVE",
                    data.get("artifact_path"),
                    data.get("artifact_checksum"),
                    data.get("feature_contract_version"),
                    data.get("model_type"),
                    data.get("calibration_version"),
                    json.dumps(data.get("training_metadata", {})),
                    data.get("description"),
                    now
                ))
                conn.commit()
            except sqlite3.IntegrityError as e:
                raise ManagementError(f"Model version already exists or invalid data: {e}")

        self._audit("MODEL_REGISTERED", f"Registered model {model_id} ({data.get('model_version')})", model_id=model_id)
        return self.get_model(model_id)

    def activate_model(self, model_id: str, is_rollback: bool = False) -> Dict[str, Any]:
        model = self.get_model(model_id)
        if not model:
            raise ManagementError(f"Model {model_id} not found.")

        # Validation
        if not os.path.exists(model["artifact_path"]):
            self._audit("MODEL_ACTIVATION_FAILED", f"Artifact missing: {model['artifact_path']}", model_id=model_id)
            raise ManagementError(f"Artifact missing: {model['artifact_path']}")
        
        # Test loading the model to ensure it is readable and compatible
        try:
            import joblib
            joblib.load(model["artifact_path"])
        except Exception as e:
            self._audit("MODEL_ACTIVATION_FAILED", f"Artifact corrupted: {e}", model_id=model_id)
            raise ManagementError(f"Artifact unreadable/corrupted: {e}")

        # Activate atomically
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Deactivate currently active
            cursor.execute("UPDATE model_registry SET status = 'INACTIVE', deactivated_at = ? WHERE status = 'ACTIVE'", (now,))
            
            # Activate new
            cursor.execute("UPDATE model_registry SET status = 'ACTIVE', activated_at = ? WHERE id = ?", (now, model_id))
            conn.commit()
            
        action = "MODEL_ROLLBACK" if is_rollback else "MODEL_ACTIVATED"
        self._audit(action, f"Activated model {model_id} ({model['model_version']})", model_id=model_id)
        
        return self.get_model(model_id)


class PolicyManagementService:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def _get_connection(self):
        return sqlite3.connect(self.db_path)

    def _row_to_dict(self, row, cursor) -> Dict[str, Any]:
        return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}

    def get_active_policy(self) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM policy_registry WHERE status = 'ACTIVE'")
            rows = cursor.fetchall()
            if len(rows) > 1:
                logger.error("CRITICAL: Multiple active policies detected in registry.")
                rows = sorted(rows, key=lambda x: x[12] or "", reverse=True)
            if not rows:
                return None
            return self._row_to_dict(rows[0], cursor)

    def get_policy(self, policy_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM policy_registry WHERE id = ?", (policy_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_dict(row, cursor)

    def list_policies(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM policy_registry ORDER BY created_at DESC")
            return [self._row_to_dict(r, cursor) for r in cursor.fetchall()]

    def _validate_policy_configuration(self, config_str: str):
        try:
            config = json.loads(config_str)
        except json.JSONDecodeError:
            raise ManagementError("Policy configuration must be valid JSON.")
            
        if "thresholds" not in config:
            raise ManagementError("Missing 'thresholds' in configuration.")
            
        t = config["thresholds"]
        app = t.get("approve_max")
        rev = t.get("review_max")
        su = t.get("step_up_max")
        
        if None in (app, rev, su):
            raise ManagementError("Missing threshold values.")
            
        if not (0 <= app <= rev <= su <= 1):
            raise ManagementError(f"Invalid threshold ordering: {app} <= {rev} <= {su}")

    def create_policy(self, data: Dict[str, Any]) -> Dict[str, Any]:
        config_str = data.get("configuration")
        if isinstance(config_str, dict):
            config_str = json.dumps(config_str)
            
        self._validate_policy_configuration(config_str)
        
        policy_id = f"p-{uuid.uuid4().hex[:8]}"
        now = datetime.now(timezone.utc).isoformat()
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    INSERT INTO policy_registry (
                        id, policy_name, policy_version, status, configuration, 
                        configuration_checksum, description, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    policy_id,
                    data.get("policy_name"),
                    data.get("policy_version"),
                    "INACTIVE",
                    config_str,
                    data.get("configuration_checksum"),
                    data.get("description"),
                    now
                ))
                conn.commit()
            except sqlite3.IntegrityError as e:
                raise ManagementError(f"Policy version already exists or invalid data: {e}")

        # Note: We use the existing audit trail implementation if possible, or print
        self._audit("POLICY_CREATED", f"Created policy {policy_id} ({data.get('policy_version')})", policy_id=policy_id)
        return self.get_policy(policy_id)

    def activate_policy(self, policy_id: str, is_rollback: bool = False) -> Dict[str, Any]:
        policy = self.get_policy(policy_id)
        if not policy:
            raise ManagementError(f"Policy {policy_id} not found.")

        try:
            self._validate_policy_configuration(policy["configuration"])
        except ManagementError as e:
            self._audit("POLICY_ACTIVATION_FAILED", f"Validation failed: {e}", policy_id=policy_id)
            raise
            
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE policy_registry SET status = 'INACTIVE', deactivated_at = ? WHERE status = 'ACTIVE'", (now,))
            cursor.execute("UPDATE policy_registry SET status = 'ACTIVE', activated_at = ? WHERE id = ?", (now, policy_id))
            conn.commit()
            
        action = "POLICY_ROLLBACK" if is_rollback else "POLICY_ACTIVATED"
        self._audit(action, f"Activated policy {policy_id} ({policy['policy_version']})", policy_id=policy_id)
        
        return self.get_policy(policy_id)

    def _audit(self, action: str, details: str, **kwargs):
        now = datetime.now(timezone.utc).isoformat()
        metadata = json.dumps(kwargs)
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                # Insert into event_ledger
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
            
# Helper mixin
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

ModelManagementService._audit = _audit
