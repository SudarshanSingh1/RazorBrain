# SentinelML — Investigation Case Management & Transaction Lifecycle (Prompt 4)
**Production-Grade Case Management, State Transitions, and Analyst Workflows**  
*Track 02: AI Risk Manager — AI Buildathon 2026*

---

## 1. Executive Summary

SentinelML's investigation case management system provides a production-grade operational workflow for fraud analysts and risk teams. It closes the loop between automated machine learning scoring, deterministic rule fusion, and human investigative oversight.

### 1.1 Strict Architectural Boundary & Scientific Integrity

A core principle of SentinelML is the explicit architectural separation between automated intelligence and operational human feedback:

1. **ML Prediction**: Calibrated probability produced by the frozen XGBoost model using the strict 15-feature contract.
2. **Operational Decision**: Automated decision (`APPROVE`, `REVIEW`, `STEP_UP`, `DECLINE`) determined by versioned rules, decision policies, and safety guardrails.
3. **Investigation Case**: Operational record generated automatically when a transaction requires human review (`REVIEW` or `STEP_UP`) or manually referred by an analyst.
4. **Analyst Action**: Lifecycle state changes (`ASSIGN`, `INVESTIGATE`, `ESCALATE`, `RESOLVE`) executed by risk officers.
5. **Verified Outcome**: Operational case resolution (`CONFIRMED_FRAUD`, `CONFIRMED_LEGITIMATE`, `INCONCLUSIVE`, `DUPLICATE`, `OTHER`).

> **CRITICAL GOVERNANCE MANDATE**: Analyst case resolutions are operational feedback records stored in audit logs. Under no circumstances are analyst labels automatically fed into serving model retraining pipelines or treated as unverified ground truth. Serving model artifacts remain frozen and strictly calibrated.

---

## 2. System Architecture

```
                    ┌─────────────────────────────────────────┐
                    │       Transaction Ingestion             │
                    │   (Manual Scoring / API / Webhook)      │
                    └────────────────────┬────────────────────┘
                                         │
                                         ▼
                    ┌─────────────────────────────────────────┐
                    │      15-Feature Extraction Contract     │
                    └────────────────────┬────────────────────┘
                                         │
                                         ▼
                    ┌─────────────────────────────────────────┐
                    │  Frozen Calibrated XGBoost Serving Model│
                    └────────────────────┬────────────────────┘
                                         │
                                         ▼
                    ┌─────────────────────────────────────────┐
                    │ Hybrid Risk Fusion Layer (Rules + ML)   │
                    └────────────────────┬────────────────────┘
                                         │
                                         ▼
                    ┌─────────────────────────────────────────┐
                    │    Decision Engine (Policy v2)          │
                    │  APPROVE / REVIEW / STEP_UP / DECLINE   │
                    └────────────────────┬────────────────────┘
                                         │
                      Decision == REVIEW or STEP_UP?
                                         │
                        ┌────────────────┴────────────────┐
                        │ YES                             │ NO (APPROVE / DECLINE)
                        ▼                                 ▼
             ┌──────────────────────┐             ┌──────────────────────┐
             │ Auto-Create Case     │             │ Log Audit & Complete │
             │ - Priority mapping   │             │ (No case required)   │
             │ - SLA assignment     │             └──────────────────────┘
             │ - Evidence snapshots │
             └──────────┬───────────┘
                        │
                        ▼
             ┌──────────────────────────────────────────────────────────┐
             │            Case Lifecycle State Machine                  │
             │                                                          │
             │   ┌──────┐  investigate   ┌───────────────┐              │
             │   │ OPEN │ ------------> │ INVESTIGATING │              │
             │   └──┬───┘                └───────┬───────┘              │
             │      │                            │                      │
             │      │ resolve          escalate  │  resume              │
             │      │                            ▼                      │
             │      │                     ┌───────────┐                 │
             │      │                     │ ESCALATED │                 │
             │      │                     └─────┬─────┘                 │
             │      │                           │                       │
             │      ▼        resolve            ▼                       │
             │   ┌────────────────────────────────┐                     │
             │   │            RESOLVED            │ (Immutable Terminal)│
             │   └────────────────────────────────┘                     │
             └──────────────────────────────────────────────────────────┘
```

