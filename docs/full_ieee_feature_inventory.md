# Full IEEE-CIS Feature Inventory

## Summary Counts

| Pool | Count | Description |
|---|---|---|
| **ENGINEERED_CORE** | **22** | Deliberately constructed fraud signals (strictly-prior temporal safety) |
| **RAW_SAFE** | **125** | Original IEEE-CIS columns passing leakage/temporal/semantic screening |
| **RAW_RESEARCH** | **78** | Columns requiring further semantic or serving investigation |
| **REJECTED** | **6 groups** | Excluded: high-null V-series, near-empty D/id groups, target, identifiers |
| **OFFLINE RESEARCH** | 1 | entity_fraud_rate_30d_delay (label-derived, delayed) |

**Total IEEE-CIS source columns inspected:** 434 (394 transaction + 41 identity − 1 shared key)

---

## POOL A — ENGINEERED_CORE (22 features)

All features are temporally safe: rolling aggregates use shift(1) + rolling window to guarantee the current row is excluded from its own history.

| Feature | Source | Semantic |
|---|---|---|
| `log_amount` | TransactionAmt | Log-scaled amount; compresses long tail |
| `time_of_day_proxy` | TransactionDT | Pseudo hour-of-day (0–23) |
| `day_of_week_proxy` | TransactionDT | Pseudo day-of-week (0–6) |
| `time_since_last_txn` | card1 + TransactionDT | Seconds since entity's last prior transaction |
| `entity_is_new` | time_since_last_txn | 1 if no prior history within 180 days |
| `entity_txn_count_1h` | card1 + TransactionDT | Strictly-prior 1h rolling count |
| `entity_txn_count_24h` | card1 + TransactionDT | Strictly-prior 24h rolling count |
| `entity_txn_count_7d` | card1 + TransactionDT | Strictly-prior 7d rolling count |
| `entity_avg_amount_24h` | card1 + TransactionAmt + TransactionDT | Strictly-prior 24h rolling mean |
| `entity_amount_sum_24h` | card1 + TransactionAmt + TransactionDT | Strictly-prior 24h rolling sum |
| `entity_velocity_24h_7d` | entity_txn_count_24h / entity_txn_count_7d | 24h-to-7d ratio — sudden spike detector |
| `amount_deviation` | TransactionAmt − entity_avg_amount_24h | Raw anomaly from historical baseline |
| `amount_relative_24h` | TransactionAmt / entity_avg_amount_24h | Relative anomaly from historical baseline |
| `email_suffix` | P_emaildomain | TLD extracted from purchaser email |
| `network_product_combo` | card4 + ProductCD | Card-network × product-type interaction |
| `email_domain_missing` | P_emaildomain | Binary: email domain absent |
| `billing_region_missing` | addr1 | Binary: billing region absent |
| `card_country_missing` | card5 | Binary: card country absent |
| `recipient_email_missing` | R_emaildomain | Binary: recipient email absent (82% missing) |
| `dist1_missing` | dist1 | Binary: distance proxy absent (66% missing) |
| `identity_present` | id_01 presence | Binary: transaction has identity record |
| `m_match_count` | M1–M9 | Count of non-null M-series flags |

---

## POOL B — RAW_SAFE (125 columns)

### Transaction metadata (12)
`TransactionAmt`, `ProductCD`,
`card1`, `card2`, `card3`, `card4`, `card5`, `card6`,
`addr1`, `addr2`, `dist1`,
`P_emaildomain`, `R_emaildomain`

### D-series — low/moderate missing (3 columns)
`D1` (0% null), `D10` (16% null), `D15` (42% null)

### M-series — match flags (2 columns)
`M4` (52% null), `M6` (29% null)

### Identity columns — low missing (18 columns)
`id_01`, `id_02`, `id_05`, `id_06`, `id_11`, `id_12`, `id_13`, `id_14`,
`id_15`, `id_16`, `id_17`, `id_19`, `id_20`,
`id_28`, `id_29`, `id_31`, `id_35`, `id_36`, `id_37`, `id_38`, `DeviceType`

### V-series — 0% missing groups (86 columns)
- **V95–V137** (43 cols): 0% null — anonymous numerical Vesta features
- **V279–V321** (43 cols): 0% null — anonymous numerical Vesta features

> **LEAKAGE NOTE**: V-series semantics are opaque. Their construction by Vesta is undocumented. However, the 0%-missing groups are present for every transaction at scoring time and cannot be clearly established as post-event. They are admitted as RAW_SAFE with UNKNOWN semantic confidence. Model training will reveal whether they carry leakage signal through abnormally high importance or train/val gap.

---

## POOL C — RAW_RESEARCH (78 columns)

