# Razorpay Serving Dataset

This document details the construction of the feature-restricted dataset derived from IEEE-CIS for training the Razorpay Serving Model prototype.

## 1. Selected Features
The following 15 features were selected because they have a direct or conceptual analogue in the Razorpay serving environment:
- `amount` (Directly aligned)
- `log_amount` (Directly aligned)
- `hour_of_day` (Directly aligned, derived from `TransactionDT`)
- `day_of_week` (Conceptually aligned, derived from `TransactionDT` as a 7-day cyclical proxy)
- `email_domain` (Directly aligned from `P_emaildomain`)
- `email_domain_missing` (Directly aligned)
- `card_network` (Conceptually aligned from `card4`)
- `card_type` (Conceptually aligned from `card6`)
- `previous_transaction_count` (Conceptually aligned entity history)
- `is_new_customer` (Conceptually aligned)
- `avg_customer_amount` (Conceptually aligned)
- `amount_deviation` (Conceptually aligned)
- `amount_ratio` (Conceptually aligned)
- `txns_last_1h` (Conceptually aligned velocity)
- `txns_last_24h` (Conceptually aligned velocity)

## 2. Rejected Features
- **All V-series (86 features)**: Vesta proprietary internal features, completely unavailable at Razorpay.
- **All id-series (21 features)**: Identity table device fingerprinting, unavailable via Razorpay webhooks.
- **All D-series (3 features)**: Anonymous timedelta proxies, irreproducible.
- **All M-series (2 features)**: Anonymous match flags.
- **`dist1`, `addr1`, `addr2`**: Billing region proxies, no location telemetry in Razorpay webhooks.
- **`R_emaildomain`**: Recipient email is a remittance concept, not standard e-commerce.
- **`card2`, `card3`, `card5`**: Anonymous card proxies.
- **`isFraud`**: Target label, strictly excluded from feature matrix.

## 3. Semantic Alignment
Features are mapped according to the `data/razorpay_serving_feature_contract.json`. 
*   **DIRECTLY_ALIGNED**: Exact semantic match (e.g., `TransactionAmt` to `payment.amount`).
*   **CONCEPTUALLY_ALIGNED**: Analogous concept requiring different representation (e.g., `card1` as entity proxy vs Razorpay `customer_id`).

## 4. Entity Definition
The IEEE-CIS dataset uses `card1` as an anonymized payment card proxy. We use `card1` as the closest behavioral grouping analogue to a Razorpay `customer_id`. While a customer might have multiple cards in reality, `card1` provides the necessary transaction history grouping to compute velocity and average spending behavior, mirroring what RazorBrain does via database queries on `customer_id`.

## 5. Historical Feature Construction
Historical features (`txns_last_1h`, `avg_customer_amount`, etc.) are computed using a strictly causal algorithm:
*   Data is sorted chronologically by `TransactionDT`.
*   Features are grouped by `card1`.
*   Aggregations explicitly shift the window to exclude the current row (e.g., `shift(1)` for cumulative means, and `count() - 1` for rolling windows).
*   No full-dataset `.transform()` functions were used that could leak future information.

## 6. Temporal Split
The data is split strictly chronologically to simulate a real-world deployment:
*   **TRAIN (70%)**: 413,378 rows (3.52% fraud). Period: 86400 - 10437996
*   **VALIDATION (15%)**: 88,581 rows (3.43% fraud). Period: 10438003 - 13151840
*   **RAZORPAY_SERVING_TEST (15%)**: 88,581 rows (3.48% fraud). Period: 13151880 - 15811131

## 7. Class Imbalance
The dataset maintains its natural class imbalance (~3.5% fraud). No synthetic rebalancing (SMOTE) or upsampling was applied to the test set, ensuring an honest evaluation of the serving model.

## 8. Missingness
Missing categorical values (e.g., `card4`, `P_emaildomain`) are explicitly encoded as the string `'MISSING'`. This mimics the expected behavior for non-card Razorpay transactions (e.g., UPI) where card network and type will be absent. The missingness of email is also explicitly captured as a binary indicator `email_domain_missing`.

## 9. Domain Shift Warning
**CRITICAL**: This dataset is derived from IEEE-CIS (US e-commerce) and merely conceptually aligned with Razorpay Test Mode inputs. It does NOT represent real Razorpay fraud patterns. Any model trained on this dataset acts as a cross-domain bootstrap prototype. Performance on the `RAZORPAY_SERVING_TEST` set estimates how a restricted model performs on IEEE-CIS data, not how it will perform on live Razorpay data.

## 10. Test Firewall
The `RAZORPAY_SERVING_TEST` split is permanently isolated. It must not be used for feature selection, model selection, hyperparameter tuning, or calibration. 
**Note**: This is a completely separate test set from Model C's frozen held-out test set. Model C's artifacts remain untouched.

## 11. Serving Feature Contract
The exact feature schema and its Razorpay mapping is defined in:
`data/razorpay_serving_feature_contract.json`

## 12. Limitations
*   **Entity Mismatch**: `card1` is not identical to `email`/`contact`.
*   **No Merchant History**: IEEE-CIS `addr1` is a billing region, not a merchant. We cannot simulate `merchant_fraud_rate` accurately.
*   **Zero Real Labels**: The prototype will be deployed into Razorpay Test Mode where no real fraud occurs, meaning further evaluation requires a real production feedback loop.
