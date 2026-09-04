# Razorpay Serving Model Feasibility Audit

> **Status**: ANALYSIS ONLY — no model training, no code changes to Model C or calibration artifacts.
>
> **Date**: 2026-09-04
>
> **Scope**: Determine whether a scientifically defensible serving model can operate on information genuinely available at Razorpay transaction scoring time.

---

## 1. Razorpay Test Mode Payload Structure

### 1.1 Order Creation (`POST /razorpay/test/orders`)

The merchant's backend sends:

| Field | Type | Example |
|---|---|---|
| `amount` | int (paise) | `50000` |
| `currency` | string | `"INR"` |
| `receipt` | string | `"order_receipt_123"` |
| `notes.customer_id` | string | `"cust_abc"` |
| `notes.merchant_id` | string | `"merch_xyz"` |

RazorBrain server-side injection at order creation:

| Injected Field | Source | Trust Level |
|---|---|---|
| `notes.ip_address` | `x-forwarded-for` header or `request.client.host` | SERVER-OBSERVED |
| `notes.session_id` | `x-session-id` header (max 36 chars) | HEADER-VALIDATED |
| `notes.customer_account_age_days` | Optional merchant-supplied | MERCHANT-DECLARED |

### 1.2 Payment Object (Webhook / Fetch)

When `payment.captured` or `payment.authorized` fires, the payload contains:

| Field | Path | Available |
|---|---|---|
| Payment ID | `payment.id` | YES |
| Amount (paise) | `payment.amount` | YES |
| Currency | `payment.currency` | YES |
| Method | `payment.method` | YES (card, netbanking, wallet, upi) |
| Email | `payment.email` | YES |
| Contact | `payment.contact` | YES |
| Order ID | `payment.order_id` | YES |
| Created At | `payment.created_at` | YES (Unix timestamp) |
| Notes | `payment.notes` | YES (immutable from order creation) |
| Card last4 | `payment.card.last4` | Conditional (card only) |
| Card network | `payment.card.network` | Conditional (card only) |
| Card type | `payment.card.type` | Conditional (card only) |
| Card issuer | `payment.card.issuer` | Conditional (card only) |
| Bank | `payment.bank` | Conditional (netbanking only) |
| Wallet | `payment.wallet` | Conditional (wallet only) |
| VPA | `payment.vpa` | Conditional (UPI only) |

### 1.3 Normalization Output

`normalize_razorpay_payment()` in `api/razorpay_adapter.py` produces a `TransactionRequest`:

| Output Field | Source | Mapping |
|---|---|---|
| `transaction_id` | `payment.id` | Direct |
| `timestamp` | `payment.created_at` | Unix to ISO-8601 |
| `amount` | `payment.amount / 100` | Paise to Rupees |
| `currency` | `payment.currency` | Direct |
| `customer_id` | `email or contact or notes.customer_id` | Fallback chain |
| `merchant_id` | `notes.merchant_id` | Required |
| `payment_method` | `payment.method` | Mapped: card=card, netbanking/upi=bank_transfer, wallet=wallet |
| `device_id` | `notes.session_id` | Optional (server-injected) |
| `ip_address` | `notes.ip_address` | Optional (server-injected) |
| `customer_account_age_days` | `notes.customer_account_age_days` | Optional (merchant-declared) |
| `assessment_id` | `order_id + "_" + payment.id` | Idempotency key |

---

## 2. Feature Availability Table

