# RazorBrain Real Dataset Contract & Discovery

## 1. Dataset Inventory
- `data/RAW/train_transaction.csv`: 590,540 rows, 394 columns.
- `data/RAW/train_identity.csv`: 144,233 rows, 41 columns.
- `data/RAW/creditcard_2023.csv`: ~310MB.
- `data/RAW/bs140513_032310.csv` / `bsNET140513_032310.csv`: BankSim synthetic datasets.
- `data/RAW/fraud_dataset.csv`: 26,393 rows, 64 columns.

## 2. Dataset Provenance
- **IEEE-CIS (train_transaction/identity)**: Real-world e-commerce transaction data provided by Vesta Corporation.
- **CreditCard2023 / BankSim**: Widely known as highly simulated or PCA-transformed datasets.
- **fraud_dataset.csv**: Contains highly granular behavioral telemetry (e.g., `pin_entry_speed`, `upi_handle_age`). Given the unrealistic visibility an acquirer would have into such client-side metrics and its small size (26k), it is likely a highly-simulated benchmark dataset.

## 3. IEEE-CIS Structure
- **Join Key**: `TransactionID`.
- **Identity Overlap**: 144,233 transactions (~24%) have associated identity/device information. 
- **Target**: `isFraud` (Overall fraud rate ~3.5%).
- **Cardinality**: `TransactionID` is unique per row.

## 4. UPI Availability
- **UPI DATASET**: NOT FOUND LOCALLY as a standalone, dedicated, real-world UPI dataset. 
- The `fraud_dataset.csv` benchmark file contains UPI-specific columns (e.g. `upi_handle_age`, `handle_similarity_score`), but it is not a primary training dataset.

## 5. Feature Semantics
| Feature | Meaning | Dataset source | Observed before transaction? | Entity level | Razorpay equivalent | Transferability | Decision |
|---|---|---|---|---|---|---|---|
| `TransactionAmt` | Transaction Amount | IEEE-CIS | Yes | Transaction | `amount` | DIRECT | KEEP |
| `TransactionDT` | Time delta | IEEE-CIS | Yes | Transaction | `created_at` | DIRECT | KEEP |
| `card1`-`card6` | Payment card attributes | IEEE-CIS | Yes | Payment Method | Masked Card/Method | PROXY | KEEP |
| `id_30`/`id_31` | OS/Browser | IEEE-CIS | Yes | Device | `notes.device_id` | PROXY | REQUIRES TELEMETRY |

## 6. Leakage Findings
- **Target (`isFraud`)**: Derived post-transaction (e.g., chargeback). **SAFE** for training labels, **REJECT** for features.
- **V-Series (Vesta engineered)**: Black-box features. High risk of temporal leakage (post-transaction aggregations). **SUSPICIOUS**. Must be excluded or thoroughly audited before inclusion.

## 7. Temporal Findings
- `TransactionDT` is a sequential time delta in seconds. It provides strong chronological ordering, allowing for a strictly ordered temporal train/validation split, which is critical for realistic fraud evaluation.

## 8. Entity Findings
- `card1` (BIN/Account proxy) can serve as an entity key for historical aggregation (e.g., velocity, average amount).
- Identity fields have high missingness (~76% absent) but can differentiate devices when present.

## 9. Razorpay Observability Mapping
| Razorpay Concept | Current RazorBrain source | Actually provided? | Trusted at scoring time? | IEEE-CIS candidate source | Status |
|---|---|---|---|---|---|
| Amount/Currency | `amount`, `currency` | Yes | Yes | `TransactionAmt` | KEEP |
| Timestamp | `created_at` | Yes | Yes | `TransactionDT` | KEEP |
| Customer ID | `notes.customer_id` | Yes (if injected) | Yes | `card1` / `addr1` | PROXY |
| IP / Device | `notes.ip_address` | Yes (if injected) | Yes | `id_31` | PROXY |
| Location | N/A | UNAVAILABLE | N/A | N/A | UNAVAILABLE |

## 10. Current 17-feature Audit
Many of the 17 features (e.g., `avg_customer_amount`, `previous_transaction_count`) require a stable `customer_id`. Since IEEE-CIS does not provide a direct explicit user ID, we will use `card1` or a composite card hash as a proxy for the customer entity to calculate these historical aggregates safely.

## 11. Label Availability Findings
- **Training**: Real labels (chargebacks) arrive days/weeks after the transaction.
- **Mismatch**: The historical synthetic generator assumed labels were known immediately for `previous_fraud_count`. For real data, `label_available_at` MUST be enforced to simulate maturity delays (e.g., +30 days) to prevent massive leakage in aggregate historical features.

## 12. Cross-Dataset Compatibility
- **PRIMARY TRAINING**: IEEE-CIS (`train_transaction` + `train_identity`).
- **BENCHMARK ONLY**: `fraud_dataset.csv`.
- **REJECTED (Not Primary)**: CreditCard2023, BankSim (due to simulated nature and lack of meaningful categorical features aligned with our pipeline).

## 13. 1M+ Strategy
Do NOT duplicate rows or merge incompatible datasets (like BankSim + IEEE) to artificially hit 1,000,000 rows. The 590,540 high-quality, real-world rows from IEEE-CIS are far superior for learning actual adversarial patterns than a larger, corrupted dataset.

## 14. Proposed Real-Data Architecture
An `IEEEDataAdapter` has been introduced. It safely loads, validates, and left-joins the IEEE-CIS data without performing any model training. It serves as the foundation for the offline training pipeline.

## 15. Open Questions
- What is the exact delay we should simulate for `label_available_at` to accurately reflect chargeback maturity?
- Should V-series features be entirely dropped to guarantee zero leakage?

## 16. Recommended Next Task
Build the offline feature engineering pipeline (using the adapter) with strict temporal splitting and `label_available_at` simulation.

---

DATASET STATUS

IEEE-CIS:
PRIMARY (590k transactions, 144k identities)

UPI:
NOT FOUND LOCALLY

fraud_dataset.csv:
BENCHMARK ONLY (Contains UPI telemetry but likely simulated)

CreditCard2023:
REJECTED (Simulated/PCA)

BankSim:
REJECTED (Simulated)

REAL TRAINING PERFORMED:
NO

MODEL ARTIFACT CREATED:
NO

SYNTHETIC DATA USED FOR TRAINING:
NO

PRODUCTION STARTUP TRAINING:
NO

CURRENT 17-FEATURE CONTRACT:
REQUIRES REDESIGN TO USE ENTITY PROXIES

IEEE-CIS ADAPTER:
IMPLEMENTED

RAZORPAY OBSERVABILITY:
AUDITED

CRITICAL FINDINGS:
1 (V-series features present high leakage risk; immediate label availability assumption in previous engine must be fixed)

HIGH FINDINGS:
2 (Razorpay does not natively provide device/IP without server injection; Location telemetry is completely unavailable)

NEXT ACTION:
Implement offline feature engineering with strict temporal splitting
