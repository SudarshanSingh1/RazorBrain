import pytest
import sqlite3
import tempfile
import os
from datetime import datetime, timezone

from database.migrations import run_migrations
from api.alert_service import AlertService, InvalidAlertTransitionError
from api.monitoring_service import MonitoringService
from api.metrics_service import MetricsCollector
from fastapi.testclient import TestClient
from api.app import app


@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    
    # Run migrations
    run_migrations(db_path=path)
    
    yield path
    os.remove(path)

@pytest.fixture
def alert_service(temp_db):
    return AlertService(db_path=temp_db)

@pytest.fixture
def monitoring_service(temp_db):
    return MonitoringService(db_path=temp_db)

@pytest.fixture
def metrics_collector(temp_db):
    return MetricsCollector(db_path=temp_db)

# ── Alert Service Tests ───────────────────────────────────────────────────────

def test_create_alert(alert_service):
    alert = alert_service.create_or_update_alert(
        alert_type="TEST_ALERT",
        severity="WARNING",
        category="SYSTEM",
        title="Test Title",
        message="Test Message"
    )
    assert alert["id"] is not None
    assert alert["status"] == "OPEN"
    assert alert["severity"] == "WARNING"
    assert alert["occurrence_count"] == 1

def test_alert_deduplication(alert_service):
    a1 = alert_service.create_or_update_alert(
        alert_type="TEST_ALERT", severity="WARNING", category="SYSTEM",
        title="T1", message="M1", deduplication_key="dedup_1"
    )
    a2 = alert_service.create_or_update_alert(
        alert_type="TEST_ALERT", severity="CRITICAL", category="SYSTEM",
        title="T2", message="M2", deduplication_key="dedup_1"
    )
    assert a1["id"] == a2["id"]
    assert a2["occurrence_count"] == 2

def test_acknowledge_alert(alert_service):
    a = alert_service.create_or_update_alert(
        alert_type="T", severity="INFO", category="SYSTEM", title="T", message="M"
    )
    ack = alert_service.acknowledge_alert(a["id"], acknowledged_by="user1")
    assert ack["status"] == "ACKNOWLEDGED"
    assert ack["acknowledged_by"] == "user1"

def test_resolve_alert(alert_service):
    a = alert_service.create_or_update_alert(
        alert_type="T", severity="INFO", category="SYSTEM", title="T", message="M"
    )
    res = alert_service.resolve_alert(a["id"])
    assert res["status"] == "RESOLVED"

def test_invalid_lifecycle(alert_service):
    a = alert_service.create_or_update_alert(
        alert_type="T", severity="INFO", category="SYSTEM", title="T", message="M"
    )
    alert_service.resolve_alert(a["id"])
    with pytest.raises(InvalidAlertTransitionError):
        alert_service.acknowledge_alert(a["id"])

def test_list_alerts(alert_service):
    alert_service.create_or_update_alert(alert_type="T1", severity="INFO", category="SYSTEM", title="T", message="M")
    alert_service.create_or_update_alert(alert_type="T2", severity="CRITICAL", category="FRAUD", title="T", message="M")
    
    res = alert_service.list_alerts(severity="CRITICAL")
    assert res["total"] == 1
    assert res["alerts"][0]["category"] == "FRAUD"

def test_alert_counts(alert_service):
    a1 = alert_service.create_or_update_alert(alert_type="T1", severity="WARNING", category="SYSTEM", title="T", message="M")
    alert_service.create_or_update_alert(alert_type="T2", severity="CRITICAL", category="SYSTEM", title="T", message="M")
    
    alert_service.resolve_alert(a1["id"])
    
    counts = alert_service.get_alert_counts()
    assert counts["total"] == 2
    assert counts["resolved"] == 1
    assert counts["open"] == 1
    assert counts["critical_active"] == 1
    assert counts["warning_active"] == 0

# ── Monitoring Service Tests ──────────────────────────────────────────────────

def test_evaluate_all_empty(monitoring_service):
    alerts = monitoring_service.evaluate_all()
    assert len(alerts) == 0

def test_queue_backlog_alert(temp_db, monitoring_service):
    # Insert dummy cases
    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()
    for i in range(51):
        cursor.execute("INSERT INTO investigation_cases (case_id, transaction_id, assessment_id, status, priority, created_from_decision, created_from_reason, decision_snapshot, risk_snapshot, rule_snapshot, created_at, updated_at) VALUES (?, ?, ?, 'OPEN', 'LOW', 'REVIEW', 'POLICY', '{}', '{}', '{}', ?, ?)", 
                       (f"c{i}", f"t{i}", f"a{i}", datetime.now(timezone.utc).isoformat(), datetime.now(timezone.utc).isoformat()))
    conn.commit()
    conn.close()
    
    alerts = monitoring_service.evaluate_all()
    queue_alerts = [a for a in alerts if a["alert_type"] == "REVIEW_QUEUE_BACKLOG"]
    assert len(queue_alerts) == 1
    assert queue_alerts[0]["metric_value"] == 51

# ── API Route Tests ───────────────────────────────────────────────────────────

def test_api_endpoints(temp_db, monkeypatch):
    monkeypatch.setenv("RAZORBRAIN_DB_PATH", temp_db)
    app.state.razor_state.db_path = temp_db
    
    with TestClient(app) as client:
        # Evaluate
        res = client.post("/monitoring/evaluate")
        assert res.status_code == 200
        
        # Summary
        res = client.get("/monitoring/summary")
        assert res.status_code == 200
        assert "system_health" in res.json()
        
        # Thresholds
        res = client.get("/monitoring/thresholds")
        assert res.status_code == 200
        assert "fraud_high_risk_rate" in res.json()["thresholds"]

        # Alerts
        res = client.get("/alerts")
        assert res.status_code == 200
