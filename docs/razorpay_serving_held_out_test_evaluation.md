# Razorpay Serving Model — Held-Out Test Evaluation

## Status

This is the **first and final** evaluation on the permanently frozen `RAZORPAY_SERVING_TEST` dataset. The test set was created chronologically after all training and validation data. It was never loaded, queried, or inspected during any prior step of the project.

**After this evaluation the test labels are permanently frozen and must not be used for:**
feature selection, model selection, preprocessing, calibration, threshold optimization, hyperparameter tuning, or policy optimization.

---

## Isolation Guarantee

| What was the test set used for? | Answer |
|---|---|
| Feature selection | NO |
| Model selection | NO |
| Preprocessing fitting | NO |
| Early stopping | NO |
| Calibration | NO |
| Threshold optimization | NO |
| Gap analysis (this document only) | YES — read-only, no decisions made |

---

## Dataset Statistics

| Split | Rows | Fraud | Legitimate | Fraud Prevalence |
|---|---|---|---|---|
| TRAIN | 413,378 | 14,538 | 398,840 | 3.52% |
| VALIDATION | 88,581 | 3,042 | 85,539 | 3.43% |
| **RAZORPAY_SERVING_TEST** | **88,581** | **3,083** | **85,498** | **3.48%** |

Fraud prevalence is stable across splits, consistent with a clean chronological split from the same source dataset. **This does not rule out feature distribution shift** — IEEE-CIS transaction patterns may differ over time in ways not captured by the label rate alone.

Temporal order verified programmatically:
- `TRAIN.max(TransactionDT)` < `VAL.min(TransactionDT)` ✓
- `VAL.max(TransactionDT)` < `TEST.min(TransactionDT)` ✓

---

## Test Metrics (threshold = 0.50, uncalibrated)

| Metric | Value |
|---|---|
| **ROC-AUC** | **0.7627** |
| **PR-AUC** | **0.1452** |
| Precision | 0.0851 |
| Recall | 0.6364 |
| F1 | 0.1501 |
| Specificity | 0.7531 |
| False-Positive Rate | 0.2469 |
| False-Negative Rate | 0.3636 |

### Confusion Matrix

| | Predicted Legitimate | Predicted Fraud |
|---|---|---|
| **Actual Legitimate** | TN = 64,392 | FP = 21,106 |
| **Actual Fraud** | FN = 1,121 | TP = 1,962 |

---

## Score Distribution

### All Transactions

| Percentile | Score |
|---|---|
| min | 0.0378 |
| p25 | 0.2729 |
| p50 | 0.3576 |
| p75 | 0.5077 |
| p90 | 0.6524 |
| p95 | 0.7291 |
| p99 | 0.8687 |
| max | 0.9370 |

### By Class

| Class | Mean | Median | p90 |
|---|---|---|---|
| Fraud | 0.5808 | 0.5947 | 0.8523 |
| Legitimate | 0.3935 | 0.3528 | 0.6372 |

The fraud and legitimate score distributions show meaningful separation but substantial overlap. This is expected at this stage — calibration and threshold optimization will address the operating point.

---

## Train / Validation / Test Comparison

| Split | ROC-AUC | PR-AUC |
|---|---|---|
| TRAIN | 0.7880 | 0.1709 |
| VALIDATION | 0.7651 | 0.1806 |
| **TEST** | **0.7627** | **0.1452** |

### Gap Analysis

| Gap | ROC-AUC | PR-AUC |
|---|---|---|
| Validation → Test | −0.0024 | −0.0354 |
| Train → Test | −0.0253 | −0.0257 |

**ROC-AUC generalises cleanly**: the validation→test gap of −0.0024 is negligible, indicating the model has not overfit to the validation set.

**PR-AUC shows a more meaningful drop** (−0.0354 validation→test). PR-AUC is sensitive to the precise score distribution at high-risk operating points. This is a realistic finding at this stage: the model's ranking of true positives becomes slightly less precise on unseen chronologically later data.

---

## Artifact Integrity (at evaluation time)

| Artifact | MD5 |
|---|---|
| `razorpay_serving_model_uncalibrated.joblib` | `1242b74830962d8d323676563648ffdb` |
| `razorpay_serving_dataset/test.csv` | `fc4e76764a2e7ad1df631ce37d050f35` |
| `model_c_calibrated.joblib` | `17eaa5aad2a2672f497221362ee4cefd` |
| `model_c_engineered_raw_safe.joblib` | `7de3be91a463ce8d9c74193869212aea` |
| `validation_selected_policy.json` | `a6f2994d904e4dab0bb8ceca52924106` |

All hashes verified against pre-evaluation baselines — zero modification detected.

---

## Cross-Domain Warning

> [!CAUTION]
> This model is a **cross-domain bootstrap prototype** trained on public IEEE-CIS data (primarily US e-commerce transactions from 2017–2019). It was evaluated on a held-out chronological partition of the same dataset. **These metrics are NOT Razorpay production fraud detection metrics.**

> [!CAUTION]
> Razorpay Test Mode does not generate real fraud events. There is no real fraud ground truth available from Razorpay Test Mode for model evaluation. The evaluation reported here is based exclusively on IEEE-CIS labels.

---

## Comparison with Model C (Descriptive Only)

Model C was trained on 147 IEEE-CIS features (438 transformed dimensions), including 86 Vesta proprietary V-series and 21 identity device features. Its frozen held-out test results are:

| Metric | Model C (147 features) | Serving Model Prototype (15 features) |
|---|---|---|
| ROC-AUC | 0.8663 | 0.7627 |
| PR-AUC | 0.3263 | 0.1452 |

The −0.10 ROC-AUC and −0.18 PR-AUC gaps represent the **cost of Razorpay compatibility** — the deliberate removal of 132 features that are unavailable at Razorpay serving time. These results are consistent with the pre-training expectation from the feasibility audit.

Neither model was modified during this comparison.

---

## Scientific Concerns

1. **PR-AUC generalisation gap**: The −0.035 drop from validation to test in PR-AUC warrants monitoring post-calibration. It may reflect temporal distribution shift in the feature-restricted space.
2. **High FPR at 0.50 threshold**: At the uncalibrated default threshold, the model flags 21,106 legitimate transactions as fraud (FPR 24.7%). This is expected pre-calibration and pre–threshold optimisation — the operating point has not yet been chosen.
3. **Score distribution overlap**: The fraud median (0.595) is only moderately separated from the legitimate median (0.353). Calibration and threshold tuning will be necessary to achieve a practically useful operating point.