| Feature / Signal | Source | Before Auth? | At Webhook? | Persistent? | Reliable? | From DB? |
|---|---|---|---|---|---|---|
| **amount** | `payment.amount` | YES | YES | YES | YES | N/A |
| **currency** | `payment.currency` | YES | YES | YES | YES | N/A |
| **payment_method** | `payment.method` | NO (at auth) | YES | YES | YES | N/A |
| **customer_id** | `email/contact/notes` | YES | YES | YES | MEDIUM | N/A |
| **merchant_id** | `notes.merchant_id` | YES | YES | YES | YES | N/A |
| **timestamp** | `payment.created_at` | YES | YES | YES | YES | N/A |
| **ip_address** | Server-injected note | YES | YES | YES | YES | N/A |
| **session_id / device_id** | Header-validated note | YES | YES | YES | MEDIUM | N/A |
| **customer_account_age_days** | Merchant-declared note | YES | YES | YES | MEDIUM | Partial |
| **hour_of_day** | Derived from timestamp | YES | YES | YES | YES | Computed |
| **day_of_week** | Derived from timestamp | YES | YES | YES | YES | Computed |
| **previous_transaction_count** | RazorBrain DB query | NO | YES | YES | YES | YES |
| **is_new_customer** | RazorBrain DB query | NO | YES | YES | YES | YES |
| **avg_customer_amount** | RazorBrain DB query | NO | YES | YES | YES | YES |
| **amount_deviation** | RazorBrain DB query | NO | YES | YES | YES | YES |
| **txns_last_5min** | RazorBrain DB query | NO | YES | YES | YES | YES |
| **txns_last_1h** | RazorBrain DB query | NO | YES | YES | YES | YES |
| **txns_last_24h** | RazorBrain DB query | NO | YES | YES | YES | YES |
| **is_new_merchant** | RazorBrain DB query | NO | YES | YES | YES | YES |
| **merchant_fraud_rate** | DB + feedback | NO | YES | YES | MEDIUM | YES |
| **previous_fraud_count** | DB + feedback | NO | YES | YES | MEDIUM | YES |
| **ip_is_missing** | Derived from ip_address | YES | YES | YES | YES | Computed |
| **card.network** | Razorpay (card only) | NO | YES | YES | YES | N/A |
| **card.type** | Razorpay (card only) | NO | YES | YES | YES | N/A |
| **V-series (V95-V321)** | IEEE-CIS only | NO | NO | NO | N/A | NO |
| **id-series (id_01-id_38)** | IEEE-CIS only | NO | NO | NO | N/A | NO |
| **D-series (D1, D10, D15)** | IEEE-CIS only | NO | NO | NO | N/A | NO |
| **card1-card6** | IEEE-CIS only | NO | NO | NO | N/A | NO |
| **addr1, addr2** | IEEE-CIS only | NO | NO | NO | N/A | NO |
| **M-series** | IEEE-CIS only | NO | NO | NO | N/A | NO |
| **P_emaildomain** | Derivable from email | NO | YES | YES | YES | Computed |
| **DeviceType** | IEEE-CIS only | NO | NO | NO | N/A | NO |

---

## 3. Razorpay-Serving Feature Catalog

### 3.1 AVAILABLE - Directly from payload + DB

| # | Feature | Source | Computation |
|---|---|---|---|
| 1 | `amount` | `payment.amount / 100` | Direct |
| 2 | `log_amount` | `ln(1 + amount)` | Derived |
| 3 | `currency` | `payment.currency` | Direct |
| 4 | `payment_method` | `payment.method` mapped | Direct |
| 5 | `hour_of_day` | `timestamp.hour` | Derived |
| 6 | `day_of_week` | `timestamp.dayofweek` | Derived |
| 7 | `ip_is_missing` | `ip_address is None` | Derived |
| 8 | `email_domain` | `email.split("@")[1]` | Derived |
| 9 | `email_domain_missing` | `email is None` | Derived |
| 10 | `previous_transaction_count` | SQLite query | DB aggregation |
| 11 | `is_new_customer` | `previous_transaction_count == 0` | DB derived |
| 12 | `avg_customer_amount` | Cumulative mean of prior amounts | DB aggregation |
| 13 | `amount_deviation` | `abs(amount - avg_customer_amount)` | DB derived |
| 14 | `amount_ratio` | `amount / avg_customer_amount` | DB derived |
| 15 | `txns_last_5min` | Rolling count from DB | DB aggregation |
| 16 | `txns_last_1h` | Rolling count from DB | DB aggregation |
| 17 | `txns_last_24h` | Rolling count from DB | DB aggregation |
| 18 | `is_new_merchant` | `merchant prior count == 0` | DB aggregation |
| 19 | `customer_account_age_days` | First-seen timestamp or merchant-declared | DB / notes |

