# Scoring and Decision Contract

## 1. Overview
The real-time scoring engine follows a strictly linear, deterministic flow:
1. Feature extraction
2. Model C raw prediction
3. Platt Calibration
4. Evidence generation (SHAP, Rules, Behavioral, Data-Quality)
5. Decision Policy (ALLOW / REVIEW / BLOCK)

*The held-out IEEE-CIS test set was used only for final evaluation and was not used to calibrate, optimize, or select the operational policy.*

## 2. Core Concepts

### 2.1 Model C & Raw Score
- The base model produces an uncalibrated margin score (XGBoost tree sum). 
- This value is captured as `raw_model_score`.
- It is NOT used for decisions directly.

### 2.2 Platt Calibration & Calibrated Risk
- A `FrozenEstimator` wraps Model C to guarantee the base model is never retrained.
- Platt scaling (logistic regression) converts `raw_model_score` into `calibrated_risk` (a true probability estimate).
- All downstream decisions and evaluations use `calibrated_risk`.

### 2.3 Validation-Selected Thresholds
- Extracted dynamically from `data/validation_selected_policy.json`.
- `T_review`: 0.1258
- `T_block`: 0.3125
- Thresholds are rigidly applied:
  - `risk < T_review`: ALLOW
  - `T_review <= risk < T_block`: REVIEW
  - `risk >= T_block`: BLOCK

## 3. Evidence Contract

The evidence layer serves strictly to *explain* the decision. It is **READ-ONLY** with respect to the `calibrated_risk`. SHAP values or rule firings NEVER mutate or override the `calibrated_risk`.

Every evidence item follows a strict `EvidenceItem` schema:
```json
{
  "source": "MODEL | RULE | BEHAVIOR | DATA_QUALITY",
  "code": "STABLE_IDENTIFIER",
  "feature": "amount",
  "value": 15000,
  "direction": "INCREASES_RISK",
  "description": "High transaction amount",
  "available_at_scoring": true
}
```

### 3.1 Temporal Availability
- Historical and behavioral features must represent state *before* the transaction.
- If data is missing (e.g. unknown customer), evidence is logged with `"source": "DATA_QUALITY"`.
- Missing data cannot artificially raise the model score.

## 4. Audit & API 
The API response returns `raw_model_score`, `calibrated_risk`, `decision`, and a fully structured `decision_reason` object containing the thresholds and nested evidence arrays. No production secrets or arbitrary rule scores are exposed.

## 5. Domain Limitation
The `calibrated_risk` represents a statistical risk estimate under the IEEE-CIS calibration population. It does not literally guarantee "there is exactly an X% chance this Razorpay transaction is fraudulent" until evaluated against true Razorpay labels.
