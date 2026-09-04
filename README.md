<div align="center">

<img src="https://upload.wikimedia.org/wikipedia/commons/8/89/Razorpay_logo.svg" width="300" alt="Razorpay Logo" />

<br />

# RazorBrain

<h3><strong>End-to-End AI Risk Management System for Real-Time Transaction Fraud Detection</strong></h3>

<sub>Track 02 — AI Risk Manager &nbsp;·&nbsp; AI Buildathon 2026</sub>

<br />

![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688?logo=fastapi)
![XGBoost](https://img.shields.io/badge/XGBoost-Serving-orange?logo=xgboost)
![SHAP](https://img.shields.io/badge/SHAP-Explainability-purple)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker)

</div>

---

## Overview

RazorBrain is an operational AI transaction fraud-risk manager. It processes Razorpay webhooks through a defensive, evidence-aware machine learning pipeline. Instead of relying solely on an opaque probability score, RazorBrain grounds its output in strict feature contracts, isotonic calibration, deterministic risk policy, and robust model SHAP explanations.

> **Important Limitation / Cross-Domain Disclaimer**
> RazorBrain operates in Razorpay Test Mode. The underlying serving model was trained on restricted IEEE-CIS public fraud data (US e-commerce). The Test Mode payments evaluated by this system are synthetic and do not reflect Indian UPI/Card payment patterns. Financial metrics and SHAP patterns exhibited here demonstrate architectural capability and system integration, but do not claim to detect real-world fraud on the Razorpay network.

---

## Actual End-to-End Architecture

RazorBrain strictly isolates the **Razorpay Serving Model** from legacy research models. The production transaction flow is completely deterministic:

1. **Transaction Event**: Razorpay webhook triggers on payment authorization.
2. **Security & Idempotency**: HMAC validation using constant-time checks; duplicate events are discarded via `x-razorpay-event-id`.
3. **Feature Extraction**: Strict extraction of exactly 15 causally safe features. Future data and identity leakage are blocked.
4. **Serving Model inference**: A frozen XGBoost model calculates a raw risk margin.
5. **Isotonic Calibration**: The margin is calibrated into a true probability estimate.
6. **Policy Engine**: A validation-selected policy applies strict thresholds (`T_review = 0.1213`, `T_block = 0.2053`).
7. **Decision**: The system issues a decision (`ALLOW`, `REVIEW`, `BLOCK`).
8. **Persistence**: Features, decisions, and metadata are safely written to an append-only `serving_assessments` table.
9. **Explanation (SHAP)**: A separate, non-blocking asynchronous pipeline calculates SHAP values explaining the model margin.
10. **Review Queue**: `REVIEW` decisions enter a deterministic manual queue prioritized by risk score.

---

## Model Separation (Model C vs. Serving Model)

RazorBrain implements two strict tracks:
*   **Model C**: A 150-feature baseline research model. Used strictly for offline benchmarking.
*   **Razorpay Serving Model**: The active webhook integration model. Features are limited to exactly 15 properties strictly derivable from a Razorpay webhook without data leakage.

The two models share no evaluation artifacts, deployment schemas, historical contexts, or ground-truth feedback tables. The API `/ops/ready` endpoint verifies that the Serving Model is active and loaded before allowing webhook processing.

---

## Model Performance

The Serving Model's metrics are carefully calculated against a permanently frozen held-out test set (`test.csv`, Hash: `fc4e76764a2e7ad1df631ce37d050f35`).

**The Razorpay-compatible serving model achieved ROC-AUC 0.7627 and PR-AUC 0.1452 on the frozen IEEE-CIS-derived serving test.**

At the validation-selected threshold (0.50), the metrics are:
*   Precision: 0.0851
*   Recall: 0.6364
*   F1: 0.1501
*   Specificity: 0.7531

*(Note: Model C baseline achieved ROC-AUC 0.8663, but required 150 features that are largely unavailable or cause leakage in real-time Razorpay environments).*

---

## Calibration and Risk Policy

### Isotonic Calibration
RazorBrain utilizes Isotonic Calibration applied strictly downstream of the frozen XGBoost model. It operates on the validation data. No test data was used for calibration.
*   Brier Score (Uncalibrated): 0.1800
*   **Brier Score (Isotonic Calibrated): 0.0307**

### Risk Policy
The policy thresholds were derived mathematically from validation data, allowing a 5% review capacity:
*   **ALLOW**: `risk < 0.1213`
*   **REVIEW**: `0.1213 <= risk < 0.2053`
*   **BLOCK**: `risk >= 0.2053`

---

## Explainability (SHAP)

The investigation dashboard provides a true SHAP (`shap.TreeExplainer`) breakdown of the decision.
*   SHAP explains the *uncalibrated XGBoost margin*, ensuring true feature contribution mapping.
*   Positive SHAP increases the model score; negative SHAP decreases it.
*   Categorical one-hot encoded variables are mathematically fused back to their source feature for human-readable explanations.
*   **Failsafe**: If the explainer fails, the exception is caught, and the response is marked `UNAVAILABLE`, preserving the original `ALLOW`/`REVIEW`/`BLOCK` decision. SHAP never alters a decision.

---

## Review Queue and Ground Truth

RazorBrain strictly separates model predictions from true fraud ground truth.
*   Only `REVIEW` decisions enter the pending queue. `BLOCK` and `ALLOW` bypass it.
*   Queue priority is strictly deterministic (descending by calibrated risk).
*   Submitting feedback (`FRAUD` or `LEGITIMATE`) records the ground truth in `serving_evaluation_feedback`. **It preserves the original model decision, risk score, and policy version.** The system will never automatically rewrite a model's `BLOCK` to a `FRAUD` label.

---

## Operational Metrics and Drift

Dashboard metrics reflect **actual persisted data**, with no fabricated transactions or fraud counts.

### Metrics
*   Precision and Recall are explicitly marked as `INSUFFICIENT_DATA` until actual ground truth is provided.
*   Financial metrics are explicitly labeled as **Amount blocked by policy** and **Amount reviewed**. They are *not* called "fraud loss prevented" unless real ground truth explicitly supports the claim.

### Drift Monitoring
*   Compares the most recent 100 assessments against the preceding 100 assessments (recent population/distribution change monitoring).
*   Does not rely on fabricated baselines.
*   Gracefully returns `INSUFFICIENT_DATA` if fewer than 200 operational assessments exist.

---

## Docker Clean-Start (Deployment)

RazorBrain is designed for deterministic, resilient deployment. 
`docker compose up --build` ensures:
1. Database initializes.
2. Migrations (`001` through `005`) run synchronously and idempotently.
3. Artifacts (`model`, `calibrator`, `policy`, `feature contract`) are verified via hash checks.
4. The system starts up safely.

**No accidental training, calibration, or test-data loading occurs at runtime.**

---

## License
MIT License.