### 3.2 CONDITIONALLY_AVAILABLE - Requires merchant cooperation or specific payment method

| # | Feature | Condition | Reliability |
|---|---|---|---|
| 20 | `card_network` | Card payments only | HIGH |
| 21 | `card_type` (credit/debit) | Card payments only | HIGH |
| 22 | `card_issuer` | Card payments only | MEDIUM |
| 23 | `session_id` (device proxy) | Merchant passes x-session-id header | MEDIUM |
| 24 | `ip_address` | Server-injected at order creation | HIGH |
| 25 | `previous_fraud_count` | Requires labeled feedback in DB | LOW (cold start) |
| 26 | `merchant_fraud_rate` | Requires labeled feedback in DB | LOW (cold start) |
| 27 | `customer_merchant_interaction_count` | DB history | MEDIUM |

### 3.3 UNAVAILABLE - Cannot be obtained from Razorpay

| Feature Family | Count | Reason |
|---|---|---|
| V-series (V95-V137, V279-V321) | 86 | Vesta proprietary internal features |
| id-series (id_01-id_38) | 21 | IEEE-CIS identity table device fingerprinting |
| D-series (D1, D10, D15) | 3 | Anonymous timedelta proxies |
| card1-card6 | 6 | IEEE-CIS anonymous card proxies (not same as Razorpay card fields) |
| addr1, addr2 | 2 | IEEE-CIS billing region proxies |
| M-series (M4, M6) | 2 | Anonymous match flags |
| dist1 | 1 | Anonymous distance proxy |
| DeviceType | 1 | IEEE-CIS identity table field |
| ProductCD | 1 | IEEE-CIS product category |
| R_emaildomain | 1 | Recipient email domain |

**Total UNAVAILABLE: ~124 of Model C's 147 source features.**

### 3.4 POST_EVENT_ONLY

| Signal | Why Post-Event |
|---|---|
| `payment.captured` webhook | Authorization already completed |
| `chargeback` feedback | Arrives 30-90 days after transaction |
| `MANUAL_REVIEW` label | Requires analyst action after scoring |

### 3.5 REJECTED

| Feature | Reason |
|---|---|
| `isFraud` / `is_fraud` | Target label - pure leakage |
| `TransactionID` | Row identifier |
| `TransactionDT` | Raw time delta (use derived features) |
| V138-V278, V322-V339 | 84-86% missing - rejected |
| D6, D7, D8, D9, D12, D13, D14 | 87-97% missing |
| id_07, id_08, id_21-id_27 | 96%+ missing |

---

## 4. Cross-Dataset Knowledge Mapping

These datasets provide fraud-pattern concepts ONLY - they are never merged into training rows.

| Concept | IEEE-CIS | BankSim | CreditCard2023 | fraud_dataset | Razorpay Serving |
|---|---|---|---|---|---|
| **Amount anomaly** | TransactionAmt | amount | Amount | amount | AVAILABLE |
| **Entity velocity** | card1 + TransactionDT | Customer txn freq | N/A (PCA) | txn_frequency | AVAILABLE |
| **Temporal patterns** | TransactionDT | step | N/A | transaction_time | AVAILABLE |
| **New entity** | entity_is_new | First-seen | N/A | is_first_transaction | AVAILABLE |
| **Payment method** | card4, card6 | category | N/A | payment_method | PARTIAL |
| **Email domain** | P_emaildomain | N/A | N/A | N/A | AVAILABLE |
| **Device fingerprint** | id_01-id_38 | N/A | N/A | device_type | UNAVAILABLE |
| **Location mismatch** | addr1, addr2, dist1 | zipcodeOri/zipMerchant | N/A | unusual_location_flag | UNAVAILABLE |
| **Behavioral biometrics** | N/A | N/A | N/A | pin_entry_speed, otp_timing | UNAVAILABLE |
| **Network/graph** | N/A | bsNET node degrees | N/A | N/A | UNAVAILABLE |
| **Merchant fraud history** | isFraud aggregation | fraud rate per merchant | N/A | merchant_fraud_history | COLD START |

