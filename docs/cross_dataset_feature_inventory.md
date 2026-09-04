# Cross-Dataset Feature Inventory and Analysis

## 1. Dataset Inventory
| Dataset | Filename | Row Count | Column Count | Target Column | Target Dist | Provenance | Status |
|---|---|---|---|---|---|---|---|
| IEEE-CIS (Txn) | `train_transaction.csv` | 590,540 | 394 | `isFraud` | 3.5% | Vesta (Real) | ANALYZED (Primary) |
| IEEE-CIS (Id) | `train_identity.csv` | 144,233 | 41 | N/A | N/A | Vesta (Real) | ANALYZED (Primary) |
| BankSim | `bs140513_032310.csv` | 594,643 | 10 | `fraud` | ~1.2% | Synthetic | ANALYZED (Benchmark) |
| BankSim Net | `bsNET140513_032310.csv`| 594,643 | 5 | `fraud` | ~1.2% | Synthetic | ANALYZED (Benchmark) |
| CreditCard2023 | `creditcard_2023.csv` | ~568,630 | 31 | `Class` | ~50% | PCA Synthetic | ANALYZED (Benchmark) |
| Fraud Dataset | `fraud_dataset.csv` | 26,393 | 65 | `is_fraud` | 17.2% | Synthetic / Simulated | ANALYZED (Benchmark) |
| UPI Dataset | N/A | 0 | 0 | N/A | N/A | N/A | ABSENT |

## 2. Feature-Family Inventory
- **Transaction**: Amount, log amount.
- **Time/temporal**: Time of day, day of week, timestamp delta.
- **Velocity**: Rolling count (1h, 24h, 7d).
- **Entity/account**: Card ID, Customer ID, account age.
- **Merchant**: Merchant ID, category, location.
- **Payment instrument**: Card network, card type, issuer bank.
- **Device/Browser**: DeviceType, OS, Browser, Screen metrics.
- **IP/network**: IP address, ASN.
- **Location**: Country, region, zip code.
- **Historical behavior**: Prior averages, deviations from baseline.
- **Frequency/rarity**: Rarity of merchant-customer pairs.
- **Network/Relationship**: Graph degrees (BankSim Net).
- **Behavioral Biometrics**: Keystrokes, OTP timing (Fraud Dataset).

## 3. Cross-Dataset Feature Concept Matrix
| Feature concept | IEEE-CIS | BS | CreditCard | fraud_dataset | RazorBrain (Status) |
|---|---|---|---|---|---|
| Amount anomaly | YES | YES | YES | YES | PRODUCTION_CANDIDATE |
| Entity velocity | YES | YES | UNKNOWN | YES | PRODUCTION_CANDIDATE |
| Device novelty | YES | NO | NO | YES | OFFLINE_RESEARCH |
| Location anomaly | NO | YES | NO | YES | UNAVAILABLE |
| Historical fraud rate | YES | YES | UNKNOWN | YES | OFFLINE_RESEARCH (Delayed) |
| Network relationship | UNKNOWN| YES | NO | UNKNOWN | BENCHMARK_ONLY |
| Behavioral biometrics| NO | NO | NO | YES | UNAVAILABLE |

## 4. IEEE-CIS Expanded Feature Analysis
- **TransactionAmt**: Highly predictive. Expanded to include `log_amount`. (PRODUCTION_CANDIDATE)
- **TransactionDT**: Used to derive `time_of_day_proxy` for cyclical fraud patterns. (PRODUCTION_CANDIDATE)
- **card1 to card6**: Safe categorical proxies for account/issuer. (PRODUCTION_CANDIDATE)
- **P_emaildomain**: Transferable to Razorpay if email is passed. (PRODUCTION_CANDIDATE)
- **V-Series / C-Series**: Anonymized aggregations. Excluded due to severe post-event leakage risk and unclear temporal bounds. (LEAKAGE_RISK)

## 5. BankSim (BS) Feature Analysis
- **zipcodeOri / zipMerchant**: Demonstrates the value of location mismatch. RazorBrain currently lacks location telemetry. (UNAVAILABLE)
- **category**: Transaction product category. Aligns with IEEE-CIS `ProductCD`. (TRANSFERABLE_CONCEPT)

## 6. CreditCard2023 Transferable Concepts
- Provides clear value in identifying amount deviations from baseline, but PCA variables (`V1`-`V28`) cannot be reverse-engineered into generic RazorBrain telemetry. (DATASET_SPECIFIC)

## 7. Fraud Dataset Transferable Concepts
- Features like `pin_entry_speed`, `unusual_location_flag`, `time_between_otp_generation_and_input` represent highly predictive behavioral biometrics. However, these are strictly client-side signals that are entirely UNAVAILABLE to RazorBrain via standard Razorpay webhooks. (UNAVAILABLE / OFFLINE_RESEARCH)

## 8. BankSim Net Transferable Concepts
- Demonstrates graph-based features (e.g., node centrality of merchants). Such graph aggregations require massive precomputation and strict temporal safety, which is currently out of scope for the realtime pipeline but valid for future research. (BENCHMARK_ONLY)

## 9. Production Candidates (New/Expanded)
- `log_amount`
- `card_issuer_proxy`
- `email_domain`
- `time_of_day_proxy`
- `entity_txn_count_1h`
- `entity_txn_count_24h`
- `entity_avg_amount_24h`
- `amount_deviation`

## 10. Transferable Concepts
- `time_of_day_proxy` (Derived from delta timestamp, maps to actual hour in Razorpay)
- `entity_velocity` (Maps to Razorpay customer/card historical lookup)

## 11. Offline-Only Concepts
- `browser_type`, `device_type` (Requires explicit merchant injection into Razorpay Notes).
- `entity_fraud_rate_30d_delay` (Requires complex label-maturity tracking).

## 12. Leakage / Post-Event Concepts
- **V-Series / C-Series**: IEEE-CIS
- **isFraud**: IEEE-CIS
These are strictly REJECTED from the `X` feature matrix.

## 13. Unavailable Concepts
- Behavioral biometrics (keystroke dynamics, OTP timings).
- Geolocation mismatch (unless explicitly integrated).

## 14. Unknown Concepts
- D-Series / M-Series (IEEE-CIS). Placed in REJECTED/UNKNOWN due to obfuscation.

## 15. Generic Feature Engineering Opportunities
We have expanded the pipeline to dynamically compute temporal baselines (e.g., `amount_deviation` = `amount` - `entity_avg_amount_24h`) using strictly prior state, shifting the focus from static features to behavioral anomaly features.

## 16. Dataset Incompatibility Analysis
- **IEEE-CIS** relies on Vesta's proprietary device tracking (`card1`, `id_*`).
- **BankSim** uses simulated strings (`C12345`).
- **CreditCard2023** uses continuous PCA components.
Schemas, label definitions (real chargebacks vs simulated rules), and feature spaces are fundamentally incompatible.

## 17. Why Datasets are NOT Blindly Merged
Merging CreditCard2023 (PCA), BankSim (Simulated), and IEEE-CIS (Real) would create a meaningless, sparse, 500+ column matrix where no single model could learn universal patterns. Worse, synthetic rules would dominate real-world adversarial signals. We analyze them independently to extract concepts, and implement those concepts uniformly on the primary real dataset (IEEE-CIS).

## 18. What Should Be Tested During Model Training Later
- Feature importance of behavioral velocity vs raw amounts.
- Performance impact of missing device/email telemetry in the test split.
- Strict evaluation of ROC-AUC on the strictly chronologically delayed test split.
