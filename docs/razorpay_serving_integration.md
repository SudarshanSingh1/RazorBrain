# Razorpay Serving Model — End-to-End Integration

## 1. Architecture

```
Razorpay Test Mode Payment
         │
         ▼
   Signature Validation (HMAC-SHA256, constant-time, over raw body)
         │
         ▼
   Idempotency Check (x-razorpay-event-id deduplication)
         │
         ▼
   Canonical Payment Extraction (RazorpayAdapter.fetch_payment or webhook entity)
         │
         ▼
   Historical Feature Query (DB: transactions WHERE timestamp < current, strict <)
         │
         ▼
   15-Feature Serving Extraction (ServingFeatureExtractor)
         │
         ├──────────────────────────────────────────────────┐
         ▼                                                  ▼
   ServingModelLoader.predict_calibrated_proba      SHAP (read-only, separate path)
         │                                                  │
         ▼                                                  ▼
   Isotonic Calibrated Risk (0–1)             ServingSHAPExplainer.explain(X)
         │                                                  │
         ▼                                                  ▼
   ServingPolicyLoader.make_decision(risk)    explanation {status, top_positive, ...}
         │
         ▼
   ALLOW / REVIEW / BLOCK
         │
         ▼
   Audit Persistence (serving_assessments table)
         │
         ▼
   POST_EVENT_RISK_ASSESSMENT Response
```

**SHAP never touches the decision path.** A SHAP failure returns `{status: UNAVAILABLE}` and the decision is unchanged.

## 2. Feature Extraction