---

## 5. Historical State Feasibility from RazorBrain's Database

### 5.1 Currently Implemented

`get_live_historical_features()` in `database/repository.py` already computes from SQLite:

| Feature | Query Pattern | Temporal Safety |
|---|---|---|
| `previous_transaction_count` | COUNT WHERE customer_id = ? AND timestamp < ? | Strictly prior |
| `is_new_customer` | count == 0 | Strictly prior |
| `avg_customer_amount` | AVG(amount) WHERE customer_id = ? AND timestamp < ? | Strictly prior |
| `amount_deviation` | abs(current - avg) | Strictly prior |
| `txns_last_5min` | Rolling window count | Strictly prior |
| `txns_last_1h` | Rolling window count | Strictly prior |
| `txns_last_24h` | Rolling window count | Strictly prior |
| `is_new_merchant` | COUNT WHERE merchant_id = ? AND timestamp < ? | Strictly prior |
| `merchant_fraud_rate` | Labeled rows only, labeled_at <= current_timestamp | Strictly prior |
| `previous_fraud_count` | Fraud labels with labeled_at <= current_timestamp | Strictly prior |
| `customer_account_age_days` | First-seen or merchant-declared | Strictly prior |

### 5.2 Additional Feasible Features (Not Yet Implemented)

| Feature | Feasibility | Implementation |
|---|---|---|
| `customer_merchant_interaction_count` | YES | COUNT WHERE customer AND merchant AND timestamp < ? |
| `time_since_last_txn` | YES | MAX(timestamp) WHERE customer_id = ? AND timestamp < ? |
| `amount_ratio` | YES | current_amount / avg_customer_amount |
| `customer_amount_stddev` | YES | STDEV(amount) from prior transactions |
| `distinct_merchant_count_24h` | YES | COUNT(DISTINCT merchant_id) in window |
| `distinct_ip_count_24h` | YES | Requires storing IP in transactions table |

### 5.3 Cold Start Problem

**WARNING**: All DB-computed historical features return zero/default for the first transaction from a new customer or merchant. The serving model must be robust to cold-start scenarios where most historical features are zero.

---

## 6. PRE_EVENT vs POST_EVENT Classification

| Timing | What Happens | Scoring Feasibility |
|---|---|---|
| **Order Creation** (POST /orders) | Amount, currency, customer_id, merchant_id, IP, session_id known | PRE-AUTH scoring possible with amount + identity + IP |
| **Checkout** (client-side) | User selects payment method | Server has no visibility |
| **Authorization** (Razorpay internal) | Payment method resolved, card details captured | RazorBrain not in authorization path |
| **payment.authorized webhook** | Full payment object available | POST-AUTH - authorization already granted |
| **payment.captured webhook** | Payment captured | POST-CAPTURE - money moved |
| **Chargeback** (30-90 days later) | Ground truth label | POST-EVENT only - label, not feature |

**IMPORTANT**: Current Razorpay integration is POST-EVENT. Webhook-triggered scoring happens after authorization. True pre-authorization blocking would require Razorpay to call RazorBrain during the authorization flow (not currently supported in Test Mode).

The system can still provide value as:
- Post-event risk triage for manual review queues
- Merchant dashboard alerting
- Feedback-driven model improvement
- Pattern detection for future pre-auth integration

---

## 7. Label / Ground-Truth Availability

### 7.1 Current Feedback Mechanism

