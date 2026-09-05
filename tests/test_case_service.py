"""
Unit tests for CaseService layer.
Tests state machine transitions, optimistic concurrency locks (versioning),
idempotency, SLA calculations, and audit timeline tracking.
"""
import os
import tempfile
import pytest
from api.case_service import (
    CaseService,
    InvalidStateTransitionError,
    ConcurrencyConflictError,
)
from database.migrations import run_migrations


@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    run_migrations(db_path=path)
    yield path
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture
def case_service(temp_db):
    return CaseService(db_path=temp_db)


def test_create_case_idempotent(case_service):
    decision_snap = {"final_decision": "REVIEW", "base_decision": "REVIEW"}
    risk_snap = {"fraud_probability": 0.18, "model_risk_level": "MEDIUM"}
    rule_snap = {"triggered_rules": [{"rule_id": "HIGH_VALUE_TRANSACTION"}]}

    c1 = case_service.create_case(
        transaction_id="txn_001",
        assessment_id="asmt_001",
        final_decision="REVIEW",
        decision_reason="High value transaction",
        decision_snapshot=decision_snap,
        risk_snapshot=risk_snap,
        rule_snapshot=rule_snap,
        priority_override="HIGH",
    )
    assert c1["case_id"].startswith("case_")
    assert c1["status"] == "OPEN"
    assert c1["priority"] == "HIGH"
    assert c1["version"] == 1

    # Second creation with same transaction_id & assessment_id must return existing case
    c2 = case_service.create_case(
        transaction_id="txn_001",
        assessment_id="asmt_001",
        final_decision="REVIEW",
        decision_reason="Different reason",
        decision_snapshot=decision_snap,
        risk_snapshot=risk_snap,
        rule_snapshot=rule_snap,
    )
    assert c2["case_id"] == c1["case_id"]
    assert c2["version"] == 1


def test_valid_state_machine_transitions(case_service):
    c = case_service.create_case(
        transaction_id="txn_002",
        assessment_id="asmt_002",
        final_decision="STEP_UP",
        decision_reason="Suspicious velocity",
        decision_snapshot={},
        risk_snapshot={},
        rule_snapshot={},
    )
    case_id = c["case_id"]
    assert c["status"] == "OPEN"
    assert c["version"] == 1

    # 1. OPEN -> INVESTIGATING
    c_inv = case_service.start_investigation(case_id, actor="analyst_1", expected_version=1)
    assert c_inv["status"] == "INVESTIGATING"
    assert c_inv["version"] == 2

    # 2. INVESTIGATING -> ESCALATED
    c_esc = case_service.escalate_case(case_id, escalation_reason="Need Tier 2 review", actor="analyst_1", expected_version=2)
    assert c_esc["status"] == "ESCALATED"
    assert c_esc["version"] == 3
    assert c_esc["escalation_reason"] == "Need Tier 2 review"

    # 3. ESCALATED -> INVESTIGATING
    c_inv2 = case_service.start_investigation(case_id, actor="lead_analyst", expected_version=3)
    assert c_inv2["status"] == "INVESTIGATING"
    assert c_inv2["version"] == 4

    # 4. INVESTIGATING -> RESOLVED
    c_res = case_service.resolve_case(
        case_id=case_id,
        resolution_type="CONFIRMED_FRAUD",
        resolution_notes="Customer confirmed unauthorized charge",
        actor="lead_analyst",
        expected_version=4,
    )
    assert c_res["status"] == "RESOLVED"
    assert c_res["version"] == 5
    assert c_res["resolution_type"] == "CONFIRMED_FRAUD"
    assert c_res["resolved_at"] is not None


