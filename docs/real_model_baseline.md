# Real Model Baseline (IEEE-CIS)

## 1. Dataset and Contract
- **Dataset Source:** IEEE-CIS (Real-world e-commerce transaction data).
- **Feature Contract:** 13 primary offline features explicitly modeled to mimic production real-time availability in Razorpay, excluding post-transaction/label-dependent leakage and obfuscated telemetry (V-series/C-series).
- **Temporal Strictness:** Guaranteed chronological split. Historical features (e.g., 24h rolling counts) only include strictly prior transactions of the same entity proxy (`card1`).

## 2. Dataset Splitting & Pre-Processing
- **Train rows:** 413,378
- **Validation rows:** 88,581
- **Held-Out Test rows:** 88,581 (STRICTLY UNTOUCHED during this phase)
- **Train Fraud Prevalence:** ~3.52%
- **Validation Fraud Prevalence:** ~3.43%
- **Class Imbalance Handling:** Used `scale_pos_weight = neg_count / pos_count` calculated strictly from the training split.
- **Preprocessing:** Categoricals mapped to strings, missing categorical values imputed with `'UNKNOWN'`, followed by standard One-Hot Encoding (ignoring unseen variables in valid/test). Numerical features mean-imputed with 0.0 (aligns safely with missing entity history counts).

## 3. Model Configuration
- **Algorithm:** XGBoost (XGBClassifier)
- **Hyperparameters:** `n_estimators=100`, `max_depth=6`, `learning_rate=0.1`, `eval_metric='logloss'`
- **Random Seed:** 42

## 4. Evaluation Metrics
| Metric | Train | Validation |
|---|---|---|
| ROC-AUC | 0.8438 | 0.7960 |
| PR-AUC | 0.2584 | 0.2119 |
| Precision | - | 0.1119 |
| Recall | - | 0.6170 |
| F1 Score | - | 0.1894 |
| False Positive Rate (FPR) | - | 0.1742 |
| False Negative Rate (FNR) | - | 0.3830 |

## 5. Feature Importance Observations
The top 10 features driving predictions are overwhelmingly categorical proxies related to the nature of the transaction and the payment method:
1. `product_type_C` (Importance: 0.299)
2. `card_issuer_proxy_185.0` (Importance: 0.094)
3. `card_type_debit` (Importance: 0.058)
4. `card_type_credit` (Importance: 0.029)
5. `product_type_W` (Importance: 0.025)

**Suspicious Feature Audit:** No single feature exhibits >90% leakage-like importance. The top feature (`product_type_C`) claims ~30% importance, which is typical for a strong risk segment (e.g., specific high-risk digital goods).

## 6. Train vs Validation Distribution
Fraud prevalence remains stable between train (3.52%) and validation (3.43%). There is a noticeable drop from train ROC-AUC (0.84) to validation (0.79), indicating some expected concept drift over time (since the validation set is chronologically strictly after the training set).

## 7. Experimental Threshold Observations
Using the default 0.5 threshold (combined with `scale_pos_weight`), the model optimizes heavily for Recall (61.7%) at a major cost to Precision (11.19%). This causes an FPR of 17.4%, which would overwhelm manual review teams in production. Production thresholds will absolutely need to be re-calibrated.

## 8. Artifact and Reproducibility
- **Artifact Location:** `data/offline_model_artifact.joblib`
- **Reproducibility:** A fully deterministic split script without randomization or random-seeds prior to ML fitting.
- **IMPORTANT LIMITATION:** This artifact is for OFFLINE VALIDATION ONLY. It must not be deployed to RazorBrain production startup until evaluated on the untouched held-out test set.