The system supports ground-truth ingestion via:

```
POST /transactions/{assessment_id}/feedback
{
  "ground_truth": "FRAUD" | "LEGITIMATE",
  "label_source": "MANUAL_REVIEW" | "CHARGEBACK" | "CUSTOMER_REPORT",
  "notes": "optional context"
}
```

Stored in `evaluation_feedback` table with `labeled_at` timestamp.

### 7.2 Label Sources

| Source | Delay | Reliability | Volume |
|---|---|---|---|
| Manual analyst review | Minutes-hours | HIGH | Limited by capacity |
| Chargeback notification | 30-90 days | HIGH | Low (only disputed txns) |
| Customer self-report | Variable | MEDIUM | Very low |
| Automated rules | Real-time | LOW (circular) | High |

### 7.3 Label Availability for Training

**CAUTION**: In Test Mode, there are NO real fraud labels. All transactions are simulated. The evaluation_feedback table will contain only analyst-supplied labels for test transactions.

A Razorpay-serving model cannot be trained on Razorpay Test Mode data because:
1. No real fraud occurs in test mode
2. Labels would be fabricated, not genuine
3. Transaction patterns are artificial

---

## 8. Training Data Options

### Option A: IEEE-CIS Subset (Feature-Restricted)

Train on IEEE-CIS data using ONLY the ~19-23 features that have Razorpay analogs.

| Aspect | Assessment |
|---|---|
| **Available features** | TransactionAmt, P_emaildomain, temporal features, some card features |
| **Dropped features** | V-series (86), id-series (21), D-series, addr, M-series - ~124 features |
| **Expected performance** | Significantly degraded vs Model C (ROC-AUC 0.87). Likely ROC-AUC 0.70-0.78 |
| **Leakage safety** | Same temporal split methodology |
| **Label quality** | Real Vesta fraud labels |
| **Domain alignment** | IEEE-CIS is US e-commerce; Razorpay is India payments |
| **Verdict** | **VIABLE as research baseline, NOT production-grade** |

### Option B: Synthetic/Other Dataset Training

| Dataset | Verdict |
|---|---|
| BankSim | REJECTED - Synthetic rule-based fraud, no adversarial signal |
| CreditCard2023 | REJECTED - PCA features impossible to align |
| fraud_dataset | REJECTED - Simulated with fabricated behavioral biometrics |
| **All cross-datasets** | **REJECTED for training - concept sources only** |

### Option C: Future Razorpay Production Feedback Loop

| Aspect | Assessment |
|---|---|
| **Feasibility** | Requires real production deployment, real transactions, real chargebacks |
| **Timeline** | 3-6 months minimum to accumulate sufficient labeled data |
| **Label quality** | Real fraud (chargebacks) |
| **Volume** | Depends on merchant adoption |
| **Cold start** | Bootstrap with IEEE-CIS feature-restricted model |
| **Verdict** | **IDEAL long-term path - requires production commitment** |

### Option D: Hybrid Bootstrap (RECOMMENDED)

1. Train feature-restricted model on IEEE-CIS (Option A)
2. Deploy in shadow/scoring mode on Razorpay
3. Collect labeled feedback over time
4. Fine-tune or retrain on real Razorpay data when sufficient labels exist
5. Evaluate with proper held-out split

**Verdict: RECOMMENDED approach for buildathon demonstration.**

---

## 9. Semantic Alignment Analysis

### DIRECTLY_ALIGNED (Exact semantic match)

| IEEE-CIS Feature | Razorpay Equivalent | Confidence |
|---|---|---|
| `TransactionAmt` | `payment.amount / 100` | HIGH |
| `P_emaildomain` | `payment.email.split("@")[1]` | HIGH |
| Time-of-day (from TransactionDT) | `payment.created_at` hour | HIGH |
| Day-of-week (from TransactionDT) | `payment.created_at` weekday | HIGH |

### CONCEPTUALLY_ALIGNED (Same concept, different representation)

