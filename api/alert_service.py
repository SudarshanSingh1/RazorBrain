"""
Alert Service for RazorBrain Monitoring.

Manages the complete alert lifecycle: creation, deduplication,
cooldown, acknowledgement, and resolution. All alert state is
persisted to SQLite.
"""

import json
import logging
import math
import sqlite3
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional

from database.connection import get_connection

logger = logging.getLogger(__name__)

# ── Alert Constants ───────────────────────────────────────────────────────────

VALID_SEVERITIES = {"INFO", "WARNING", "CRITICAL"}
VALID_STATUSES = {"OPEN", "ACKNOWLEDGED", "RESOLVED"}
VALID_CATEGORIES = {
    "SYSTEM", "MODEL", "FRAUD", "DRIFT", "QUEUE",
    "API", "DATABASE", "RULE_ENGINE", "DATA_QUALITY", "FEEDBACK",
}

# Default cooldown in seconds per category
DEFAULT_COOLDOWNS: Dict[str, int] = {
    "FRAUD": 300,        # 5 minutes
    "MODEL": 120,        # 2 minutes
    "API": 60,           # 1 minute
    "DATABASE": 120,
    "RULE_ENGINE": 120,
    "DRIFT": 600,        # 10 minutes
    "QUEUE": 300,
    "DATA_QUALITY": 300,
    "FEEDBACK": 600,
    "SYSTEM": 60,
}


# ── Exceptions ────────────────────────────────────────────────────────────────

class AlertNotFoundError(Exception):
    pass

class InvalidAlertTransitionError(Exception):
    pass


# ── Alert Service ─────────────────────────────────────────────────────────────

