-- Migration: 008_investigation_cases
-- Description: Creates investigation_cases and case_events tables for transaction lifecycle management.

CREATE TABLE IF NOT EXISTS investigation_cases (
    case_id TEXT PRIMARY KEY,
    transaction_id TEXT NOT NULL,
    assessment_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'OPEN',
    priority TEXT NOT NULL DEFAULT 'MEDIUM',
    assigned_to TEXT,
    resolution_type TEXT,
    resolution_notes TEXT,
    escalation_reason TEXT,
    case_policy_version TEXT NOT NULL DEFAULT '1.0',
    created_from_decision TEXT NOT NULL,
    created_from_reason TEXT NOT NULL,
    decision_snapshot TEXT NOT NULL,
    risk_snapshot TEXT NOT NULL,
    rule_snapshot TEXT NOT NULL,
    audit_metadata TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    resolved_at TEXT,
    UNIQUE(transaction_id, assessment_id)
);

CREATE INDEX IF NOT EXISTS idx_cases_status ON investigation_cases(status);
CREATE INDEX IF NOT EXISTS idx_cases_priority ON investigation_cases(priority);
CREATE INDEX IF NOT EXISTS idx_cases_assigned_to ON investigation_cases(assigned_to);
CREATE INDEX IF NOT EXISTS idx_cases_transaction_id ON investigation_cases(transaction_id);
CREATE INDEX IF NOT EXISTS idx_cases_created_at ON investigation_cases(created_at);

CREATE TABLE IF NOT EXISTS case_events (
    event_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    previous_state TEXT,
    new_state TEXT,
    actor TEXT NOT NULL DEFAULT 'SYSTEM',
    metadata TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(case_id) REFERENCES investigation_cases(case_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_case_events_case_id ON case_events(case_id);
CREATE INDEX IF NOT EXISTS idx_case_events_created_at ON case_events(created_at);