| IEEE-CIS Concept | Razorpay Equivalent | Gap |
|---|---|---|
| `card1` (entity proxy) | `customer_id` (email/contact) | Different entity resolution |
| `card4` (card network) | `payment.card.network` | Only for card payments |
| `card6` (credit/debit) | `payment.card.type` | Only for card payments |
| `entity_txn_count_*` | `txns_last_*` from DB | Different entity key |
| `entity_avg_amount_24h` | `avg_customer_amount` from DB | Different entity key |
| `ProductCD` | No Razorpay equivalent | No equivalent |

### UNALIGNED (No Razorpay equivalent)

| IEEE-CIS Feature | Reason |
|---|---|
| V95-V321 (86 features) | Proprietary Vesta device/risk signals |
| id_01-id_38 (21 features) | Identity table browser/device fingerprinting |
| D1, D10, D15 | Anonymous timedelta proxies |
| addr1, addr2 | Billing address proxies |
| dist1 | Distance proxy |
| M4, M6 | Anonymous match flags |
| DeviceType | Device classification from identity table |

**Summary**: Only ~23 of 147 Model C source features have direct or conceptual Razorpay equivalents. The remaining ~124 are UNALIGNED.

---

## 10. Performance / Latency Estimation

### 10.1 Feature Computation Latency

| Component | Estimated Latency | Notes |
|---|---|---|
| Payload parsing + normalization | <1ms | In-memory |
| SQLite historical feature query | 5-50ms | Depends on table size, indexed |
| Velocity window computation | 10-30ms | Multiple timestamp comparisons |
| Feature vector assembly | <1ms | In-memory |
| **Total feature computation** | **15-80ms** | |

### 10.2 Model Inference Latency

| Component | Estimated Latency | Notes |
|---|---|---|
| XGBoost predict_proba | 1-5ms | 100 trees, small feature set |
| Platt calibration | <1ms | Logistic regression transform |
| SHAP explanation (if requested) | 50-200ms | TreeExplainer, optional |
| Decision policy evaluation | <1ms | Threshold comparison |
| **Total inference** | **2-10ms** (without SHAP) | |

### 10.3 Database Persistence

| Component | Estimated Latency | Notes |
|---|---|---|
| Transaction + assessment + decision INSERT | 5-20ms | SQLite WAL mode |
| Event deduplication check | 1-5ms | Indexed lookup |
| **Total persistence** | **6-25ms** | |

### 10.4 End-to-End Estimate

| Scenario | Total Latency |
|---|---|
| Scoring without SHAP | **25-115ms** |
| Scoring with SHAP | **75-315ms** |
| Razorpay webhook P99 target | <500ms |
| **Feasibility** | Well within budget |

SQLite is adequate for buildathon demonstration volumes. Production scaling would require PostgreSQL or Redis for historical feature lookups.

---

## 11. Serving Model Architecture

### 11.1 Proposed Scoring Chain

```
Razorpay webhook / assess endpoint
        |
normalize_razorpay_payment()
        |
get_live_historical_features() - SQLite
        |
Feature vector assembly (~19-23 features)
        |
Serving Model (NOT Model C) - feature-restricted XGBoost
        |
Serving Model's OWN Platt calibration
        |
Serving Model's OWN calibrated risk probability
        |
Serving Model's OWN threshold policy
        |
ALLOW / REVIEW / BLOCK
        |
Serving Model's OWN SHAP evidence
        |
Database persistence + audit
```