**Module**: [`model/serving_feature_extractor.py`](file:///Users/sudarshankumar/RazorBrain/model/serving_feature_extractor.py)

Produces exactly 15 features in contract order. No extra features can silently enter the model.

| Feature | Source | Notes |
|---|---|---|
| `amount` | Razorpay payment (paise → main units) | Always available |
| `log_amount` | `log1p(amount)` | Always computable |
| `hour_of_day` | Real ISO-8601 UTC timestamp | Unavailable if timestamp unparseable |
| `day_of_week` | Real ISO-8601 UTC timestamp | Calendar day, NOT IEEE-CIS TransactionDT |
| `email_domain` | `payment.email` split on `@` | MISSING if email absent |
| `email_domain_missing` | Derived from email | Always computable |
| `card_network` | `payment.card.network` | MISSING if card info absent |
| `card_type` | `payment.card.type` | MISSING if card info absent |
| `previous_transaction_count` | DB history | Cold-start = 0 |
| `is_new_customer` | DB history | Cold-start = 1 |
| `avg_customer_amount` | DB history (strict < timestamp) | Cold-start = 0.0 |
| `amount_deviation` | `|amount - avg_customer_amount|` | Cold-start = 0.0 |
| `amount_ratio` | `amount / avg_customer_amount` | Cold-start = 1.0 |
| `txns_last_1h` | DB velocity (1h window, strict <) | Cold-start = 0 |
| `txns_last_24h` | DB velocity (24h window, strict <) | Cold-start = 0 |

## 3. Feature Availability

Each feature carries an explicit `feature_availability` boolean in the assessment record. `False` means the feature fell back to a safe default. The model receives the default; the availability flag signals the downstream reviewer that the signal was unavailable.

## 4. Customer Identity Semantics

Identity priority (highest to lowest):
1. `payment.email` — directly from Razorpay
2. `payment.contact` — phone number from Razorpay
3. `notes.customer_id` — backend-injected at order creation

These are NOT silently merged. The first non-null value becomes `customer_id`. If none are available, the payment is rejected at normalization. Historical features are always keyed by this canonical `customer_id`.

## 5. Historical Feature Causality

DB query:
```sql
SELECT amount, timestamp FROM transactions
WHERE customer_id = ? AND timestamp < ?
ORDER BY timestamp ASC
```

The `<` (strict less-than) ensures the current transaction is never included in its own historical aggregates. This is enforced at the query level, not application logic.

## 6. Cold-Start Behavior

A customer with no prior transactions receives:
```json
{
  "previous_transaction_count": 0,
  "is_new_customer": 1,
  "avg_customer_amount": 0.0,
  "amount_deviation": 0.0,
  "amount_ratio": 1.0,
  "txns_last_1h": 0,
  "txns_last_24h": 0
}
```
Cold-start is a valid model input, not a fabrication.

## 7. Model Loading

At startup, `lifespan.py` loads:
- `ServingModelLoader("data/razorpay_serving_model_calibrated.joblib")`
- `ServingPolicyLoader("data/razorpay_serving_selected_policy.json")`
- `ServingSHAPExplainer("data/razorpay_serving_model_calibrated.joblib")`

`ServingPolicyLoader` explicitly validates `model_track == RAZORPAY_SERVING_MODEL`. Startup fails clearly if the artifacts are missing or have an incompatible track. The app never falls back to Model C for serving decisions.

## 8. Calibration

The `ServingModelLoader.predict_calibrated_proba(X)` applies:
1. Frozen `ColumnTransformer` (StandardScaler + OHE) — no refit
2. Frozen `XGBClassifier.predict_proba` → raw scores
3. Frozen `IsotonicRegression.predict` → calibrated risk [0, 1]

The calibration step is opaque to the policy.

## 9. Policy

`ServingPolicyLoader` loads `data/razorpay_serving_selected_policy.json`:
- `threshold_review`: 0.1213
- `threshold_block`: 0.2053

Decision rule:
- risk < 0.1213 → `ALLOW`
- 0.1213 ≤ risk < 0.2053 → `REVIEW`
- risk ≥ 0.2053 → `BLOCK`

## 10. Decision Behavior

| Condition | Decision | Reason |
|---|---|---|
| Normal scoring | per policy | `POLICY_THRESHOLD` |
| NaN/Inf risk | `REVIEW` | `RISK_UNAVAILABLE` |
| Model unavailable | `REVIEW` | `SERVING_MODEL_UNAVAILABLE` |
| Policy unavailable | `REVIEW` | `POLICY_UNAVAILABLE` |

Fail-closed: no `ALLOW` on failure.

## 11. SHAP Separation

SHAP is a read-only, asynchronous-safe explanation layer. It is:
- Never on the decision code path
- Never allowed to modify risk or decision
- Stored separately in `serving_assessments.shap_snapshot` after the decision is persisted
- Exposed only via the `/investigate` endpoint, explicitly labeled as `MODEL EXPLANATION` not `DECISION REASON`

## 12. Webhook Signature Validation

```python
expected_signature = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
if not hmac.compare_digest(expected_signature, signature):
    raise HTTPException(401, "Invalid signature.")
```
- Validated over **raw bytes** before any JSON parsing
- **Constant-time** comparison (`hmac.compare_digest`)
- Secrets are never logged

## 13. Idempotency

- Webhook deduplication via `x-razorpay-event-id` header (falls back to payload `id`)
- `check_event_already_processed()` queries `serving_assessments.event_id` before processing
- Duplicate events return the previously persisted decision without re-scoring or re-inserting history

## 14. Post-Event vs Pre-Event Semantics

RazorBrain operates in **Test Mode**. The webhook events `payment.captured` and `payment.authorized` arrive **after** Razorpay has already processed the payment. All assessments are explicitly typed as:

```json
{"assessment_type": "POST_EVENT_RISK_ASSESSMENT"}
```

This decision **cannot** retroactively block an already-authorized payment. It is a risk signal for downstream human review.

## 15. Audit Persistence

Every completed assessment persists:
```
assessment_id, transaction_id, event_id, assessment_type, model_track,
model_version, calibration_version, policy_version, timestamp, risk,
decision, decision_reason (JSON), feature_snapshot (JSON),
feature_availability (JSON), shap_snapshot (JSON), processing_status, created_at
```

The `model_track` column ensures serving and Model C assessments can never be mixed in analytics.

## 16. Ground-Truth Feedback

Feedback is recorded in the existing `evaluation_feedback` table. It does NOT alter:
- serving assessment decisions
- historical feature aggregates
- fraud labels used in feature engineering

`BLOCK` ≠ `FRAUD`. `ALLOW` ≠ `LEGITIMATE`. These are model decisions; fraud labels require explicit human submission with a `label_source`.

## 17. Test Mode Limitations

> [!CAUTION]
> RazorBrain uses Razorpay Test Mode. Test Mode payments are not real financial transactions. Test Mode events do not constitute real fraud labels. The serving model's performance on Test Mode data does not validate real-world fraud detection accuracy.

## 18. Failure Behavior

| Failure | Outcome | Behavior |
|---|---|---|
| Serving model artifact missing | startup warning | All serving txns → REVIEW |
| Policy artifact missing | startup warning | All serving txns → REVIEW |
| NaN/Inf risk at scoring | REVIEW | `RISK_UNAVAILABLE` |
| SHAP error | UNAVAILABLE status | Decision unchanged |
| DB persistence failure | exception | No silent data loss |
| Invalid webhook signature | HTTP 401 | Rejected before scoring |
| Duplicate event | HTTP 409 | No re-scoring, no history duplication |

## 19. Cross-Domain Limitations

> [!CAUTION]
> The serving model was trained on IEEE-CIS data derived from US e-commerce transactions. Its feature distributions, thresholds, and SHAP explanations reflect that domain — not Indian UPI/card payment patterns. The serving model does NOT claim to detect real Razorpay fraud. It is a Razorpay-compatible prototype demonstrating the architectural integration.
