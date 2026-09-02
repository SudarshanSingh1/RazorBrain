readme_content = """<div align="center">

<img src="https://upload.wikimedia.org/wikipedia/commons/8/89/Razorpay_logo.svg" width="300" alt="Razorpay Logo" />

<br />

# RazorBrain

<h3><strong>End-to-End AI Risk Management System for Real-Time Transaction Fraud Detection</strong></h3>

<sub>Track 02 — AI Risk Manager &nbsp;·&nbsp; AI Buildathon 2026</sub>

<br />

![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688?logo=fastapi)
![React](https://img.shields.io/badge/React-20+-61DAFB?logo=react)
![TypeScript](https://img.shields.io/badge/TypeScript-5.2+-3178C6?logo=typescript)
![scikit-learn](https://img.shields.io/badge/scikit--learn-1.3+-F7931E?logo=scikit-learn)
![SHAP](https://img.shields.io/badge/SHAP-Explainability-purple)
![SQLite](https://img.shields.io/badge/SQLite-Database-003B57?logo=sqlite)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker)
![pytest](https://img.shields.io/badge/pytest-218%20Passing-success)

</div>

---

## Table of Contents

- [Overview](#overview)
- [Why RazorBrain](#why-razorbrain)
- [Architecture](#architecture)
- [Transaction Risk Pipeline](#transaction-risk-pipeline)
- [Feature Engineering](#feature-engineering)
- [Machine Learning](#machine-learning)
- [Dataset and Split](#dataset-and-split)
- [Evaluation](#evaluation)
- [Calibration](#calibration)
- [SHAP / Explainability](#shap--explainability)
- [Rule Engine](#rule-engine)
- [Risk Fusion](#risk-fusion)
- [Decision Engine](#decision-engine)
- [Explanation Engine / Local AI](#explanation-engine--local-ai)
- [Database / Audit Trail](#database--audit-trail)
- [API](#api)
- [Enterprise Dashboard](#enterprise-dashboard)
- [Real-Time Event Processing](#real-time-event-processing)
- [Scalability and Load Validation](#scalability-and-load-validation)
- [Robustness and Edge Cases](#robustness-and-edge-cases)
- [Security](#security)
- [Docker Deployment](#docker-deployment)
- [Environment Variables](#environment-variables)
- [Project Structure](#project-structure)
- [Quick Start](#quick-start)
- [Testing](#testing)
- [Operational Research Applications](#operational-research-applications)
- [Safety Principles](#safety-principles)
- [Current Limitations](#current-limitations)
- [Implementation Status](#implementation-status)
- [Author](#author)

---

## Overview

RazorBrain is a defensive transaction fraud-risk manager that processes real-time transaction events through an evidence-aware pipeline. Instead of relying solely on an opaque probability score, RazorBrain grounds its output in calibrated evidence, deterministic rules, and model contributions (SHAP). 

The transaction lifecycle evaluates inputs through strict schema validation, temporal feature construction, Logistic Regression inference, probability calibration, and deterministic risk rules before fusing this evidence into a final confidence assessment. The outcome is funneled into the Decision Engine, resulting in one of three operational decisions: **ALLOW**, **REVIEW**, or **BLOCK**.

All events, assessments, explanations, and decisions are captured in an append-only audit trail designed for explainability, analyst efficiency, and operational scalability.

---

## Why RazorBrain

Fraud detection is rarely just a binary classification problem. Operational teams require a holistic system because:
- **Probability alone is insufficient**: A 90% probability means nothing if the confidence is low due to missing data.
- **Historical context matters**: Fraud is temporal. The sequence and velocity of transactions provide more signal than isolated events.
- **Missing data must be honest**: Data pipelines break. "Missing" must be represented as a conscious state rather than fabricating median values.
- **Explanations must be faithful**: Models must justify their outputs using actual feature evidence.
- **Review workload is expensive**: High-risk decisions need independent supporting evidence to avoid overwhelming human analysts.
- **Auditability is mandatory**: Financial decisions must be explainable months later.

---

## Architecture

```mermaid
flowchart LR
    A[Transaction/Event] --> B[FastAPI API]
    B --> C[Validation]
    C --> D[Feature Engineering]
    D --> E[Logistic Regression]
    E --> F[Probability Calibration]
    F --> G[SHAP Evidence]
    D --> H[Rule Engine]
    G --> I[Risk Fusion]
    H --> I
    I --> J[Decision Engine]
    J --> K[ALLOW]
    J --> L[REVIEW]
    J --> M[BLOCK]
    I --> N[Explanation Engine]
    J --> O[Audit Persistence]
    N --> O
    O --> P[Enterprise Dashboard]
```

---

## Transaction Risk Pipeline

```mermaid
flowchart TD
    1[Transaction Received] --> 2[Strict Schema Validation]
    2 --> 3[Temporal Feature Construction]
    3 --> 4[Trained Model Inference]
    4 --> 5[Calibrated Probability]
    5 --> 6[Model Evidence / SHAP]
    3 --> 7[Deterministic Rules]
    6 --> 8[Evidence Fusion]
    7 --> 8
    8 --> 9[Confidence Scoring]
    9 --> 10[Decision Guardrails]
    10 --> 11[Audit Persistence]
    11 --> 12[Explanation Generation]
    12 --> 13[API / Event Response]
```

Each stage operates deterministically, failing safely with explicit error semantics if anomalies occur.

---

## Feature Engineering

RazorBrain uses a canonical set of 21 time-aware features designed explicitly to prevent data leakage and handle cold-starts honestly. 

**Canonical Features:**
1. `amount`
2. `customer_account_age_days`
3. `previous_transaction_count`
4. `previous_fraud_count`
5. `avg_customer_amount`
6. `amount_deviation`
7. `is_new_customer`
8. `merchant_fraud_rate`
9. `is_new_merchant`
10. `txns_last_5min`
11. `txns_last_1h`
12. `txns_last_24h`
13. `new_device_flag`
14. `new_location_flag`
15. `ip_is_missing`
16. `location_is_missing`
17. `location_freq`
18. `payment_method_card`
19. `payment_method_bank_transfer`
20. `payment_method_wallet`
21. `payment_method_crypto`

**Important Properties:**
- Raw IDs (customer, merchant, transaction) and target labels are excluded from the model.
- Timestamps strictly enforce chronological ordering for historical aggregations.
- Historical features aggregate **PRIOR** rows only to prevent future-target leakage.
- Missing IP or location data is represented using explicit binary missingness signals.
- *Note: This was developed on a synthetic dataset and should not be confused with live production fraud data.*

---

## Machine Learning

The authoritative production model is a **Logistic Regression** baseline. 

**Configuration:**
- `class_weight="balanced"`
- `max_iter=1000`
- `random_state=42`
- `StandardScaler`
- 21 canonical features

*XGBoost was evaluated as a comparison model but underperformed the Logistic Regression baseline on the current synthetic validation dataset. Logistic Regression remains authoritative.*

---

## Dataset and Split

The underlying development dataset is entirely synthetic. 

**Total Population (90-day UTC period, chronologically sorted):**
- **Total Transactions:** 100,000 (~1,111 tx/day)
- **Legitimate:** 92,699
- **Fraud:** 7,301
- **Overall Fraud Rate:** 7.30%

**Time-Aware Split:**
- **TRAIN:** 70,000 (Fraud: 5,078, Rate: 7.25%)
- **VALIDATION:** 15,000 (Fraud: 1,129, Rate: 7.53%)
- **TEST:** 15,000 (Fraud: 1,094, Rate: 7.29%)

*The test set is rigorously protected from model fitting and threshold selection. No random cross-time shuffling is used.*

---

## Evaluation

Validation metrics measured at a 0.5 probability threshold during Phase 05/06:

**Logistic Regression (Authoritative Model)**
- **Precision:** 0.0845
- **Recall:** 0.5624
- **F1 Score:** 0.1469
- **PR-AUC:** 0.0915
- **ROC-AUC:** 0.5570

*Confusion Matrix (Validation):*
- TP: 635 | TN: 6,991 | FP: 6,880 | FN: 494
- FPR: 0.496 | FNR: 0.4376

**XGBoost (Comparison Model)**
- Configuration: 50 trees, depth 3, lr 0.1, subsample 0.8
- **Precision:** 0.0801 | **Recall:** 0.4668 | **F1 Score:** 0.1367
- **PR-AUC:** 0.0806 | **ROC-AUC:** 0.5122
- *Confusion Matrix:* TP: 527 | TN: 7,816 | FP: 6,055 | FN: 602

*(Note: These are validation metrics on the synthetic dataset, exhibiting notably poor precision, which drove the need for calibrated probabilities and strict decision guardrails).*

---

## Calibration

To make probability outputs operationally useful, **Isotonic calibration** was applied to the Logistic Regression model.

**Validation Results:**
- **Brier Score:** before 0.1652 → after 0.0694
- **Log Loss:** before 0.5255 → after 0.2655
- **Expected Calibration Error (ECE):** before 0.3540 → after 0.00088

*Limitation: Calibration was fitted using in-sample training predictions. These numbers represent validation quality for this synthetic setup, not proof of robust production-grade calibration.*

---

## SHAP / Explainability

Model decisions are explained using a SHAP `LinearExplainer`.

- SHAP contributions are evaluated in log-odds space.
- SHAP represents **model contribution**, NOT a risk score.
- SHAP is NOT added directly to probability and does NOT independently determine BLOCK/ALLOW.

**Global Mean Absolute SHAP Findings:**
- `previous_fraud_count`: 0.1838
- `previous_transaction_count`: 0.1347
- `amount`: 0.0539
- `new_device_flag`: 0.0380
- `amount_deviation`: 0.0311

---

## Rule Engine

Deterministic rules provide contextual risk evidence alongside the ML model.

**Current Rules:**
1. `velocity_new_device`
2. `deviation_new_location`
3. `missing_critical_context`
4. `repeated_fraud`
5. `risky_merchant_new_customer`
6. `extreme_amount_single_signal`

**Important Semantics:**
- Rule severity is **NOT** overall risk. A `HIGH` severity rule does not mean an 80/100 generic "risk score."
- Single weak signals cannot independently force a BLOCK.
- `repeated_fraud` is highly contextual and is NOT blocking-eligible by itself.
- Missing data results in rule evidence evaluating as `UNAVAILABLE`, rather than fabricating data.

*Validation Rule Evidence Frequencies:*
Total evidence generated: 15,841
- `repeated_fraud`: 14,896 *(Extremely common in this synthetic dataset; thus intentionally excluded from independent blocking)*
- `missing_critical_context`: 755
- `extreme_amount_single_signal`: 163
- `velocity_new_device`: 14
- `deviation_new_location`: 13
- `risky_merchant_new_customer`: 0

---

## Risk Fusion

Risk fusion preserves the semantic separation of evidence sources rather than collapsing them into a single score:
- Calibrated model probability
- Raw model probability
- SHAP contributions
- Deterministic rule evidence
- Evidence completeness
- Contextual severity & conflicts

Provenance is rigorously preserved so downstream decisions do not blindly double-count correlated evidence (e.g., SHAP vs Rules).

---

## Decision Engine

The Decision Engine applies operational thresholds to fused risk evidence to yield exactly one of three decisions:
**ALLOW** | **REVIEW** | **BLOCK**

**Validation Cost Policy:**
- Fraud ALLOWED = 500
- Fraud REVIEWED = 50
- Legitimate REVIEWED = 50
- Legitimate BLOCKED = 100

**Optimized Thresholds:**
- ALLOW threshold = 0.10
- BLOCK threshold = 0.40

**Validation Results:**
- **Legitimate:** ALLOW: 13,289 | REVIEW: 582 | BLOCK: 0
- **Fraud:** ALLOW: 1,050 | REVIEW: 79 | BLOCK: 0

**Important Limitation:**
Zero validation transactions met the current BLOCK conditions. The calibrated validation probabilities did not reach the 0.40 blocking threshold, and blocking strictly requires both confidence and blocking-eligible evidence. 
Fraud outcome distribution: **ALLOW = 93.00%**, **REVIEW = 7.00%**, **BLOCK = 0%**.

---

## Explanation Engine / Local AI

RazorBrain utilizes an explanation-provider abstraction, defaulting to a deterministic operational fallback.

**Guarantees:**
- Explanations are strictly read-only.
- Providers **cannot** modify probability, confidence, or decision.
- Providers **cannot** invent evidence (references must map to verified rule IDs).
- Forbidden concepts (fabricated risk scores, anomaly scores, percentage changes) are strictly filtered.
- Malformed/malicious provider output triggers a safe fallback.
- Prompt-injection defenses exist for the deterministic explanation path.

*(Note: The `LocalLLMProvider` interface exists but hard-fails by default. Live LLM inference is not currently executed.)*

---

## Database / Audit Trail

RazorBrain implements an **append-only audit persistence** layer via SQLite.

**Core Tables:**
- `migrations`
- `transactions`
- `risk_assessments`
- `decisions`
- `rule_evidence`
- `model_evidence`
- `explanations`

**Database Features:**
- Atomic assessment persistence.
- Foreign keys and indexing.
- Exact evidence preservation and paginated retrieval.
- *Note: This is an append-only application audit trail, NOT a cryptographically immutable ledger. Model hashes are not generated or verified.*

---

## API

RazorBrain exposes a strictly validated FastAPI boundary.

### Endpoints
- `POST /transactions/assess` (Synchronous assessment)
- `POST /transactions/events` (Asynchronous event ingestion returning HTTP 202)
- `GET /health` (Liveness)
- `GET /ready` (Readiness: ML and Migrations bootstrapped)
- `GET /dashboard/*` (Analytical aggregates)

**Semantics:**
- Pydantic models strictly forbid extra/unknown fields and explicitly reject target labels.
- Unauthenticated requests are rejected.
- Request IDs (`X-Request-ID`) provide cross-layer traceability.

---

## Enterprise Dashboard

The React + TypeScript + Vite frontend visualizes the audit trail and risk intelligence.

**Pages:**
- Overview
- Risk Analytics
- Transactions
- Review Queue
- Audit Trail
- Transaction Detail

**Intelligence Panels:**
- Decision trends and volume
- Probability distribution (Amount vs. Probability)
- Rule intelligence and SHAP model contributions
- Evidence completeness (`FULL`, `PARTIAL`, `LIMITED`, `UNAVAILABLE`)

---

## Real-Time Event Processing

Event processing handles asynchronous ingestion with explicit failure boundaries.

**Event Lifecycle:**
`RECEIVED` → `VALIDATED` → `PROCESSING` → `ASSESSED` → `PERSISTED` → `PUBLISHED`

**Semantics & Idempotency:**
- Bounded in-memory event broker (max queue size: 1000).
- **Event Idempotency:** Duplicate `event_id` submissions are rejected completely to prevent reprocessing.
- **Assessment Uniqueness:** Distinct events generating the same assessment trigger a `DUPLICATE_ASSESSMENT` failure state, preserving the initial success.
- **Persistence Boundary:** If persistence succeeds but publication fails, the event safely remains `PERSISTED` and does not revert to a false failure state.
- **Crash Recovery:** A server crash leaves active events in `PROCESSING`. On restart, they are gracefully reconciled to `PROCESSING_FAILED`. 
- **Limitation:** In-memory queued events are permanently lost during a process crash. Publication is at-most-once. Exactly-once delivery is NOT claimed.

---

## Scalability and Load Validation

Phase 17 validated application behavior under severe asynchronous overload (100K event burst at 100 concurrent clients).

**Observations:**
- **Arrival Rate (Burst):** ~1,204 RPS
- **Accepted:** 1,999 events (HTTP 202)
- **Backpressure Rejected:** 98,001 events (HTTP 503)
- **Processed & Persisted:** 1,999 events (0 processing failures)
- **Observed Service Rate:** ~90.7 events/second

**Conclusion:** 
The bounded queue successfully protects the system from Out-of-Memory (OOM) crashes by shedding load via HTTP 503 backpressure. Burst arrival exceeded observed CPU service capacity by ~13×. This test demonstrates robust survival under overload, **NOT** a capacity to successfully service 100K concurrent throughput.

*Selected component timings (measured locally):*
Feature construction: ~7.49ms | Fusion: ~1.34ms | Transform: ~0.72ms | LR Inference: ~0.61ms | Calibration: ~0.45ms | SHAP: ~0.38ms | Rules: ~0.06ms | DB Persistence: ~0.06ms | Decision: ~0.01ms.

---

## Robustness and Edge Cases

Phase 16 executed comprehensive robustness testing including:
- Boundary input values (extreme amounts capped safely at 1e15).
- Missing values (IP/location).
- Explanation timeout/failures.
- Missing critical context and cold starts.
- Duplicate/retry behavior testing.
- Unhandled API failures and traceback leak prevention.

---

## Security

RazorBrain enforces defensive engineering across boundaries:
- **API Key Authentication** protecting business logic.
- **Strict Pydantic Validation** (identifiers max length 100, bounded floats).
- **Parameterized SQLite** preventing SQL injection.
- **Prompt-Injection Safeguards** isolating the model decision from untrusted explanation text.
- **Global Error Handlers** preventing raw Python traceback leakage.
- **Security Headers** (`X-Content-Type-Options`, `X-Frame-Options`).
- **Secrets Management** (`.env` ignored, repository scanned).

*See [Current Limitations](#current-limitations) for security boundaries not yet implemented.*

---

## Docker Deployment

RazorBrain supports reproducible local deployment via Docker Compose.

**Architecture:**
- **Backend:** `python:3.11-slim`, running Uvicorn on port 8000 as a non-root `appuser`. Persists state to a mounted SQLite volume.
- **Frontend:** Multi-stage Node 20 Alpine build serving static files via `nginx:alpine` on port 80 (mapped to 8080).
- **Compose:** Defines `backend`, `frontend`, explicit dependencies, and healthchecks validating `/ready`.

*(Note: Docker images and Compose startup were conditionally validated; final host validation requires a live Docker daemon).*

---

## Environment Variables

| Variable | Description |
|---|---|
| `RAZORBRAIN_API_KEY` | Server-side authentication key required for API access. |
| `RAZORBRAIN_CORS_ORIGINS` | Comma-separated CORS origins (defaults to `*` for dev). |
| `RAZORBRAIN_DB_PATH` | Path to SQLite database file. |
| `VITE_API_KEY` | **Client Credential** baked into the frontend to authenticate with the API. |
| `VITE_API_URL` | Base URL used by the frontend to contact the API backend. |

---

## Project Structure

```text
razorbrain/
├── api/             # FastAPI application, routes, schemas, lifecycle, and event processor
├── backend/         # Utility module aliases
├── data/            # Synthetic data generation and preprocessing logic
├── database/        # SQLite schema migrations, connection pooling, and append-only repository
├── evaluation/      # Model performance analysis and baseline comparisons
├── frontend/        # React + TypeScript + Vite Enterprise Dashboard
├── model/           # ML pipeline: features, rules, fusion, calibration, and explainability
├── scratch/         # Sandbox scripts and local evaluation runner utilities
├── tests/           # 218 automated pytest regression and security boundary tests
├── Dockerfile.backend
├── Dockerfile.frontend
├── compose.yaml
├── pyproject.toml
└── README.md
```

---

## Quick Start

### Local Development
```bash
# 1. Clone and setup environment
python -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -e .[dev]

# 3. Configure environment
cp .env.example .env
# Edit .env to set your RAZORBRAIN_API_KEY

# 4. Start Backend
uvicorn api.app:app --reload --port 8000

# 5. Start Frontend
cd frontend
npm install
npm run dev
```

### Docker Deployment
```bash
cp .env.example .env
docker compose up -d --build
```
- API: `http://localhost:8000`
- Dashboard: `http://localhost:8080`

---

## Testing

RazorBrain is validated by a rigorous test suite.
- **Backend:** 218 passing `pytest` tests validating robustness, edge cases, real-time queues, and security boundaries.
- **Frontend:** Standard `npm run build` succeeds cleanly.

Run backend tests:
```bash
pytest -q tests/
```

---

## Operational Research Applications

RazorBrain integrates Operational Research (OR) principles to solve real-world decision bottlenecks.
- **Currently Implemented:** Business-cost optimization for decision thresholds (minimizing false positive friction while capturing high-value fraud).
- **Future Applications:** Review queue capacity planning, queueing analysis, workload simulation, and multi-objective Pareto analysis for analyst allocation.

---

## Safety Principles

RazorBrain is designed strictly for defensive transaction analysis.
- **Defense-only:** Contains no offensive security tooling, credential theft, or attack automation.
- **Synthetic Data:** Developed entirely on synthetically generated transactions.
- **Architectural Isolation:** Explanations (LLM or deterministic) cannot override the decision engine.
- **Honest Constraints:** Missing evidence is explicitly logged as `UNAVAILABLE`. No fake metrics or probabilities are fabricated.

---

## Current Limitations

RazorBrain embraces transparency. The following limitations are documented explicitly:

1. **Synthetic dataset:** The ML performance and rules reflect a synthetic development environment.
2. **Modest ML performance:** Current Logistic Regression precision is low.
3. **Zero BLOCK decisions:** The current validation policy produced zero BLOCK decisions due to conservative confidence thresholds.
4. **Calibration leakage:** Isotonic calibration currently utilizes in-sample training predictions.
5. **SQLite Scaling:** SQLite serves as a robust prototype persistence layer but lacks distributed concurrency.
6. **Queue Payload Loss:** The in-memory event queue permanently loses unprocessed payloads if the container crashes.
7. **At-Most-Once Publication:** Exactly-once event delivery is NOT implemented.
8. **RBAC:** Granular Role-Based Access Control is not implemented.
9. **Client Credentials:** `VITE_API_KEY` is browser-visible, acting as a client credential rather than a secret.
10. **Audit Immutability:** The database is append-only, but cryptographic immutability (hashing) is not implemented.
11. **Scalability Ceiling:** Phase 17 validated backpressure survival under overload, NOT 100K successful concurrent throughput.
12. **Docker Validation:** Final `docker-compose up` validation was performed statically due to sandbox environment constraints.
13. **Model Verification:** Cryptographic integrity verification of model artifacts is not implemented.

---

## Implementation Status

| Phase | Status | Notes |
|---|---|---|
| Repository + README Foundation | Complete | |
| Data Contract + Validation Foundation | Complete | |
| Synthetic Dataset + 100K Quality Gate | Complete | |
| Time-Aware Feature Engineering + Temporal Split | Complete | |
| Logistic Regression Baseline | Complete | |
| XGBoost + Model Comparison | Complete | |
| Probability Calibration + SHAP | Complete | |
| Rule Engine + Risk Evidence | Complete | |
| Risk Fusion + Evidence Independence | Complete | |
| Decision Engine + Safety Guardrails | Complete | |
| Own/Open-Source AI Explanation | Complete | |
| Database + Audit Trail | Complete | |
| Production API | Complete | |
| Enterprise Dashboard | Complete | |
| Real-Time Processing Foundation | Complete | |
| Event Idempotency + Failure Semantics Hardening | Complete | |
| Comprehensive Robustness / Edge Cases | Complete | |
| 100K+ Workload / Load Validation | Complete | |
| Security + Failure/Recovery | Complete | |
| Docker + Deployment | Conditionally Pass | Docker daemon unavailable in validation environment |
| Deployed-System Validation | Not Started | |
| Final Evaluation + Demo | Not Started | |

---

## Author

**Sudarshan Kushwaha**
AI Buildathon 2026 — Track 02: AI Risk Manager

Deployment target: Docker-based local deployment; hosted deployment pending Phase 20.
"""

with open("README.md", "w") as f:
    f.write(readme_content)