**IMPORTANT**: The serving model MUST have its OWN:
- Calibration artifact (NOT Model C's model_c_calibrated.joblib)
- Threshold policy (NOT Model C's validation_selected_policy.json)
- SHAP explainer (NOT Model C's TreeExplainer)
- Held-out evaluation (NOT Model C's frozen test ROC-AUC=0.8663)

Model C remains the IEEE-CIS research/benchmark model. The serving model is a separate, independently validated artifact.

### 11.2 Coexistence with Model C

| Aspect | Model C (Benchmark) | Serving Model (Production) |
|---|---|---|
| Training data | Full IEEE-CIS (147 features) | IEEE-CIS feature-restricted (~23 features) |
| Serving context | Offline research/evaluation | Live Razorpay transactions |
| Feature contract | 147 -> 438 transformed | ~23 -> TBD transformed |
| Artifact | model_c_calibrated.joblib (FROZEN) | New artifact (TBD) |
| Test evaluation | ROC-AUC=0.8663 (FROZEN) | Independent held-out eval |
| Status | COMPLETE | NOT YET TRAINED |

---

## 12. Risk Assessment

### 12.1 What We Gain

1. **Honest ML scoring** on real Razorpay transactions (instead of FEATURE_CONTRACT_UNAVAILABLE blanket REVIEW)
2. **Evidence-based decisions** with genuine SHAP explanations
3. **Velocity detection** from DB-computed historical features
4. **Amount anomaly detection** from customer spending baselines
5. **Temporal pattern detection** from hour/day features
6. **Progressive learning** via feedback loop

### 12.2 What We Lose vs Model C

1. **V-series signal** (~54% of Model C's predictive weight) - UNAVAILABLE
2. **Identity/device fingerprinting** - UNAVAILABLE
3. **Address/distance features** - UNAVAILABLE
4. **Expected performance degradation**: ROC-AUC likely 0.70-0.78 vs Model C's 0.87

### 12.3 Honest Limitations

**CAUTION**:
- A feature-restricted model trained on IEEE-CIS and deployed on Razorpay data operates across a **domain shift** (US e-commerce to India payments)
- Historical features suffer **cold start** - new customers/merchants have zero history
- Label availability in test mode is **zero** - no real fraud to learn from
- The model cannot detect sophisticated fraud patterns that rely on device/identity signals
- Performance claims must be qualified: "Evaluated on IEEE-CIS held-out test with restricted features; real-world Razorpay performance is unmeasured"

---

## 13. Feasibility Verdict

| Criterion | Assessment |
|---|---|
| Can a model score Razorpay transactions? | YES - ~19-23 features available |
| Can it use Model C directly? | NO - 124/147 features missing |
| Can it achieve Model C's performance? | NO - V-series/id-series unavailable |
| Is it scientifically defensible? | YES - if properly evaluated on restricted features |
| Is feature computation feasible in real-time? | YES - <115ms end-to-end |
| Are training labels available? | PARTIAL - IEEE-CIS labels only; no Razorpay labels |
| Is it honest about limitations? | YES - domain shift and cold start acknowledged |
| Does it require modifying Model C? | NO - separate artifact |
| **Overall verdict** | **FEASIBLE with significant, documented limitations** |

---

## 14. Recommendations

1. **DO NOT modify Model C** - it remains the IEEE-CIS research benchmark with frozen test ROC-AUC=0.8663

2. **Train a feature-restricted serving model** on IEEE-CIS using only the ~23 features that have Razorpay analogs (Option A / Option D hybrid)

3. **Give it its own calibration, thresholds, SHAP, and held-out evaluation** - completely independent from Model C

4. **Deploy in shadow mode** on Razorpay Test Mode for demonstration

5. **Document the domain shift** honestly - IEEE-CIS training vs Razorpay serving

6. **Implement the feedback loop** for future real-label training (Option C)

7. **Do not claim Model C's performance** for the serving model - evaluate independently

8. **Keep FEATURE_CONTRACT_UNAVAILABLE fallback** as a safety net for any future model that cannot satisfy its feature contract

9. **Consider the serving model a v0.1 prototype** - real performance measurement requires real Razorpay production data with real fraud labels

10. **For the buildathon**, present this as a two-model architecture:
    - Model C: IEEE-CIS benchmark demonstrating ML methodology rigor
    - Serving Model: Razorpay-deployable prototype demonstrating production integration