---

## 3. Data Model & Database Schema

Migration `database/migrations/008_investigation_cases.sql` adds two dedicated tables:

### 3.1 `investigation_cases` Table
- **`case_id`**: Globally unique ID (`case_YYYYMMDD_<hex>`).
- **`transaction_id`**: Foreign reference to the transaction.
- **`assessment_id`**: Foreign reference to the decision assessment.
- **`status`**: State machine status (`OPEN`, `INVESTIGATING`, `ESCALATED`, `RESOLVED`).
- **`priority`**: Severity tier (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`).
- **`assigned_to`**: Analyst username or email.
- **`resolution_type`**: Outcome (`CONFIRMED_FRAUD`, `CONFIRMED_LEGITIMATE`, `INCONCLUSIVE`, `DUPLICATE`, `OTHER`).
- **`resolution_notes`**: Detailed findings from investigator.
- **`escalation_reason`**: Justification when escalated to Tier-2 review.
- **`decision_snapshot`**: Frozen JSON payload capturing base decision, final decision, amount, and reason.
- **`risk_snapshot`**: Frozen JSON payload capturing calibrated fraud probability, model risk level, and thresholds.
- **`rule_snapshot`**: Frozen JSON payload capturing triggered deterministic rules and fusion version.
- **`version`**: Integer counter for optimistic concurrency locking.
- **`UNIQUE(transaction_id, assessment_id)`**: Idempotency guarantee preventing duplicate case creation.

### 3.2 `case_events` Table (Immutable Audit Timeline)
- **`event_id`**: Globally unique ID (`evt_<hex>`).
- **`case_id`**: Foreign key to `investigation_cases`.
- **`event_type`**: Action performed (`CASE_CREATED`, `INVESTIGATION_STARTED`, `CASE_ASSIGNED`, `CASE_ESCALATED`, `CASE_RESOLVED`).
- **`previous_state`** & **`new_state`**: State transition delta.
- **`actor`**: User or service initiating the change (`SYSTEM`, `analyst_sam`, etc.).
- **`metadata`**: JSON payload with context (notes, escalation reasons, SLA info).
- **`created_at`**: UTC timestamp of event occurrence.

---

## 4. State Machine & Concurrency Control

### 4.1 Valid Transitions
| Current State | Allowed Next State | Action / Method |
| :--- | :--- | :--- |
| `OPEN` | `INVESTIGATING` | `start_investigation()` |
| `OPEN` | `RESOLVED` | `resolve_case()` |
| `INVESTIGATING` | `ESCALATED` | `escalate_case()` |
| `INVESTIGATING` | `RESOLVED` | `resolve_case()` |
| `ESCALATED` | `INVESTIGATING` | `start_investigation()` (Resume) |
| `ESCALATED` | `RESOLVED` | `resolve_case()` |
| `RESOLVED` | *(None)* | Terminal state; modifications rejected |

### 4.2 Optimistic Concurrency Control (OCC)
To prevent lost updates in multi-analyst operational centers:
1. Every case state modification request must pass `expected_version: int`.
2. The service executes an atomic conditional SQL update: `UPDATE investigation_cases SET ..., version = version + 1 WHERE case_id = ? AND version = ?`.
3. If row count is 0, the service throws `ConcurrencyConflictError`, mapping to HTTP **409 Conflict**. The frontend displays a conflict banner and refreshes state automatically.

---

## 5. API Endpoints Reference

| Method | Path | Description | Status Code |
| :--- | :--- | :--- | :--- |
| `POST` | `/cases` | Manually create or idempotent re-fetch case | 201 Created |
| `GET` | `/cases` | Paginated listing with status, priority, and text filters + summary KPIs | 200 OK |
| `GET` | `/cases/{case_id}` | Retrieve case details, frozen evidence snapshots, and event timeline | 200 OK / 404 |
| `POST` | `/cases/{case_id}/assign` | Assign investigator with optimistic concurrency lock | 200 OK / 409 |
| `POST` | `/cases/{case_id}/investigate` | Transition status to `INVESTIGATING` | 200 OK / 409 |
| `POST` | `/cases/{case_id}/escalate` | Escalate case with required escalation reason | 200 OK / 409 |
| `POST` | `/cases/{case_id}/resolve` | Resolve case with resolution type, notes, and governance audit | 200 OK / 409 |
| `POST` | `/transactions/decide` | Scored decisions automatically return `case: { case_created, case_id, ... }` | 200 OK |

---

## 6. Frontend User Experience

### 6.1 Investigation Queue (`/cases`)
- **KPI Metrics Cards**: Total Open, Under Investigation, Escalated, High/Critical Open, Resolved Today.
- **Search & Filters**: Debounced text search (Case ID, Transaction ID, Assignee) with Status and Priority filter dropdowns.
- **Cases Table**: Live priority badges (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`), lifecycle badges, assignment status, and direct link to case details.

