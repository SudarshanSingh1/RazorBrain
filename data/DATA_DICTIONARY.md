# RazorBrain Data Dictionary

This document is the authoritative data contract for a transaction flowing
through the RazorBrain risk pipeline.

All fields are defined in `data/schema.py` using Pydantic.  This document
serves as the human-readable companion to the code-level schema.

---

## Field Reference

| Field | Type | Role | Constraints | Notes |
|---|---|---|---|---|
| `transaction_id` | `str` | Identifier | Non-empty | Unique transaction reference. Not a model feature. |
| `customer_id` | `str` | Identifier | Non-empty | Customer reference. Use frequency encoding if used as a feature. |
| `merchant_id` | `str` | Identifier | Non-empty | Merchant reference. Use frequency encoding if used as a feature. |
| `device_id` | `str` | Identifier | Non-empty | Device reference for the session. |
| `ip_address` | `str \| None` | Identifier | Optional | May be None (card-present, VPN, unavailable). |
| `timestamp` | `datetime` | Transaction-time | Timezone-aware | UTC required. Used for time-based splits and velocity. |
| `amount` | `float` | Transaction-time | ≥ 0 | Transaction value in base currency. |
| `payment_method` | `PaymentMethod` | Transaction-time | Enum | `card`, `bank_transfer`, `wallet`, `crypto`. |
| `location` | `str \| None` | Transaction-time | Optional | Coarse label (city/country). None when unavailable. |
| `customer_account_age_days` | `int` | Historical | ≥ 0 | Age of the account on the day of the transaction. |
| `previous_transaction_count` | `int` | Historical | ≥ 0 | Count of prior completed transactions. Excludes current. |
| `previous_fraud_count` | `int` | Historical | ≥ 0 | Confirmed fraud events prior to this transaction. Excludes current. |
| `failed_attempt_count_24h` | `int` | Historical | ≥ 0 | Failed payment attempts by the customer in the prior 24 hours. |
| `txns_last_5min` | `int` | Historical | ≥ 0 | Transaction velocity: prior 5 minutes. |
| `txns_last_1h` | `int` | Historical | ≥ 0 | Transaction velocity: prior 1 hour. |
| `txns_last_24h` | `int` | Historical | ≥ 0 | Transaction velocity: prior 24 hours. |
| `avg_customer_amount` | `float` | Historical | ≥ 0 | Mean transaction amount over the customer's prior history. Zero for new accounts. |
| `amount_deviation` | `float` | Historical | ≥ 0 | `abs(amount − avg_customer_amount)`. Zero when no prior history. |
| `merchant_fraud_rate` | `float` | Historical | [0, 1] | Estimated fraud rate for the merchant from **prior** transactions only. |
| `new_device_flag` | `bool` | Transaction-time | — | True if `device_id` is new for this customer. |
| `new_location_flag` | `bool` | Transaction-time | — | True if `location` is new for this customer. |
| `is_fraud` | `bool` | **TARGET** | — | Supervised learning label. **Must never be used as a model feature.** |

---

## Field Role Definitions

| Role | Meaning |
|---|---|
| Identifier | Entity reference. Not a predictive feature by default. |
| Transaction-time | Information present at the moment of evaluation. Safe as a feature. |
| Historical | Aggregate computed from events **before** this transaction. Safe as a feature if leakage rules are followed. |
| **TARGET** | The value the model is trained to predict. Excluded from all feature sets. |

---

## Leakage Rules

The following must hold throughout the entire pipeline:

1. `is_fraud` for the **current** transaction must not appear in any feature set.
2. `previous_fraud_count` must not include the current transaction's label.
3. `merchant_fraud_rate` must be computed from transactions **prior** to the
   current one (time-ordered or entity-level pre-computation).
4. All `txns_last_*` and `failed_attempt_count_24h` windows refer to the time
   **before** `timestamp` of the current transaction.

Violation of any of these rules constitutes target leakage and will produce
optimistic but unreliable model performance on held-out data.

---

## Missing Data Policy

- Fields typed `Optional[X]` may be `None` when the information is genuinely
  unavailable.
- Missing values are **not** silently filled at the schema layer.
- Downstream imputation, confidence adjustment, and review-routing for missing
  data are handled by the **feature engineering** layer.
- A missing value should reduce system confidence or route the transaction
  toward **Review**, never crash the pipeline.

---

## Feature / Target Separation

Use the helpers on `Transaction` to avoid accidentally including the target
in a feature matrix:

```python
from data.schema import Transaction

feature_cols = Transaction.feature_columns()   # list of safe feature names
target_col   = Transaction.target_column()     # "is_fraud"

X = df[feature_cols]
y = df[target_col]
```
