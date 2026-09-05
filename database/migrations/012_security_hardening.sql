-- Migration: 012_security_hardening
-- Description: API Key management, idempotency tracking

CREATE TABLE IF NOT EXISTS api_keys (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    key_hash TEXT UNIQUE NOT NULL,
    prefix TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'SCORER', -- ADMIN, OPERATOR, SCORER
    status TEXT NOT NULL DEFAULT 'ACTIVE', -- ACTIVE, REVOKED, EXPIRED
    created_at TEXT NOT NULL,
    expires_at TEXT,
    last_used_at TEXT,
    revoked_at TEXT
);

CREATE TABLE IF NOT EXISTS idempotency_keys (
    idempotency_key TEXT PRIMARY KEY,
    request_payload_hash TEXT NOT NULL,
    response_payload TEXT NOT NULL,
    status_code INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

-- We don't automatically insert the fallback env key here, 
-- but we rely on the service to fall back to ENV if the table is empty.
