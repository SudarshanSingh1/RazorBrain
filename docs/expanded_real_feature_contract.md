# Expanded Real Feature Contract (IEEE-CIS)

## 1. ENGINEERED PRODUCTION CANDIDATES
- `log_amount`: Log-scaled transaction amount.
- `time_of_day_proxy`: Cyclical hour-of-day proxy (derived from TransactionDT).
- `day_of_week_proxy`: Cyclical day-of-week proxy (derived from TransactionDT).
- `time_since_last_txn`: Time in seconds since the entity's (`card1`) last transaction.
- `entity_txn_count_1h`: Strictly prior rolling 1-hour transaction count for the entity.
- `entity_txn_count_24h`: Strictly prior rolling 24-hour transaction count for the entity.
- `entity_txn_count_7d`: Strictly prior rolling 7-day transaction count for the entity.
- `entity_avg_amount_24h`: Strictly prior rolling 24-hour average transaction amount for the entity.
- `entity_amount_sum_24h`: Strictly prior rolling 24-hour sum of transaction amounts for the entity.
- `entity_velocity_24h_7d`: Ratio of 24h count to 7d count, representing sudden frequency spikes.
- `entity_is_new`: Indicator if the entity has no history (or history older than 180 days).
- `amount_deviation`: Deviation of the current amount from the entity's 24h average.
- `amount_relative_24h`: Ratio of the current amount relative to the entity's 24h average.
- `email_domain_missing`: Indicator variable for absent purchaser email domain.
- `billing_region_missing`: Indicator variable for absent billing region (`addr1`).
- `card_country_missing`: Indicator variable for absent card-issuing country (`card5`).
- `email_suffix`: Extracted TLD (e.g., `.com`, `.net`) from `P_emaildomain`.
- `network_product_combo`: Interaction string combining payment network and product type.

## 2. RAW APPROVED CANDIDATES
- `amount`: Raw `TransactionAmt`.
- `product_type`: `ProductCD`.
- `card_network`: `card4`.
- `card_type`: `card6`.
- `card_issuer_proxy`: `card3`.
- `card_country_proxy`: `card5`.
- `billing_region_proxy`: `addr1`.
- `billing_country_proxy`: `addr2`.
- `email_domain`: `P_emaildomain`.

## 3. OFFLINE RESEARCH FEATURES
- `entity_fraud_rate_30d_delay`: Historical fraud rate strictly gated by a 30-day delay, mimicking chargeback latency.
- `browser_type`: `id_31` (Requires explicit merchant telemetry injection).
- `device_type`: `DeviceType` (Requires explicit merchant telemetry injection).

## 4. DATASET-SPECIFIC FEATURES
- CreditCard2023 PCA components.

## 5. LEAKAGE/POST-EVENT FEATURES
- **V-Series / C-Series**: Highly obfuscated IEEE-CIS feature groups with confirmed post-transaction or full-window counting mechanisms that pose severe data leakage risks in production serving.
- `isFraud`: Excluded from all feature vectors.

## 6. UNKNOWN FEATURES
- **D-Series / M-Series**: Obfuscated timedelta and matching strings in IEEE-CIS.

## 7. REJECTED FEATURES
- Features with extreme missingness, zero variance, or reliance on un-parsable synthetic data.

## Cross-Dataset Conceptual Origin
- **Velocity (24h/7d)**: Concept extracted from banking datasets (BankSim, Fraud Dataset).
- **Missingness indicators**: Concept derived from Fraud Dataset structural analysis where missing biometrics correlate highly with synthetic attacks.
