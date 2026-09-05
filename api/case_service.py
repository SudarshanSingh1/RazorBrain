"""
Case Service Layer for RazorBrain Investigation Case Management.

Enforces deterministic state transitions, optimistic concurrency control,
immutable audit event logging, and idempotent case creation.
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import sqlite3
import uuid
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# State Machine Transition Rules
VALID_TRANSITIONS: Dict[str, List[str]] = {
    "OPEN": ["INVESTIGATING", "RESOLVED"],
    "INVESTIGATING": ["RESOLVED", "ESCALATED"],
    "ESCALATED": ["INVESTIGATING", "RESOLVED"],
    "RESOLVED": [],  # Terminal state
}

VALID_STATUSES = {"OPEN", "INVESTIGATING", "ESCALATED", "RESOLVED"}
VALID_PRIORITIES = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
VALID_RESOLUTIONS = {
    "CONFIRMED_FRAUD",
    "CONFIRMED_LEGITIMATE",
    "INCONCLUSIVE",
    "DUPLICATE",
    "OTHER",
}


class CaseServiceError(Exception):
    """Base exception for case service."""
    pass


class CaseNotFoundError(CaseServiceError):
    pass


class InvalidStateTransitionError(CaseServiceError):
    pass


class ConcurrencyConflictError(CaseServiceError):
    pass


class CasePolicy:
    """Loads case creation policy."""

    def __init__(self, policy_path: str = "data/razorpay_serving_case_policy_v1.json"):
        self.policy_path = policy_path
        self.policy_version = "1.0"
        self.auto_create_cases = True
        self.decision_case_mapping = {
            "APPROVE": False,
            "REVIEW": True,
            "STEP_UP": True,
            "DECLINE": False,
        }
        self.priority_mapping = {
            "REVIEW": "MEDIUM",
            "STEP_UP": "HIGH",
            "DECLINE": "CRITICAL",
        }
        self.high_amount_escalation_threshold = 1000000.0
        self.sla_hours = {
            "CRITICAL": 2,
            "HIGH": 6,
            "MEDIUM": 24,
            "LOW": 72,
        }
        self.allowed_resolution_types = list(VALID_RESOLUTIONS)
        self._load()

    def _load(self):
        if os.path.exists(self.policy_path):
            try:
                with open(self.policy_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.policy_version = data.get("policy_version", "1.0")
                self.auto_create_cases = data.get("auto_create_cases", True)
                self.decision_case_mapping = data.get("decision_case_mapping", self.decision_case_mapping)
                self.priority_mapping = data.get("priority_mapping", self.priority_mapping)
                self.high_amount_escalation_threshold = float(data.get("high_amount_escalation_threshold", 1000000.0))
                self.sla_hours = data.get("sla_hours", self.sla_hours)
            except Exception as e:
                logger.error(f"Failed to load case policy from {self.policy_path}: {e}")

    def should_create_case(self, final_decision: str) -> bool:
        if not self.auto_create_cases:
            return False
        return bool(self.decision_case_mapping.get(final_decision, False))

    def determine_priority(self, final_decision: str, amount: float = 0.0) -> str:
        if amount >= self.high_amount_escalation_threshold:
            return "CRITICAL"
        return self.priority_mapping.get(final_decision, "MEDIUM")

    def get_sla_deadline(self, priority: str, from_dt: Optional[datetime.datetime] = None) -> str:
        now = from_dt or datetime.datetime.now(datetime.timezone.utc)
        hours = self.sla_hours.get(priority, 24)
        deadline = now + datetime.timedelta(hours=hours)
        return deadline.isoformat()


class CaseService:
    """Manages transaction investigation cases and audit event trail."""

    def __init__(self, db_path: str = "razorbrain_api.db", policy: Optional[CasePolicy] = None):
        self.db_path = db_path
        self.policy = policy or CasePolicy()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def generate_case_id() -> str:
        date_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d")
        return f"case_{date_str}_{uuid.uuid4().hex[:12]}"

    @staticmethod
    def generate_event_id() -> str:
        return f"evt_{uuid.uuid4().hex[:14]}"

    def create_case(
        self,
        transaction_id: str,
        assessment_id: str,
        final_decision: str,
        decision_reason: str,
        decision_snapshot: Dict[str, Any],
        risk_snapshot: Dict[str, Any],
        rule_snapshot: Dict[str, Any],
        explanation_snapshot: Optional[Dict[str, Any]] = None,
        priority_override: Optional[str] = None,
        assigned_to: Optional[str] = None,
        actor: str = "SYSTEM",
    ) -> Dict[str, Any]:
        """
        Creates an investigation case idempotently.
        If a case already exists for (transaction_id, assessment_id), returns the existing case.
        """
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute(
                "SELECT * FROM investigation_cases WHERE transaction_id = ? AND assessment_id = ?",
                (transaction_id, assessment_id),
            )
            row = c.fetchone()
            if row:
                return dict(row)

            now = datetime.datetime.now(datetime.timezone.utc)
            now_iso = now.isoformat()
            amount = float(decision_snapshot.get("amount", 0.0) or 0.0)
            priority = priority_override or self.policy.determine_priority(final_decision, amount)
            if priority not in VALID_PRIORITIES:
                priority = "MEDIUM"

            case_id = self.generate_case_id()
            sla_deadline = self.policy.get_sla_deadline(priority, now)

            audit_meta = {
                "sla_deadline": sla_deadline,
                "created_by": actor,
            }

            try:
                c.execute(
                    """
                    INSERT INTO investigation_cases (
                        case_id, transaction_id, assessment_id, status, priority,
                        assigned_to, case_policy_version, created_from_decision,
                        created_from_reason, decision_snapshot, risk_snapshot,
                        rule_snapshot, explanation_snapshot, explanation_version, audit_metadata, version, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        case_id,
                        transaction_id,
                        assessment_id,
                        "OPEN",
                        priority,
                        assigned_to,
                        self.policy.policy_version,
                        final_decision,
                        decision_reason,
                        json.dumps(decision_snapshot),
                        json.dumps(risk_snapshot),
                        json.dumps(rule_snapshot),
                        json.dumps(explanation_snapshot) if explanation_snapshot else None,
                        "1.0" if explanation_snapshot else None,
                        json.dumps(audit_meta),
                        1,
                        now_iso,
                        now_iso,
                    ),
                )

                # Log creation event
                self._record_event(
                    conn=conn,
                    case_id=case_id,
                    event_type="CASE_CREATED",
                    previous_state=None,
                    new_state="OPEN",
                    actor=actor,
                    metadata={"priority": priority, "decision": final_decision},
                    created_at=now_iso,
                )

                conn.commit()
            except sqlite3.IntegrityError:
                # Concurrent insertion tie: fetch existing
                c.execute(
                    "SELECT * FROM investigation_cases WHERE transaction_id = ? AND assessment_id = ?",
                    (transaction_id, assessment_id),
                )
                row = c.fetchone()
                if row:
                    return dict(row)
                raise

            return self.get_case(case_id)

    def get_case(self, case_id: str) -> Dict[str, Any]:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM investigation_cases WHERE case_id = ?", (case_id,))
            row = c.fetchone()
            if not row:
                raise CaseNotFoundError(f"Case '{case_id}' not found.")
            data = dict(row)
            # Parse JSON snapshots safely
            for col in ["decision_snapshot", "risk_snapshot", "rule_snapshot", "explanation_snapshot", "audit_metadata"]:
                if data.get(col) and isinstance(data[col], str):
                    try:
                        data[col] = json.loads(data[col])
                    except Exception:
                        pass
            return data

    def get_case_events(self, case_id: str) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute(
                "SELECT * FROM case_events WHERE case_id = ? ORDER BY created_at ASC",
                (case_id,),
            )
            rows = c.fetchall()
            events = []
            for r in rows:
                item = dict(r)
                if item.get("metadata") and isinstance(item["metadata"], str):
                    try:
                        item["metadata"] = json.loads(item["metadata"])
                    except Exception:
                        pass
                events.append(item)
            return events

    def start_investigation(
        self,
        case_id: str,
        actor: str,
        expected_version: int,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self._transition_case(
            case_id=case_id,
            target_status="INVESTIGATING",
            event_type="INVESTIGATION_STARTED",
            actor=actor,
            expected_version=expected_version,
            metadata={"notes": notes} if notes else {},
        )

    def assign_case(
        self,
        case_id: str,
        assigned_to: str,
        actor: str,
        expected_version: int,
    ) -> Dict[str, Any]:
        if not assigned_to or not assigned_to.strip():
            raise CaseServiceError("Assignee cannot be empty.")

        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT status, version, assigned_to FROM investigation_cases WHERE case_id = ?", (case_id,))
            row = c.fetchone()
            if not row:
                raise CaseNotFoundError(f"Case '{case_id}' not found.")

            if row["version"] != expected_version:
                raise ConcurrencyConflictError(
                    f"Conflict updating case '{case_id}': expected version {expected_version} but found {row['version']}."
                )

            prev_assignee = row["assigned_to"]
            c.execute(
                """
                UPDATE investigation_cases
                SET assigned_to = ?, version = version + 1, updated_at = ?
                WHERE case_id = ? AND version = ?
                """,
                (assigned_to.strip(), now_iso, case_id, expected_version),
            )
            if c.rowcount == 0:
                raise ConcurrencyConflictError(f"Concurrent modification on case '{case_id}'.")

            self._record_event(
                conn=conn,
                case_id=case_id,
                event_type="CASE_ASSIGNED",
                previous_state=row["status"],
                new_state=row["status"],
                actor=actor,
                metadata={"previous_assigned_to": prev_assignee, "assigned_to": assigned_to.strip()},
                created_at=now_iso,
            )
            conn.commit()

        return self.get_case(case_id)

    def escalate_case(
        self,
        case_id: str,
        escalation_reason: str,
        actor: str,
        expected_version: int,
    ) -> Dict[str, Any]:
        if not escalation_reason or not escalation_reason.strip():
            raise CaseServiceError("Escalation reason is required.")

        return self._transition_case(
            case_id=case_id,
            target_status="ESCALATED",
            event_type="CASE_ESCALATED",
            actor=actor,
            expected_version=expected_version,
            escalation_reason=escalation_reason.strip(),
            new_priority="CRITICAL",
            metadata={"escalation_reason": escalation_reason.strip()},
        )

    def resolve_case(
        self,
        case_id: str,
        resolution_type: str,
        actor: str,
        expected_version: int,
        resolution_notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not resolution_type or resolution_type not in VALID_RESOLUTIONS:
            raise CaseServiceError(
                f"Invalid resolution_type '{resolution_type}'. Allowed: {sorted(VALID_RESOLUTIONS)}"
            )

        return self._transition_case(
            case_id=case_id,
            target_status="RESOLVED",
            event_type="CASE_RESOLVED",
            actor=actor,
            expected_version=expected_version,
            resolution_type=resolution_type,
            resolution_notes=resolution_notes.strip() if resolution_notes else None,
            metadata={
                "resolution_type": resolution_type,
                "resolution_notes": resolution_notes,
                "scientific_disclaimer": "Operational resolution only. Not automatically ML ground truth.",
            },
        )

    def _transition_case(
        self,
        case_id: str,
        target_status: str,
        event_type: str,
        actor: str,
        expected_version: int,
        escalation_reason: Optional[str] = None,
        resolution_type: Optional[str] = None,
        resolution_notes: Optional[str] = None,
        new_priority: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT status, version, priority FROM investigation_cases WHERE case_id = ?", (case_id,))
            row = c.fetchone()
            if not row:
                raise CaseNotFoundError(f"Case '{case_id}' not found.")

            current_status = row["status"]
            current_version = row["version"]

            if current_version != expected_version:
                raise ConcurrencyConflictError(
                    f"Conflict updating case '{case_id}': expected version {expected_version} but found {current_version}."
                )

            # Validate transition
            allowed = VALID_TRANSITIONS.get(current_status, [])
            if target_status not in allowed:
                raise InvalidStateTransitionError(
                    f"Cannot transition case '{case_id}' from '{current_status}' to '{target_status}'. "
                    f"Allowed transitions: {allowed or 'None (Terminal state)'}."
                )

            resolved_at_val = now_iso if target_status == "RESOLVED" else None
            priority_val = new_priority or row["priority"]

            c.execute(
                """
                UPDATE investigation_cases
                SET status = ?, priority = ?, escalation_reason = COALESCE(?, escalation_reason),
                    resolution_type = COALESCE(?, resolution_type),
                    resolution_notes = COALESCE(?, resolution_notes),
                    resolved_at = COALESCE(?, resolved_at),
                    version = version + 1, updated_at = ?
                WHERE case_id = ? AND version = ?
                """,
                (
                    target_status,
                    priority_val,
                    escalation_reason,
                    resolution_type,
                    resolution_notes,
                    resolved_at_val,
                    now_iso,
                    case_id,
                    expected_version,
                ),
            )
            if c.rowcount == 0:
                raise ConcurrencyConflictError(f"Concurrent modification on case '{case_id}'.")

            self._record_event(
                conn=conn,
                case_id=case_id,
                event_type=event_type,
                previous_state=current_status,
                new_state=target_status,
                actor=actor,
                metadata=metadata or {},
                created_at=now_iso,
            )
            conn.commit()

        return self.get_case(case_id)

    @staticmethod
    def _record_event(
        conn: sqlite3.Connection,
        case_id: str,
        event_type: str,
        previous_state: Optional[str],
        new_state: Optional[str],
        actor: str,
        metadata: Dict[str, Any],
        created_at: str,
    ) -> None:
        event_id = f"evt_{uuid.uuid4().hex[:14]}"
        conn.cursor().execute(
            """
            INSERT INTO case_events (event_id, case_id, event_type, previous_state, new_state, actor, metadata, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                case_id,
                event_type,
                previous_state,
                new_state,
                actor,
                json.dumps(metadata),
                created_at,
            ),
        )

    def list_cases(
        self,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        assigned_to: Optional[str] = None,
        search: Optional[str] = None,
        created_from: Optional[str] = None,
        created_to: Optional[str] = None,
        page: int = 1,
        page_size: int = 25,
        sort: str = "created_at",
        sort_direction: str = "desc",
    ) -> Dict[str, Any]:
        page = max(1, page)
        page_size = min(max(1, page_size), 100)

        allowed_sort_fields = {"created_at", "updated_at", "priority", "status", "case_id"}
        if sort not in allowed_sort_fields:
            sort = "created_at"
        sort_direction = "ASC" if sort_direction.lower() == "asc" else "DESC"

        where_clauses = ["1=1"]
        params: List[Any] = []

        if status and status in VALID_STATUSES:
            where_clauses.append("status = ?")
            params.append(status)

        if priority and priority in VALID_PRIORITIES:
            where_clauses.append("priority = ?")
            params.append(priority)

        if assigned_to:
            where_clauses.append("assigned_to = ?")
            params.append(assigned_to)

        if search and search.strip():
            term = f"%{search.strip()}%"
            where_clauses.append("(case_id LIKE ? OR transaction_id LIKE ?)")
            params.extend([term, term])

        if created_from:
            where_clauses.append("created_at >= ?")
            params.append(created_from)

        if created_to:
            where_clauses.append("created_at <= ?")
            params.append(created_to)

        where_sql = " AND ".join(where_clauses)

        with self._get_connection() as conn:
            c = conn.cursor()
            # Count
            c.execute(f"SELECT COUNT(*) FROM investigation_cases WHERE {where_sql}", params)
            total_items = c.fetchone()[0]

            total_pages = (total_items + page_size - 1) // page_size if total_items > 0 else 1
            offset = (page - 1) * page_size

            # Items query
            c.execute(
                f"""
                SELECT case_id, transaction_id, assessment_id, status, priority,
                       assigned_to, created_from_decision, created_from_reason,
                       version, created_at, updated_at, resolved_at, audit_metadata
                FROM investigation_cases
                WHERE {where_sql}
                ORDER BY {sort} {sort_direction}
                LIMIT ? OFFSET ?
                """,
                params + [page_size, offset],
            )
            rows = c.fetchall()
            items = []
            for r in rows:
                item = dict(r)
                if item.get("audit_metadata") and isinstance(item["audit_metadata"], str):
                    try:
                        item["audit_metadata"] = json.loads(item["audit_metadata"])
                    except Exception:
                        pass
                items.append(item)

            # Summary metrics for quick dashboard display
            c.execute("SELECT status, COUNT(*) FROM investigation_cases GROUP BY status")
            status_counts = dict(c.fetchall())

            c.execute("SELECT priority, COUNT(*) FROM investigation_cases WHERE status != 'RESOLVED' GROUP BY priority")
            priority_counts = dict(c.fetchall())

            today_utc = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
            c.execute("SELECT COUNT(*) FROM investigation_cases WHERE status = 'RESOLVED' AND resolved_at LIKE ?", (f"{today_utc}%",))
            resolved_today = c.fetchone()[0]

            return {
                "items": items,
                "pagination": {
                    "page": page,
                    "page_size": page_size,
                    "total_items": total_items,
                    "total_pages": total_pages,
                },
                "stats": {
                    "open_cases": status_counts.get("OPEN", 0),
                    "investigating_cases": status_counts.get("INVESTIGATING", 0),
                    "escalated_cases": status_counts.get("ESCALATED", 0),
                    "resolved_cases": status_counts.get("RESOLVED", 0),
                    "high_critical_open": priority_counts.get("HIGH", 0) + priority_counts.get("CRITICAL", 0),
                    "resolved_today": resolved_today,
                },
            }
