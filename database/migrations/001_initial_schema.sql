-- Migration: 001_initial_schema
-- Description: Creates the baseline tables for RazorBrain audit and persistence.

CREATE TABLE migrations (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE transactions (
    transaction_id TEXT PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL,
    amount REAL,
    customer_id TEXT,
    merchant_id TEXT,
    context_data TEXT -- JSON
);

CREATE TABLE risk_assessments (
    assessment_id TEXT PRIMARY KEY,
    transaction_id TEXT NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    primary_risk_probability REAL,
    confidence_in_probability TEXT,
    model_metadata TEXT, -- JSON
    FOREIGN KEY(transaction_id) REFERENCES transactions(transaction_id)
);
CREATE INDEX idx_risk_assessments_tx_id ON risk_assessments(transaction_id);
CREATE INDEX idx_risk_assessments_ts ON risk_assessments(timestamp);

CREATE TABLE decisions (
    assessment_id TEXT PRIMARY KEY,
    decision TEXT NOT NULL,
    decision_reason TEXT,
    blocking_guardrail_status TEXT,
    policy_metadata TEXT, -- JSON
    FOREIGN KEY(assessment_id) REFERENCES risk_assessments(assessment_id)
);

CREATE TABLE rule_evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    assessment_id TEXT NOT NULL,
    rule_id TEXT NOT NULL,
    severity TEXT NOT NULL,
    FOREIGN KEY(assessment_id) REFERENCES risk_assessments(assessment_id)
);
CREATE INDEX idx_rule_evidence_assessment ON rule_evidence(assessment_id);

CREATE TABLE model_evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    assessment_id TEXT NOT NULL,
    feature_name TEXT NOT NULL,
    shap_contribution REAL NOT NULL,
    FOREIGN KEY(assessment_id) REFERENCES risk_assessments(assessment_id)
);
CREATE INDEX idx_model_evidence_assessment ON model_evidence(assessment_id);

CREATE TABLE explanations (
    assessment_id TEXT PRIMARY KEY,
    explanation_text TEXT NOT NULL,
    provider TEXT NOT NULL,
    grounded BOOLEAN NOT NULL,
    limitations TEXT, -- JSON
    generation_timestamp TIMESTAMP NOT NULL,
    FOREIGN KEY(assessment_id) REFERENCES risk_assessments(assessment_id)
);
