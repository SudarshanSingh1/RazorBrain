# Operations and Monitoring

This document outlines the operational hardening implemented for the Razorpay Serving Model to support deterministic, safe execution in production or local Docker environments.

## 1. Docker Startup

The system is configured to start securely from a clean `docker compose up` environment without attempting to retrain or optimize the serving model.

The startup sequence is strictly deterministic:
1. Wait for database.
2. Run database migrations in sequential order.
3. Validate artifacts: `data/razorpay_serving_model_calibrated.joblib` and `data/razorpay_serving_selected_policy.json`.
4. The system validates the `model_track` matches `RAZORPAY_SERVING_MODEL`.
5. Loads the frozen calibrator and XGBoost model.
6. Starts the Real-Time Event Processor and API.

**Failure Behavior**: If required artifacts are missing, the API fails cleanly. It does **not** fall back to training. It does **not** silently default to Model C. All Razorpay serving traffic routes to a fail-closed `REVIEW` decision if the serving model is unavailable.

## 2. Model Loading & Readiness

At runtime, `api/lifespan.py` performs rigorous initialization checks. It injects the `ServingModelLoader`, `ServingPolicyLoader`, and `ServingSHAPExplainer` into the `AppState`.

**Health Endpoints**:
- `/health`: Simple liveness check (HTTP server running).
- `/ready`: Readiness check. Verifies the database is queryable and the Serving Model artifacts are correctly loaded into memory.

## 3. Database Migrations

Database operations are executed through SQL migrations (`database/migrations/`).
- `004_serving_assessments.sql` isolates serving traffic from the existing `risk_assessments` table.
- `005_serving_operations.sql` introduces `serving_evaluation_feedback` (ground truth) and `review_status` columns to `serving_assessments`.

Migrations are idempotent and order-dependent. They execute synchronously at application boot.

## 4. Review Queue Workflow

Only assessments with a `REVIEW` decision automatically enter the manual review queue (via `review_status = 'PENDING'`). `BLOCK` and `ALLOW` decisions are set to `NOT_REQUIRED` to keep the queue actionable.

- **Priority**: Queue priority is entirely deterministic and relies on calibrated `risk` in descending order.
- **Workflow**: PENDING → REVIEWED.
- **API**: Exposed securely via `/ops/review-queue`.

## 5. Ground-Truth Handling

Model decisions are **not** ground truth. Submitting an outcome (e.g., `FRAUD` or `LEGITIMATE`) via the `/ops/review-queue/{id}/feedback` endpoint:
- Persists to a dedicated `serving_evaluation_feedback` table.
- Records the reviewer action and timestamp.
- **Preserves** the original model decision, risk score, and policy version.
- Will **never** automatically rewrite a `BLOCK` to `FRAUD` or an `ALLOW` to `LEGITIMATE`.

## 6. Operational Metrics

The `/ops/overview` endpoint calculates metrics directly from persisted data:
- `total_assessments`, `ALLOW`, `REVIEW`, `BLOCK`.
- Precision and Recall metrics are only calculated for records that possess a corresponding entry in `serving_evaluation_feedback`.
- If insufficient labeled data exists, the endpoint safely returns `INSUFFICIENT_DATA` rather than fabricating metrics from model assumptions.

## 7. Financial Metric Definitions

Financial metrics are exposed in the operations dashboard but explicitly labeled to prevent misinterpretation:
- `amount_blocked_by_policy` 
- `amount_reviewed`
- *Definition Note*: Financial metrics indicate estimated exposure intercepted under the assumed policy. They do NOT represent measured fraud savings unless confirmed by real ground truth.

## 8. Drift Monitoring

The `/ops/drift` endpoint offers lightweight monitoring utilizing only actual persisted traffic:
- Compares the most recent 100 assessments against the prior 100 assessments as a rolling baseline.
- Tracks decision proportion shifts and risk mean deviations.
- If fewer than 200 total serving assessments exist, it explicitly returns `INSUFFICIENT_DATA`.
- Does **not** fabricate baseline distributions or falsely alarm based on insufficient history.

## 9. SHAP Isolation

The `ServingSHAPExplainer` executes strictly outside the synchronous critical decision path.
- The explanation explains the *model score*, it does not constitute *proof of fraud*.
- If the explainer raises an exception, the exception is caught, the response sets `"status": "UNAVAILABLE"`, and the original `ALLOW`/`REVIEW`/`BLOCK` decision remains unmutated.

## 10. Security Controls

- **Webhook Validation**: Razorpay HMAC signatures are validated in constant time (`hmac.compare_digest`) against the raw byte-stream before JSON parsing to mitigate serialization vulnerabilities.
- **Idempotency**: Webhook events check for existing processing via the `x-razorpay-event-id` header to avoid duplicate risk execution.
- **Logging**: PII (emails, full contact numbers), API Keys, and Webhook secrets are never logged. Error responses are scrubbed of internal stack traces.

## 11. Cross-Domain and Test Mode Limitations

> [!CAUTION]
> RazorBrain operates in Razorpay Test Mode. The serving model was trained on IEEE-CIS data (US e-commerce). The Test Mode payments evaluated by this system are synthetic and do not reflect Indian UPI/Card payment patterns. Financial metrics and SHAP patterns exhibited here demonstrate architectural capability but do not claim to detect real-world fraud on the Razorpay network.

## 12. Model C vs. Serving Model Separation

- `RAZORPAY_SERVING_MODEL` is completely decoupled from Model C.
- Their evaluation artifacts, deployment schemas (`serving_assessments` vs `risk_assessments`), historical contexts, and ground truth feedback (`serving_evaluation_feedback` vs `evaluation_feedback`) share no operational overlap.
- Validation metrics and held-out test metrics remain permanently frozen in the deployment artifacts and are explicitly documented as separate from real-time operational metrics.