class AlertService:
    """
    Manages the complete alert lifecycle with deduplication and cooldown.
    """

    def __init__(self, db_path: str = "razorbrain_api.db", cooldowns: Optional[Dict[str, int]] = None):
        self._db_path = db_path
        self._cooldowns = cooldowns or DEFAULT_COOLDOWNS

    # ── Public: Create / Upsert ───────────────────────────────────────────

    def create_or_update_alert(
        self,
        alert_type: str,
        severity: str,
        category: str,
        title: str,
        message: str,
        metric_name: Optional[str] = None,
        metric_value: Optional[float] = None,
        threshold: Optional[float] = None,
        source: str = "monitoring_service",
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        deduplication_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Creates a new alert or updates an existing OPEN/ACKNOWLEDGED alert
        with the same deduplication key.

        Returns the alert record dict.
        """
        # ── Validate ──────────────────────────────────────────────────────
        if severity not in VALID_SEVERITIES:
            raise ValueError(f"Invalid severity: {severity}")
        if category not in VALID_CATEGORIES:
            raise ValueError(f"Invalid category: {category}")

        # Sanitise metric_value
        if metric_value is not None and not math.isfinite(metric_value):
            metric_value = None
        if threshold is not None and not math.isfinite(threshold):
            threshold = None

        now = datetime.now(timezone.utc).isoformat()
        dedup_key = deduplication_key or self._make_dedup_key(alert_type, source, category, entity_type, entity_id, metric_name)

        conn = get_connection(self._db_path)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.cursor()

            # ── Check for existing open/ack alert with same dedup key ─────
            cursor.execute(
                """SELECT * FROM monitoring_alerts
                   WHERE deduplication_key = ? AND status IN ('OPEN', 'ACKNOWLEDGED')
                   ORDER BY created_at DESC LIMIT 1""",
                (dedup_key,),
            )
            existing = cursor.fetchone()

            if existing:
                # ── Cooldown check ────────────────────────────────────────
                cooldown_until = existing["cooldown_until"]
                if cooldown_until and now < cooldown_until:
                    # Still in cooldown — update evidence silently
                    cursor.execute(
                        """UPDATE monitoring_alerts
                           SET last_detected_at = ?,
                               metric_value = COALESCE(?, metric_value),
                               occurrence_count = occurrence_count + 1,
                               metadata = COALESCE(?, metadata),
                               updated_at = ?
                           WHERE id = ?""",
                        (now, metric_value, json.dumps(metadata) if metadata else None, now, existing["id"]),
                    )
                    conn.commit()
                    cursor.execute("SELECT * FROM monitoring_alerts WHERE id = ?", (existing["id"],))
                    return self._row_to_dict(cursor.fetchone())

                # ── Update existing alert ─────────────────────────────────
                new_cooldown = self._calculate_cooldown(category, now)
                cursor.execute(
                    """UPDATE monitoring_alerts
                       SET severity = CASE WHEN ? = 'CRITICAL' THEN 'CRITICAL' ELSE severity END,
                           last_detected_at = ?,
                           metric_value = COALESCE(?, metric_value),
                           threshold = COALESCE(?, threshold),
                           occurrence_count = occurrence_count + 1,
                           metadata = COALESCE(?, metadata),
                           message = ?,
                           updated_at = ?,
                           cooldown_until = ?
                       WHERE id = ?""",
                    (
                        severity, now, metric_value, threshold,
                        json.dumps(metadata) if metadata else None,
                        message, now, new_cooldown, existing["id"],
                    ),
                )
                conn.commit()
                # Return refreshed row
                cursor.execute("SELECT * FROM monitoring_alerts WHERE id = ?", (existing["id"],))
                return self._row_to_dict(cursor.fetchone())

            # ── Create new alert ──────────────────────────────────────────

            # Check if we recently resolved one with the same dedup key (prevent flapping)
            cursor.execute(
                """SELECT resolved_at FROM monitoring_alerts
                   WHERE deduplication_key = ? AND status = 'RESOLVED'
                   ORDER BY resolved_at DESC LIMIT 1""",
                (dedup_key,),
            )
            cursor.fetchone()
            cooldown_until_val = self._calculate_cooldown(category, now)

            alert_id = str(uuid.uuid4())
            meta_json = json.dumps(metadata) if metadata else None

            cursor.execute(
                """INSERT INTO monitoring_alerts
                   (id, alert_type, severity, status, category, title, message, source,
                    metric_name, metric_value, threshold, deduplication_key,
                    entity_type, entity_id, occurrence_count, metadata,
                    first_detected_at, last_detected_at, created_at, updated_at, cooldown_until)
                   VALUES (?, ?, ?, 'OPEN', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?)""",
                (
                    alert_id, alert_type, severity, category, title, message, source,
                    metric_name, metric_value, threshold, dedup_key,
                    entity_type, entity_id, meta_json,
                    now, now, now, now, cooldown_until_val,
                ),
            )
            conn.commit()

            cursor.execute("SELECT * FROM monitoring_alerts WHERE id = ?", (alert_id,))
            return self._row_to_dict(cursor.fetchone())

        except Exception as e:
            conn.rollback()
            logger.error(f"Alert create/update failed: {e}")
            raise
        finally:
            conn.close()

    # ── Public: Lifecycle Actions ─────────────────────────────────────────

    def acknowledge_alert(self, alert_id: str, acknowledged_by: str = "operator") -> Dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        conn = get_connection(self._db_path)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM monitoring_alerts WHERE id = ?", (alert_id,))
            row = cursor.fetchone()
            if not row:
                raise AlertNotFoundError(f"Alert {alert_id} not found")

            current_status = row["status"]
            if current_status == "RESOLVED":
                raise InvalidAlertTransitionError("Cannot acknowledge a resolved alert")
            if current_status == "ACKNOWLEDGED":
                # Idempotent
                return self._row_to_dict(row)

            cursor.execute(
                """UPDATE monitoring_alerts
                   SET status = 'ACKNOWLEDGED', acknowledged_at = ?, acknowledged_by = ?, updated_at = ?
                   WHERE id = ?""",
                (now, acknowledged_by, now, alert_id),
            )
            conn.commit()
            cursor.execute("SELECT * FROM monitoring_alerts WHERE id = ?", (alert_id,))
            return self._row_to_dict(cursor.fetchone())
        finally:
            conn.close()

    def resolve_alert(self, alert_id: str) -> Dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        conn = get_connection(self._db_path)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM monitoring_alerts WHERE id = ?", (alert_id,))
            row = cursor.fetchone()
            if not row:
                raise AlertNotFoundError(f"Alert {alert_id} not found")

            if row["status"] == "RESOLVED":
                # Idempotent
                return self._row_to_dict(row)

            cursor.execute(
                """UPDATE monitoring_alerts
                   SET status = 'RESOLVED', resolved_at = ?, updated_at = ?
                   WHERE id = ?""",
                (now, now, alert_id),
            )
            conn.commit()
            cursor.execute("SELECT * FROM monitoring_alerts WHERE id = ?", (alert_id,))
            return self._row_to_dict(cursor.fetchone())
        finally:
            conn.close()

    # ── Public: Query ─────────────────────────────────────────────────────

    def get_alert(self, alert_id: str) -> Dict[str, Any]:
        conn = get_connection(self._db_path)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM monitoring_alerts WHERE id = ?", (alert_id,))
            row = cursor.fetchone()
            if not row:
                raise AlertNotFoundError(f"Alert {alert_id} not found")
            return self._row_to_dict(row)
        finally:
            conn.close()

    def list_alerts(
        self,
        status: Optional[str] = None,
        severity: Optional[str] = None,
        category: Optional[str] = None,
        source: Optional[str] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        conn = get_connection(self._db_path)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.cursor()
            conditions = []
            params: list = []

            if status:
                conditions.append("status = ?")
                params.append(status)
            if severity:
                conditions.append("severity = ?")
                params.append(severity)
            if category:
                conditions.append("category = ?")
                params.append(category)
            if source:
                conditions.append("source = ?")
                params.append(source)
            if since:
                conditions.append("created_at >= ?")
                params.append(since)
            if until:
                conditions.append("created_at <= ?")
                params.append(until)

            where = ""
            if conditions:
                where = "WHERE " + " AND ".join(conditions)

            # Count
            cursor.execute(f"SELECT COUNT(*) as cnt FROM monitoring_alerts {where}", params)
            total = cursor.fetchone()["cnt"]

            # Fetch
            cursor.execute(
                f"""SELECT * FROM monitoring_alerts {where}
                    ORDER BY
                        CASE severity WHEN 'CRITICAL' THEN 0 WHEN 'WARNING' THEN 1 ELSE 2 END,
                        last_detected_at DESC
                    LIMIT ? OFFSET ?""",
                params + [limit, offset],
            )
            rows = [self._row_to_dict(r) for r in cursor.fetchall()]

            return {"alerts": rows, "total": total, "limit": limit, "offset": offset}
        finally:
            conn.close()

    def get_alert_counts(self) -> Dict[str, int]:
        conn = get_connection(self._db_path)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'OPEN' THEN 1 ELSE 0 END) as open_count,
                    SUM(CASE WHEN status = 'ACKNOWLEDGED' THEN 1 ELSE 0 END) as acknowledged_count,
                    SUM(CASE WHEN status = 'RESOLVED' THEN 1 ELSE 0 END) as resolved_count,
                    SUM(CASE WHEN severity = 'CRITICAL' AND status != 'RESOLVED' THEN 1 ELSE 0 END) as critical_active,
                    SUM(CASE WHEN severity = 'WARNING' AND status != 'RESOLVED' THEN 1 ELSE 0 END) as warning_active
                FROM monitoring_alerts
            """)
            row = cursor.fetchone()
            return {
                "total": row["total"] or 0,
                "open": row["open_count"] or 0,
                "acknowledged": row["acknowledged_count"] or 0,
                "resolved": row["resolved_count"] or 0,
                "critical_active": row["critical_active"] or 0,
                "warning_active": row["warning_active"] or 0,
            }
        finally:
            conn.close()

    # ── Private Helpers ───────────────────────────────────────────────────

    @staticmethod
    def _make_dedup_key(alert_type: str, source: str, category: str,
                        entity_type: Optional[str], entity_id: Optional[str],
                        metric_name: Optional[str]) -> str:
        parts = [alert_type, source, category]
        if entity_type:
            parts.append(entity_type)
        if entity_id:
            parts.append(entity_id)
        if metric_name:
            parts.append(metric_name)
        return "|".join(parts)

    def _calculate_cooldown(self, category: str, now_iso: str) -> str:
        seconds = self._cooldowns.get(category, 60)
        now_dt = datetime.fromisoformat(now_iso.replace("Z", "+00:00")) if "Z" in now_iso else datetime.fromisoformat(now_iso)
        return (now_dt + timedelta(seconds=seconds)).isoformat()

    @staticmethod
    def _row_to_dict(row) -> Dict[str, Any]:
        if row is None:
            return {}
        d = dict(row)
        # Parse metadata JSON
        if d.get("metadata"):
            try:
                d["metadata"] = json.loads(d["metadata"])
            except (json.JSONDecodeError, TypeError):
                pass
        return d
