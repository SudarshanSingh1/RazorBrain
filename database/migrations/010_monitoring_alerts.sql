-- Migration: 010_monitoring_alerts
-- Description: Creates monitoring_alerts and monitoring_metrics tables for production monitoring and alerting.

CREATE TABLE IF NOT EXISTS monitoring_alerts (
    id TEXT PRIMARY KEY,
    alert_type TEXT NOT NULL,
    severity TEXT NOT NULL CHECK(severity IN ('INFO', 'WARNING', 'CRITICAL')),
    status TEXT NOT NULL DEFAULT 'OPEN' CHECK(status IN ('OPEN', 'ACKNOWLEDGED', 'RESOLVED')),
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'monitoring_service',
    metric_name TEXT,
    metric_value REAL,
    threshold REAL,
    deduplication_key TEXT NOT NULL,
    entity_type TEXT,
    entity_id TEXT,
    occurrence_count INTEGER NOT NULL DEFAULT 1,
    metadata TEXT,
    first_detected_at TEXT NOT NULL,
    last_detected_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    resolved_at TEXT,
    acknowledged_at TEXT,
    acknowledged_by TEXT,
    cooldown_until TEXT
);

CREATE INDEX IF NOT EXISTS idx_alerts_status ON monitoring_alerts(status);
CREATE INDEX IF NOT EXISTS idx_alerts_severity ON monitoring_alerts(severity);
CREATE INDEX IF NOT EXISTS idx_alerts_category ON monitoring_alerts(category);
CREATE INDEX IF NOT EXISTS idx_alerts_dedup_key ON monitoring_alerts(deduplication_key);
CREATE INDEX IF NOT EXISTS idx_alerts_created_at ON monitoring_alerts(created_at);
CREATE INDEX IF NOT EXISTS idx_alerts_source ON monitoring_alerts(source);

CREATE TABLE IF NOT EXISTS monitoring_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    metric_name TEXT NOT NULL,
    metric_value REAL NOT NULL,
    tags TEXT,
    recorded_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_metrics_name ON monitoring_metrics(metric_name);
CREATE INDEX IF NOT EXISTS idx_metrics_recorded_at ON monitoring_metrics(recorded_at);
CREATE INDEX IF NOT EXISTS idx_metrics_name_time ON monitoring_metrics(metric_name, recorded_at);
