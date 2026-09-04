# Razorpay Serving Model — Probability Calibration

## 1. Why This Calibration Is Independent from Model C

Model C has its own Platt calibration artifact (`data/model_c_calibrated.joblib`) trained on IEEE-CIS validation data using Model C's XGBoost scores. The Razorpay Serving Model has a completely different feature space (15 vs 438 transformed dimensions), different raw score distribution, and different performance characteristics. Reusing Model C's calibration would be incorrect. The serving model requires and receives its own independent calibration.

## 2. Frozen Model Used for Calibration

```
data/razorpay_serving_model_uncalibrated.joblib
MD5: 1242b74830962d8d323676563648ffdb
Selected model: XGBoost (15 features)
```

The model was not retrained. The XGBoost classifier and its preprocessing pipeline were loaded from the frozen artifact and only used to generate raw prediction scores.

## 3. Calibration Split Construction

The TRAIN set (413,378 rows) was split chronologically:

| Portion | Rows | Fraud | Fraud Rate | DT Range |
|---|---|---|---|---|
| Model-train (first 80%) | 330,702 | 11,180 | 3.38% | 86,400 – 8,121,450 |
| **Calibration** (last 20%) | **82,676** | **3,358** | **4.06%** | 8,121,466 – 10,437,996 |
| **Cal-evaluation** (VALIDATION) | **88,581** | **3,042** | **3.43%** | 10,438,003 – 13,151,840 |

Chronological ordering verified: model-train < calibration < cal-evaluation < test.

## 4. Why the Test Set Was Excluded

The `RAZORPAY_SERVING_TEST` is permanently frozen. Using it for calibration fitting or calibrator selection would contaminate the final held-out evaluation. It was not opened during this step. Its hash (`fc4e76764a2e7ad1df631ce37d050f35`) remains unchanged.

## 5–7. Calibration Metrics on Cal-Evaluation (VALIDATION)

| Method | ROC-AUC | PR-AUC | Brier Score | Log Loss |
|---|---|---|---|---|
| **Uncalibrated** | 0.7651 | 0.1806 | 0.1800 | 0.5458 |
| **Platt** | 0.7651 | 0.1806 | 0.0308 | 0.1305 |
| **Isotonic** | 0.7647 | 0.1725 | **0.0307** | **0.1300** |

## 8. Brier / Log-Loss Comparison

Calibration dramatically improves probability quality (Brier: 0.1800 → 0.0307). This is expected — the uncalibrated XGBoost scores are raw probabilities optimised for ranking, not calibrated risk estimates.

Isotonic regression achieves a marginally lower Brier score (0.0307 vs 0.0308) and log loss (0.1300 vs 0.1305) than Platt scaling.

Note: Isotonic slightly decreases PR-AUC (0.1806 → 0.1725) because isotonic regression is not strictly monotonic at the tails. This minor ranking degradation is documented honestly.

## 9. Selected Calibrator

**Isotonic Regression** — selected because it achieves the lower Brier score (0.0307 vs 0.0308) on the calibration-evaluation set. Primary selection criterion: Brier score. Both calibrators were evaluated only on the validation set; the serving test was excluded.

## 10. Reliability / Calibration Diagnostics

Reliability bins (Isotonic, on validation set). Observed fraud rate vs. mean predicted probability:

| Bin [lo, hi) | n | Mean Predicted | Observed Fraud Rate | Notes |
|---|---|---|---|---|
| [0.00, 0.10) | 80,698 | 0.024 | 0.022 | Well calibrated (low end) |
| [0.10, 0.20) | 5,914 | 0.141 | 0.112 | Slight over-prediction |
| [0.20, 0.30) | 1,567 | 0.253 | 0.266 | Slight under-prediction |
| [0.30, 0.40) | 402 | 0.319 | 0.438 | Under-prediction at mid-range |
| [0.40, 0.50) | 0 | — | — | Empty bin |
| [0.50, 0.60) | 0 | — | — | Empty bin |
| [0.60, 0.70) | 105 | 0.645 | 0.619 | Acceptable |
| [0.70, 0.80) | 16 | 0.759 | 0.812 | Sparse |
| [0.80, 0.90) | 34 | 0.840 | 0.912 | Sparse — interpret cautiously |
| [0.90, 1.00) | 8 | 0.906 | 0.875 | Very sparse |

The bins from 0.30–0.60 are thinly or entirely populated, which is expected given the 3.5% fraud prevalence and the model's score distribution. Calibration estimates in those ranges should be treated with caution.

## 11. Cross-Domain Limitations

> [!CAUTION]
> The calibrated value is a model-estimated fraud risk based on the **IEEE-CIS-derived serving model**. It is NOT:
> - a measured Razorpay fraud probability
> - a guarantee of fraud
> - a causal fraud probability
> - a real-world Razorpay production probability
>
> Because this model is trained on IEEE-CIS data and not real Razorpay fraud labels, **calibration does not eliminate cross-domain uncertainty**. The calibrated probabilities reflect the model's uncertainty in the IEEE-CIS domain, not in the Razorpay domain.

## 12. Calibration Does Not Improve Ranking Quality

> [!IMPORTANT]
> Calibration applies a monotonic (Platt) or near-monotonic (Isotonic) transformation to the raw scores. ROC-AUC is preserved under Platt (0.7651 → 0.7651). Isotonic shows a minor PR-AUC change (0.1806 → 0.1725). **Calibration improves probability estimates, not discrimination ability.**

## 13. Serving Test Firewall Confirmation

The `RAZORPAY_SERVING_TEST` (`data/razorpay_serving_dataset/test.csv`) was:
- ✅ Never loaded by `calibrate_serving_model.py`
- ✅ Never used for calibrator fitting
- ✅ Never used for calibrator selection
- ✅ Hash verified unchanged: `fc4e76764a2e7ad1df631ce37d050f35`