| Group | Count | Reason for Research status |
|---|---|---|
| C-series (C1–C14) | 14 | 0% null but rolling semantics may aggregate future rows |
| D-series (D2–D5) | 4 | 44–68% null, unknown timedelta semantics |
| M-series (M1,M2,M3,M5,M7,M8,M9) | 7 | 60–79% null |
| dist2 | 1 | 95% null |
| Identity (id_03,id_04,id_09,id_10,id_18,id_30,id_32,id_33,id_34) | 9 | 28–70% null |
| DeviceInfo | 1 | 12% null but very high cardinality (638 unique values) |
| V53–V94 | 42 | 49% null — moderate sparsity |

---

## REJECTED / EXCLUDED

| Group | Reason |
|---|---|
| `isFraud` | Target label — pure leakage |
| `TransactionID` | Row identifier |
| `TransactionDT` | Raw ordering signal; used only for derived features |
| V138–V278 (84–86% null) | Near-empty; model would see zeros for >84% of rows |
| V322–V339 (86% null) | Same |
| D6,D7,D8,D9,D12,D13,D14 (>87% null) | Near-empty |
| id_07,id_08,id_21–id_27 (>96% null) | Effectively absent |

---

## Feature Family Counts

| Family | RAW_SAFE | RAW_RESEARCH | REJECTED |
|---|---|---|---|
| V-series | 86 | 42 | 211 |
| C-series | 0 | 14 | 0 |
| D-series | 3 | 4 | 7 |
| M-series | 2 | 7 | 0 |
| card* | 6 | 0 | 0 |
| addr* | 2 | 0 | 0 |
| dist* | 1 | 1 | 0 |
| email | 2 | 0 | 0 |
| id_* | 18 | 9 | 7 |
| Device* | 1 | 1 | 0 |
| Transaction metadata | 2 | 0 | 2 |

---

## Encoding Strategy

### Categorical columns (low cardinality ≤ 100 unique)
- Fit `OneHotEncoder(handle_unknown='ignore')` on **training data only**
- Unknown values at validation/test → all-zero row (safe, no data leakage)
- Columns: `ProductCD`, `card4`, `card6`, `P_emaildomain`, `R_emaildomain`, `id_12`, `id_15`, `id_16`, `id_28`, `id_29`, `id_35`, `id_36`, `id_37`, `id_38`, `DeviceType`, `M4`, `M6`, `email_suffix`, `network_product_combo`

### Categorical columns (high cardinality > 100 unique)
- `card1` (3192 unique), `card2` (470), `id_02`, `DeviceInfo` (638): use **frequency encoding** — but **only from training split statistics**, mapped at inference time with an `UNKNOWN` fallback
- Alternatively: treat as numeric by direct value passthrough (XGBoost handles integers)

### Numerical columns
- `SimpleImputer(strategy='constant', fill_value=0)` — appropriate since many are counts where missing naturally corresponds to zero activity
- `StandardScaler` fit on training data only

### Estimated transformed model-matrix dimension
- ENGINEERED_CORE (22 features): ~22 numeric + ~80–120 OHE columns for categoricals → **~140–160**
- RAW_SAFE addition (125 cols): ~86 V-series numeric + ~39 other cols → **+125–200 (after OHE of categoricals)**
- **Estimated total matrix dimension with ENGINEERED_CORE + RAW_SAFE: ~265–360 columns**

---

## Cross-Dataset Fraud Concepts Mapped to IEEE-CIS

| Source Concept | Dataset | IEEE-CIS Implementation |
|---|---|---|
| Transaction velocity | BankSim | `entity_txn_count_1h/24h/7d` |
| Sudden frequency spike | BankSim / Fraud dataset | `entity_velocity_24h_7d` |
| Amount anomaly | All datasets | `amount_deviation`, `amount_relative_24h` |
| First-time entity | BankSim | `entity_is_new` |
| Missing identity | Fraud dataset | `identity_present`, `m_match_count` |
| Missing telemetry = suspicious | Fraud dataset | `email_domain_missing`, `dist1_missing` |
| Location mismatch | BankSim | addr1/addr2/dist1 (proxy only — no GPS) |
| Device novelty | Fraud dataset | `DeviceType`, `id_31` (browser) |
| Card-product risk combination | CreditCard2023 pattern | `network_product_combo` |

## Concepts That Could NOT Be Represented

| Concept | Reason |
|---|---|
| Exact geolocation mismatch | No GPS/IP coordinates in IEEE-CIS or Razorpay standard webhook |
| Behavioral biometrics (keystroke, OTP speed) | Not observable without client-side SDK |
| Real-time merchant reputation | No merchant dimension in IEEE-CIS |
| Graph centrality / network relationships | BankSim-only structure; not reconstructable from IEEE-CIS |