def test_invalid_state_machine_transitions(case_service):
    c = case_service.create_case(
        transaction_id="txn_003",
        assessment_id="asmt_003",
        final_decision="REVIEW",
        decision_reason="Test invalid transitions",
        decision_snapshot={},
        risk_snapshot={},
        rule_snapshot={},
    )
    case_id = c["case_id"]

    # OPEN cannot transition directly to ESCALATED
    with pytest.raises(InvalidStateTransitionError):
        case_service.escalate_case(case_id, escalation_reason="Cannot jump to escalate", actor="analyst_1", expected_version=1)

    # Resolve directly from OPEN is allowed
    c_res = case_service.resolve_case(
        case_id=case_id,
        resolution_type="CONFIRMED_LEGITIMATE",
        actor="analyst_1",
        expected_version=1,
    )
    assert c_res["status"] == "RESOLVED"

    # Once RESOLVED, cannot transition to any other status
    with pytest.raises(InvalidStateTransitionError):
        case_service.start_investigation(case_id, actor="analyst_1", expected_version=c_res["version"])

    with pytest.raises(InvalidStateTransitionError):
        case_service.resolve_case(
            case_id=case_id,
            resolution_type="DUPLICATE",
            actor="analyst_1",
            expected_version=c_res["version"],
        )


def test_optimistic_concurrency_conflict(case_service):
    c = case_service.create_case(
        transaction_id="txn_004",
        assessment_id="asmt_004",
        final_decision="REVIEW",
        decision_reason="Concurrency test",
        decision_snapshot={},
        risk_snapshot={},
        rule_snapshot={},
    )
    case_id = c["case_id"]

    # Pass outdated expected_version
    with pytest.raises(ConcurrencyConflictError):
        case_service.start_investigation(case_id, actor="analyst_1", expected_version=999)

    # Valid update
    case_service.start_investigation(case_id, actor="analyst_1", expected_version=1)

    # Stale version 1 used again
    with pytest.raises(ConcurrencyConflictError):
        case_service.assign_case(case_id, assigned_to="analyst_2", actor="supervisor", expected_version=1)


def test_audit_event_logging(case_service):
    c = case_service.create_case(
        transaction_id="txn_005",
        assessment_id="asmt_005",
        final_decision="REVIEW",
        decision_reason="Audit test",
        decision_snapshot={},
        risk_snapshot={},
        rule_snapshot={},
    )
    case_id = c["case_id"]

    case_service.assign_case(case_id, assigned_to="agent_smith", actor="dispatcher", expected_version=1)
    case_service.start_investigation(case_id, actor="agent_smith", expected_version=2)
    case_service.resolve_case(case_id, resolution_type="CONFIRMED_LEGITIMATE", actor="agent_smith", expected_version=3)

    events = case_service.get_case_events(case_id)
    assert len(events) == 4

    types = [e["event_type"] for e in events]
    assert types == ["CASE_CREATED", "CASE_ASSIGNED", "INVESTIGATION_STARTED", "CASE_RESOLVED"]

    assert events[0]["new_state"] == "OPEN"
    assert events[1]["metadata"]["assigned_to"] == "agent_smith"
    assert events[2]["previous_state"] == "OPEN"
    assert events[2]["new_state"] == "INVESTIGATING"
    assert events[3]["previous_state"] == "INVESTIGATING"
    assert events[3]["new_state"] == "RESOLVED"
    assert events[3]["metadata"]["resolution_type"] == "CONFIRMED_LEGITIMATE"


def test_list_cases_filtering_and_stats(case_service):
    for i in range(5):
        case_service.create_case(
            transaction_id=f"txn_list_{i}",
            assessment_id=f"asmt_list_{i}",
            final_decision="REVIEW" if i < 3 else "STEP_UP",
            decision_reason=f"Reason {i}",
            decision_snapshot={},
            risk_snapshot={},
            rule_snapshot={},
            priority_override="CRITICAL" if i == 0 else "MEDIUM",
        )

    res = case_service.list_cases(page=1, page_size=10)
    assert res["pagination"]["total_items"] == 5
    assert res["stats"]["open_cases"] == 5
    assert res["stats"]["high_critical_open"] == 1

    # Filter by priority
    res_crit = case_service.list_cases(priority="CRITICAL")
    assert len(res_crit["items"]) == 1
    assert res_crit["items"][0]["transaction_id"] == "txn_list_0"

    # Filter by search
    res_search = case_service.list_cases(search="txn_list_2")
    assert len(res_search["items"]) == 1
    assert res_search["items"][0]["transaction_id"] == "txn_list_2"
