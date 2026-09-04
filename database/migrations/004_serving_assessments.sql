-- Migration: 004_serving_assessments
-- Description: Adds serving_assessments table for the Razorpay Serving Model decision track.
-- Preserves all existing tables. model_track distinguishes RAZORPAY_SERVING_MODEL from any
-- legacy assessments stored in risk_assessments.

CREATE TABLE IF NOT EXISTS serving_assessments (
    assessment_id       TEXT PRIMARY KEY,
    transaction_id      TEXT NOT NULL,
    event_id            TEXT,                   -- Razorpay event ID for idempotency
    assessment_type     TEXT NOT NULL DEFAULT 'POST_EVENT_RISK_ASSESSMENT',
    model_track         TEXT NOT NULL DEFAULT 'RAZORPAY_SERVING_MODEL',
    model_version       TEXT,
    calibration_version TEXT,
    policy_version      TEXT,
    timestamp           TEXT NOT NULL,
    risk                REAL,
    decision            TEXT NOT NULL,
    decision_reason     TEXT,                   -- JSON
    feature_snapshot    TEXT,                   -- JSON: {feature: value, ...}
    feature_availability TEXT,                 -- JSON: {feature: true/false, ...}
    shap_snapshot       TEXT,                   -- JSON: AVAILABLE or UNAVAILABLE envelope
    processing_status   TEXT NOT NULL DEFAULT 'COMPLETED',
    created_at          TEXT NOT NULL,
    FOREIGN KEY(transaction_id) REFERENCES transactions(transaction_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_serving_assessments_pk
    ON serving_assessments(assessment_id);

CREATE INDEX IF NOT EXISTS idx_serving_assessments_tid
    ON serving_assessments(transaction_id);

CREATE INDEX IF NOT EXISTS idx_serving_assessments_event
    ON serving_assessments(event_id)
    WHERE event_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_serving_assessments_ts
    ON serving_assessments(timestamp);
