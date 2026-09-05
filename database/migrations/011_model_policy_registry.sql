-- Migration: 011_model_policy_registry
-- Description: Adds Model and Policy registries for reproducible management.

CREATE TABLE IF NOT EXISTS model_registry (
    id TEXT PRIMARY KEY,
    model_name TEXT NOT NULL,
    model_version TEXT UNIQUE NOT NULL,
    status TEXT NOT NULL,
    artifact_path TEXT NOT NULL,
    artifact_checksum TEXT,
    feature_contract_version TEXT NOT NULL,
    model_type TEXT,
    calibration_version TEXT,
    training_metadata TEXT,
    description TEXT,
    created_at TEXT NOT NULL,
    activated_at TEXT,
    deactivated_at TEXT
);

CREATE TABLE IF NOT EXISTS policy_registry (
    id TEXT PRIMARY KEY,
    policy_name TEXT NOT NULL,
    policy_version TEXT UNIQUE NOT NULL,
    status TEXT NOT NULL,
    configuration TEXT NOT NULL,
    configuration_checksum TEXT,
    description TEXT,
    created_at TEXT NOT NULL,
    activated_at TEXT,
    deactivated_at TEXT
);

ALTER TABLE serving_assessments ADD COLUMN feature_contract_version TEXT;

-- Bootstrap initial legacy models if the tables are empty
INSERT OR IGNORE INTO model_registry (
    id, model_name, model_version, status, artifact_path, feature_contract_version, model_type, calibration_version, description, created_at, activated_at
) VALUES (
    'm-initial-legacy-v1',
    'Razorpay Serving Model',
    'fraud-model-v1',
    'ACTIVE',
    'data/razorpay_serving_model_calibrated.joblib',
    'feature-contract-v1',
    'xgboost',
    'isotonic-v1',
    'Initial legacy serving model ported to registry',
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
);

-- We need to inline the policy configuration for policy-v2
-- so we can bootstrap it directly.
INSERT OR IGNORE INTO policy_registry (
    id, policy_name, policy_version, status, configuration, description, created_at, activated_at
) VALUES (
    'p-initial-legacy-v2',
    'Razorpay Serving Policy',
    'policy-v2',
    'ACTIVE',
    '{"policy_version": "2.0", "thresholds": {"approve_max": 0.1213, "review_max": 0.1600, "step_up_max": 0.2053}, "hard_overrides": [{"condition": "amount > 500000", "force_decision": "REVIEW", "reason_code": "HIGH_VALUE_TRANSACTION"}, {"condition": "str(card_network).lower() == ''test''", "force_decision": "DECLINE", "reason_code": "TEST_CARD_NOT_ALLOWED"}, {"condition": "is_new_customer == 1 and txns_last_1h > 5", "force_decision": "STEP_UP", "reason_code": "HIGH_VELOCITY_NEW_CUSTOMER"}]}',
    'Initial legacy serving policy ported to registry',
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
);
