-- Real-Time Event Ledger for Idempotency
-- Allows tracking event_id uniqueness separately from assessment_id
CREATE TABLE IF NOT EXISTS processed_events (
    event_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    assessment_id TEXT,
    correlation_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
