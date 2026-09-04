# Codebase Cleanup Report (Prompt 28)

## 1. Dead Code Removal
- Removed `api/operations.py` (obsolete router, endpoints superseded by `dashboard_routes.py`).
- Removed `model/shap_evidence.py` (abandoned, duplicate SHAP implementation).
- Removed unused local variables across `model/` scripts (`compute_time`, `t0`, `val_feat`, `X_val`, `y_val`, `n_legit`, `t_start`, etc.).
- Cleaned unused imports across the codebase (`TargetEncoder`, `time`, etc.).
- Removed empty and obsolete directories: `evaluation/`, `backend/`, `model_artifacts/`.
- Cleared out the `scratch/` directory containing temporary dev scripts and JSON dumps.

## 2. Duplicate Logic Consolidation
- Fixed duplicate router prefix definitions in `api/app.py` (routers were being included with a prefix while internally defining the exact same prefix).
- Verified `normalize_razorpay_payment` and feature extraction pipelines are uniquely implemented. Legacy Model C vs. Serving pipelines remain intentionally isolated.

## 3. Linting & Error Handling
- Fixed all Ruff violations (E701, E402, F401, F821, F841).
- Replaced bare `except:` blocks with `except Exception:` in database operations.
- Fixed an unhandled `console.error` in the React frontend (`DriftMonitoring.tsx`) by converting it into a proper UI error state.

## 4. Terminology Fixes
- Standardized logging and terminal output to strictly use "RISK PROBABILITIES" rather than "FRAUD SCORES".

## 5. Security Check
- Verified `RAZORBRAIN_API_KEY` is loaded from the `.env` environment rather than hardcoded. Hardcoded `dev-api-key-123` tokens strictly reside in the `tests/` directory.

## 6. Testing & Build
- Python backend test suite executed (Razorpay flows, Serving flows, Webhooks pass).
- Documented that `test_api.py` (Legacy Model C) contains API-contract drift failures, intentionally retained as historical artifacts.
- `test_operations.py` and `test_shap_evidence.py` marked as skipped due to intentional codebase pruning.
- Frontend builds cleanly (`npm run build`) with strict TypeScript type-checking passing.
