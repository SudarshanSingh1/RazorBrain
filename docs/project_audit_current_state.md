# RazorBrain Project Audit: Current State

## 1. Executive Summary
The RazorBrain repository is currently a sophisticated prototype. While it contains strong architectural elements for feature engineering, decision logic, and Razorpay integration, it fundamentally relies on **synthetic data generation** at application startup to train an in-memory XGBoost model. There is no persisted model artifact, and real-world datasets in `data/RAW/` are currently unutilized in the production lifecycle. The explanation engine uses deterministic rules rather than an LLM, and Docker deployment inherently depends on this synthetic training loop.

## 2. Repository Structure
- **api/**: FastAPI routes, application state, lifespan management, schemas, and Razorpay webhooks.
- **model/**: Contains ML training loops (`baseline.py`), feature engineering, calibration, evaluation scripts, and the decision engine.
- **database/**: SQLite repository logic and schema migrations.
- **frontend/**: React/Vite dashboard application.
- **data/**: Synthetic generator (`generator.py`) and ignored RAW datasets.
- **tests/**: Local test suite.
- **scratch/**: Temporary or fast audit scripts.

## 3. Current Architecture

### DATA / TRAINING SIDE (Current Reality)
Synthetic Generator (n=1000) -> Historical Feature Computation -> Feature Fitting -> Baseline XGBoost Train -> Calibration Fit -> In-Memory State

### PRODUCTION SIDE
Razorpay Webhook/Normal API -> Request Validation -> Idempotency Check -> Live Feature Extraction (SQLite queries) -> Model Inference -> Risk Fusion -> Decision Engine -> Deterministic Explanation -> Persistence -> Dashboard

*Deviation:* The architecture diagram assumes a loaded model artifact trained on real data. The current implementation trains the model on synthetic data every time the API starts.

## 4. End-to-End Transaction Flow

**A. Normal Transaction API**
`api/routes.py` POST `/transactions` -> `api/service.py:assess_transaction` -> `get_live_historical_features` -> `model_artifact.predict_proba` -> `decision_engine` -> `explanation_engine.explain` -> `database.repository.save_assessment`

**B. Razorpay Test Mode**
`api/razorpay_routes.py` POST `/razorpay/test/checkout` -> `RazorpayAdapter.create_test_order` -> Razorpay API

**C. Razorpay Webhook**
`api/razorpay_routes.py` POST `/webhooks/razorpay` -> HMAC signature verification -> Extract event payload -> `razorpay_adapter.normalize_razorpay_payment` -> Converts to `TransactionRequest` using notes for telemetry -> passes to `api/service.py:assess_transaction`

## 5. Synthetic Data Dependency Audit
**CRITICAL FINDING:** `api/lifespan.py` calls `generate_transactions(n=1000, seed=1337)` on FastAPI startup.
- **FILE:** `api/lifespan.py`
- **FUNCTION:** `lifespan(app: FastAPI)`
- **WHAT DATA IS USED:** 1000 rows of synthetic transaction data.
- **WHY IT IS USED:** To bootstrap a small subset to ensure the engine is fully operational without an external artifact.
- **AFFECTS PRODUCTION INFERENCE:** YES. The production endpoint uses this synthetically trained model to score real requests.
- **RISK LEVEL:** CRITICAL.

## 6. Model Lifecycle Audit
- **Current authoritative model:** In-memory `XGBClassifier`.
- **Where is it trained:** Inside `api/lifespan.py` during app startup.
- **Where is it saved:** Kept in `app_state.model_artifact` (RAM only). Not persisted to disk.
- **Where is it loaded:** Never loaded from an artifact file.
- **Calibration Persisted:** No.
- **Feature Schema Persisted:** No.
- **What happens if missing:** It cannot be missing because the app trains it synchronously on startup before accepting requests.
- **Production API silently trains a replacement model:** YES. 

## 7. Feature Engineering Audit
Features like `amount`, `avg_customer_amount`, and `amount_deviation` are computed.
- **Training source:** `model/feature_engineering.py:compute_historical_features` (Pandas vectorized on full generated timeline).
- **Serving source:** `database/repository.py:get_live_historical_features` (SQLite aggregations on live DB records).
- **Razorpay source:** Extracted from Razorpay notes and payload.
- **Potential leakage:** Training computes history globally. Serving relies on SQLite which uses `< current_timestamp` preventing future leakage.
- **Semantic Mismatch:** The training Pandas logic heavily relies on synthetic data behaviors, which may differ structurally from the live SQLite schema on real data.

## 8. Current 17-Feature Contract Audit
The system relies on features like `amount`, `customer_account_age_days`, `previous_transaction_count`, etc. 
- **Training implementation:** Vectorized in pandas.
- **Serving implementation:** Implemented via `get_live_historical_features`.
- **Razorpay implementation:** `normalize_razorpay_payment` translates fields (e.g., `netbanking` -> `bank_transfer`).
- **Dependency on synthetic semantics:** Yes. Real categorical distributions (payment methods) have not been modeled.

## 9. Label Availability Audit
- **Training label availability:** Synthetic labels are immediately available in the training dataframe.
- **Serving label availability:** Uses the `evaluation_feedback` table. Live feature queries strictly bound to `timestamp` but the mismatch between immediate synthetic labels and delayed real-world labels is severe.

## 10. Razorpay Integration Audit
- **Supported:** Only Test Mode (`RazorpayAdapter`).
- **Signature:** HMAC verified safely in webhook.
- **Idempotency:** Utilizes `event_id` checking via `reserve_event` in the database.
- **Fake/Hardcoded Telemetry:** `client_ip = request.client.host if request.client else "127.0.0.1"` in the webhook router if no client host is detected. Device/IP data heavily rely on server-injected `notes` sent during order creation.

## 11. Database Audit
- **Persisted Data:** Transactions, risk assessments, rule evidence, decisions, explanations, processed events, and evaluation feedback.
- **Path:** Docker utilizes `/app/data_store/razorbrain_production.db` injected via `.env`.
- **Idempotency:** `processed_events` prevents double processing of Razorpay webhooks.

## 12. API Audit
- `POST /transactions`: Assesses risk (uses synthetic model).
- `POST /razorpay/test/checkout`: Initiates Razorpay test order.
- `POST /webhooks/razorpay`: Razorpay webhook entry point.
- `/dashboard/*`: Exposes analytics endpoints. Dashboard analytics are based on database records, which reflect the decisions of the synthetic model.

## 13. Dashboard Audit
- Dashboard accurately reflects the SQLite database. However, because the DB is populated by a synthetically-trained model, the probabilities and metrics reflect synthetic distributions. 
- Review capacity uses hypothetical simulator inputs rather than purely observed operational metrics.

## 14. Evidence/Explanation Audit
- **REAL LLM INFERENCE = NOT CURRENTLY USED.**
- The `ExplanationEngine` intentionally uses a `DeterministicFallbackProvider` which constructs text directly from evidence arrays.

## 15. Decision Engine Audit
- **ALLOW threshold:** 0.10
- **BLOCK threshold:** 0.40
- **Source:** Hardcoded in `api/lifespan.py`, derived historically from synthetic distributions.

## 16. Drift/Operations Audit
- Drift monitoring measures the Population Stability Index (PSI) against a reference distribution built in-memory during startup using the synthetic dataset predictions. 
- Status: Measures operational distribution change against an artificial baseline.

## 17. OR Audit
- Operational analytics and review capacity simulations are mathematical assumptions (`simulate_review_capacity`), not optimization from real observed data.

## 18. Docker Audit
- `compose.yaml` and `Dockerfile.backend` correctly configured for API and DB.
- Docker environment inherently trains the synthetic model on startup because `lifespan.py` is invoked unconditionally. 

## 19. Testing Results
- **pytest:** Fails locally. `ModuleNotFoundError: No module named 'xgboost'`.
- **Frontend build:** Succeeded (Vite build completed).
- **Docker startup:** Failed locally due to Docker socket unavailability in the sandbox environment.

## 20. Repository Hygiene
- Datasets are safely ignored.
- Model artifacts do not exist in the repository (not tracked or generated).
- Deleted scratch scripts and evaluation reports are uncommitted.

## 21. Hardcoded/Fabricated Data Audit
- `127.0.0.1` hardcoded for missing client IPs in webhook.
- The UI review queue planning tool uses hypothetical data (explicitly stated).

## 22. Dataset Inventory
The following files exist in `data/RAW/` and are currently ignored by the application:
1. `train_transaction.csv`
2. `train_identity.csv`
3. `creditcard_2023.csv`
4. `bs140513_032310.csv`
5. `bsNET140513_032310.csv`
6. `fraud_dataset.csv`
- **UPI dataset:** NOT FOUND LOCALLY.

## 23. Phase 21C Protection Check
- `model/phase_21c_final_test_report.md` exists and is preserved. The code does not overwrite this file.

## 24. Findings
- **CRITICAL**: Production Docker startup silently generates synthetic data and trains an XGBoost model used for live inference.
- **HIGH**: No authoritative real model artifact exists on disk.
- **HIGH**: `get_live_historical_features` uses assumptions derived from the synthetic generator.
- **MEDIUM**: Local test suite lacks required dependencies (`xgboost`) in base requirements.
- **INFO**: Explanation engine uses deterministic fallback, not an LLM.

## 25. Current Reality Table
| Component | Current Reality | Evidence | Status |
|---|---|---|---|
| ML training data | Synthetic (n=1000) | `api/lifespan.py` | IMPLEMENTED |
| Model | XGBClassifier | `model/baseline.py` | IMPLEMENTED |
| Model artifact | Kept in RAM | `api/lifespan.py` | NOT IMPLEMENTED |
| Razorpay webhook | HMAC verified, notes extracted | `api/razorpay_routes.py` | IMPLEMENTED |
| Razorpay Test Mode | Adapter creates orders | `api/razorpay_adapter.py` | IMPLEMENTED |
| Feature telemetry | Server IP injection to notes | `api/razorpay_adapter.py` | ASSUMED |
| Database | SQLite local/volume | `compose.yaml` | IMPLEMENTED |
| Dashboard | React/Vite serving DB stats | `frontend/src/` | IMPLEMENTED |
| Explanation | Deterministic string fallback | `model/explanation_engine.py`| IMPLEMENTED |
| Ground truth | `evaluation_feedback` table | `database/repository.py` | IMPLEMENTED |
| Drift | PSI vs synthetic reference | `model/drift_monitor.py` | IMPLEMENTED |
| Docker | Fails natively without ML artifact | `compose.yaml` | TESTED LOCALLY |

## 26. Ordered Next Work
1. Remove synthetic training dependency from production API startup.
2. Develop a real dataset adapter for `train_transaction.csv` and `train_identity.csv`.
3. Align the real feature contract across training and serving.
4. Correct leakage and availability semantics for real labels.
5. Create a standalone real-data training pipeline that saves a persistent artifact.
6. Perform model validation on the real dataset.
7. Align Razorpay serving adapter with the real model's expectations.
8. Perform end-to-end integration and load testing.

## 27. Explicit Limitations
- This audit did NOT test Razorpay webhook signatures against live Razorpay servers.
- This audit did NOT measure the inference latency of the live SQL feature queries on a populated production database.
- Real-data performance is unproven.

***

AUDIT STATUS:
Critical findings: 1
High findings: 2
Medium findings: 1
Low findings: 0

Synthetic data used for final ML training:
YES

Production inference silently trains a model:
YES

Current authoritative model:
XGBClassifier

Current model artifact:
NOT FOUND

Razorpay Test Mode integration:
IMPLEMENTED

Razorpay webhook integration:
IMPLEMENTED

Real-data training pipeline:
NOT IMPLEMENTED

UPI dataset found locally:
NOT FOUND

Phase 21C preserved:
YES

Tests:
FAILED (ModuleNotFoundError: xgboost)

Frontend:
SUCCEEDED

Docker:
FAILED (Socket unavailable)

NEXT ACTION:
Remove synthetic training dependency from production API startup