### 6.2 Case Detail Workspace (`/cases/:caseId`)
- **Header & Action Bar**: Contextual action buttons dynamically shown based on lifecycle state (Start Investigation, Assign, Escalate, Resolve).
- **SLA & Turnaround Target**: Computes real-time countdown against policy deadlines (`CRITICAL`: 4h, `HIGH`: 12h, `MEDIUM`: 24h, `LOW`: 48h) with visual breach warnings.
- **Frozen Evidence Snapshots**: Read-only display of exact scoring-time metrics: Base Decision, Final Decision, Calibrated Probability, Model Risk Level, and Triggered Rule details.
- **Audit Timeline**: Chronological event stream displaying state transitions, actors, timestamps, and investigation notes.
- **Governance Disclaimers**: Clear visual notices highlighting operational partitioning from ML ground truth.

---

## 7. Verification & Quality Assurance

### 7.1 Automated Test Suites (59 Tests Passing)
- `tests/test_case_service.py` (6 tests): Valid and invalid state transitions, optimistic locking, idempotent insertion, priority mapping, and event logging.
- `tests/test_case_routes.py` (4 tests): REST endpoints for case creation, listing, filtering, optimistic conflict handling (409), and 404 handling.
- `tests/test_case_lifecycle.py` (2 tests): End-to-end flow from `POST /transactions/decide` auto-triggering case creation on `REVIEW` through assignment, investigation, and final resolution.
- `tests/test_rule_engine.py` (13 tests): Rule evaluation, severity, and deterministic priority.
- `tests/test_risk_fusion.py` (8 tests): Hard safety overrides, monotonic guardrails, hybrid decision fusion.
- `tests/test_decision_engine.py` (12 tests): Decision engine policies and trace logging.
- `tests/test_predict.py` (14 tests): Manual scoring and 15-feature contract compliance.

```bash
RAZORBRAIN_API_KEY="" .venv/bin/python3 -m pytest tests/test_case_service.py tests/test_case_routes.py tests/test_case_lifecycle.py tests/test_rule_engine.py tests/test_risk_fusion.py tests/test_decision_engine.py tests/test_predict.py
# 59 passed, 4 warnings in 16.78s
```

### 7.2 Frontend Compilation & Linting
```bash
npm run lint && npm run build
# oxlint: 0 errors
# tsc -b && vite build: 0 errors (dist/ assets generated cleanly)
```

### 7.3 Model Artifact Integrity Verification
MD5 checksums remain 100% byte-identical to pre-prompt baselines:
- `data/razorpay_serving_model_calibrated.joblib`: `1aada82e6f1af13bcada372eb02ec312`
- `data/razorpay_serving_model_uncalibrated.joblib`: `1242b74830962d8d323676563648ffdb`
- `data/model_c_calibrated.joblib`: `17eaa5aad2a2672f497221362ee4cefd`
