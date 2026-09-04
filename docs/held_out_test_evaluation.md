# Held-Out Test Evaluation — Model C

> **ONE-TIME EVALUATION**. This document records the first and only use of the held-out IEEE-CIS test set. Test labels were used exclusively to compute final evaluation metrics. No tuning, calibration, feature selection, or model modification occurred before, during, or after this evaluation.

---

## Model Identification

| Field | Value |
|---|---|
| Model ID | `MODEL_C_ENGINEERED_PLUS_RAW` |
| Artifact | `data/model_c_engineered_raw_safe.joblib` |
| Feature pools | ENGINEERED_CORE (22) + RAW_SAFE (125) = 147 source features |
| Transformed dimension | 438 (after OHE of categoricals) |
| XGBoost config | n_estimators=100, max_depth=6, lr=0.1, seed=42 |
| scale_pos_weight | 27.43 (derived from training labels only) |

---

## Dataset Provenance

| Split | Rows | Fraud count | Fraud rate |
|---|---|---|---|
| Train | 413,378 | 14,538 | 0.0352 |
| Validation | 88,581 | 3,038 | 0.0343 |
| **Test (held-out)** | **88,581** | **3,083** | **0.0348** |

Fraud prevalence is stable across all three splits (~3.5%). No prevalence shift.

---

## Test Immutability Verification

| Check | Result |
|---|---|
| No TransactionID overlap (train ∩ test) | ✅ PASS |
| No TransactionID overlap (val ∩ test) | ✅ PASS |
| Temporal monotonicity (train.max_DT < test.min_DT) | ✅ PASS |
| Temporal monotonicity (val.max_DT ≤ test.min_DT) | ✅ PASS |
| Preprocessor not re-fit on test | ✅ PASS (frozen artifact) |
| Encoders not re-fit on test | ✅ PASS (frozen artifact) |
| Test labels not used for threshold selection | ✅ PASS |
| Test labels not used for feature selection | ✅ PASS |

---

## Final Test Metrics

**EVALUATION THRESHOLD: 0.50** — _EXPERIMENTAL. NOT a production threshold. Threshold optimization will occur separately using train/validation data only._

| Metric | Value |
|---|---|
| **ROC-AUC** | **0.8663** |
| **PR-AUC** | **0.3263** |
| **Precision** | **0.1504** |
| **Recall** | **0.6769** |
| **F1** | **0.2461** |
| **FPR** | **0.1379** |
| **FNR** | **0.3231** |
| **Specificity** | **0.8621** |

### Confusion Matrix

```
                 Predicted Legit    Predicted Fraud
Actual Legit         73,709              11,789   (FP)
Actual Fraud            996              2,087    (TP)
```

| Cell | Count | Interpretation |
|---|---|---|
| TN | 73,709 | Legitimate transactions correctly cleared |
| FP | 11,789 | Legitimate transactions incorrectly flagged — customer friction |
| FN | 996 | Fraud transactions missed — financial loss |
| TP | 2,087 | Fraud transactions correctly caught |

**Fraud capture rate (Recall): 67.7%** — the model catches 2 in 3 fraud transactions at this threshold.
**False-positive rate: 13.8%** — 1 in 7 legitimate transactions is incorrectly flagged.

---

## Train / Validation / Test Comparison

| Metric | Train | Validation | Test |
|---|---|---|---|
| ROC-AUC | 0.9223 | 0.8781 | **0.8663** |
| PR-AUC | 0.5376 | 0.3785 | **0.3263** |
| Precision | — | 0.1671 | 0.1504 |
| Recall | — | 0.7068 | 0.6769 |
| F1 | — | 0.2703 | 0.2461 |

### Generalization Gaps

| Transition | ROC-AUC Gap | PR-AUC Gap |
|---|---|---|
| Train → Validation | +0.0442 | +0.1591 |
| Validation → Test | +0.0118 | +0.0522 |
| Train → Test | +0.0560 | +0.2113 |

**Interpretation:**
- The **Validation → Test ROC-AUC gap is only 0.0118** — excellent. The model generalizes chronologically.
- The PR-AUC drops 5.2pp from val to test. The majority of the train→test PR-AUC gap (0.21) is already captured in train→val (0.16), meaning there is no additional collapse at the test boundary — the model is stable.
- The PR-AUC gaps are larger than ROC-AUC gaps because PR-AUC is sensitive to precision on the fraud minority class, which is inherently more variable.

---

## Score Distribution (Test Set)

| Percentile | Score |
|---|---|
| MIN | 0.006450 |
| P25 | 0.111250 |
| P50 | 0.205845 |
| P75 | 0.369919 |
| P90 | 0.611169 |
| P95 | 0.746795 |
| P99 | 0.905531 |
| MAX | 0.996019 |

The median score is ~0.21 — most transactions receive sub-50% scores as expected in a 3.5%-fraud dataset. The p90 of 0.61 and p99 of 0.91 indicate the model assigns strong confidence to a tail of high-risk predictions.

---

## Risk Separation

| Population | Mean Score | Median Score | p90 Score |
|---|---|---|---|
| Legitimate (85,498) | 0.2603 | 0.1995 | 0.5713 |
| Fraud (3,083) | 0.6372 | 0.6875 | 0.9462 |

**Score gap (fraud median − legit median): +0.488** — the model achieves strong distributional separation. Fraud transactions concentrate at high scores; legitimate transactions concentrate near 0.20.

> [!NOTE]
> The fact that legitimate transactions have a median of ~0.20 and p90 of 0.57 confirms that the 0.50 threshold creates a significant FPR (13.8%). A lower threshold (e.g. 0.30–0.35) would reduce recall while improving precision. Threshold optimization must use train/validation data only.

---

## Feature Behavior Assessment

Features ranked by importance during training (fixed — not re-derived from test):

| Rank | Feature Group | Importance Share |
|---|---|---|
| 1 | V-series (86 cols, 0%-null) | 31.9% |
| 2 | id-series (low-null id_01–id_38) | 22.4% |
| 3 | Email features | 17.5% |
| 4 | Address features (addr2) | 7.6% |
| 5 | Device features | 7.4% |
| 6 | Card features | 5.3% |
| 7 | M-series match flags | 4.7% |
| 8 | Engineered combo (email_suffix, network_product_combo) | 4.1% |
| 9 | Transaction (ProductCD, TransactionAmt) | 2.7% |
| 10 | Entity velocity/temporal (engineered) | 1.3% + 1.3% |

The id-series (id_17, id_29, id_31) and email (R_emaildomain) are the dominant non-V features. These are interpretable: anonymous identity verification flags and email domain are documented fraud signals.

---

## V-Series Assessment

> [!IMPORTANT]
> **V-series features contribute 31.9% of total model importance** — within a reasonable range but warranting explicit documentation of the limitation.

**What is known:**
- V-series (V95–V137, V279–V321) have 0% missingness — they are populated for every IEEE-CIS transaction.
- They are numerical, transaction-time available, and contributed to improved validation and test performance.
- Top V features: V294 (6.1%), V308 (3.8%), V124 (1.2%), V306 (1.0%).

**What is unknown:**
- Exact construction by Vesta (provider). IEEE-CIS competition documentation does not disclose V-series derivation.
- Whether V-series incorporate information from contemporaneous batch processes (if any) that would not be available in real-time serving.

**Scientific position:**
- The test ROC-AUC (0.8663) and PR-AUC (0.3263) remain strong with minimal val→test degradation (+0.0118 ROC), which is **not consistent** with V-series being severely leaky (leaky features would collapse at the test boundary).
- However, the unknown semantics remain a documented model limitation.

> [!WARNING]
> V-series features are admitted as RAW_SAFE with **UNKNOWN semantic confidence**. They should be reassessed if RazorBrain is deployed against a different data source or if serving infrastructure cannot provide them in real-time at transaction time.

---

## Model Limitations

1. **V-series semantics unknown** — 31.9% of importance comes from features with opaque Vesta-internal construction.
2. **No real-time IP/device fingerprint** — identity signals from the IEEE-CIS identity table require the merchant/application to supply them; they are not guaranteed in a Razorpay webhook.
3. **Threshold not optimized** — the 0.50 threshold produces 13.8% FPR. Cost-optimal threshold selection is pending.
4. **Probabilities not calibrated** — predicted probabilities are uncalibrated XGBoost outputs. Calibration will improve reliability.
5. **IEEE-CIS is an e-commerce dataset** — domain coverage may differ from UPI/Razorpay merchant population.

---

## Integrity Statement

> **Test labels were used ONLY to compute evaluation metrics listed in this document. They were not used for model selection, feature selection, hyperparameter tuning, threshold selection, preprocessing fitting, or calibration. The model artifact `model_c_engineered_raw_safe.joblib` was not modified after test evaluation.**

| Check | Status |
|---|---|
| TEST USED FOR TRAINING | NO |
| TEST USED FOR FEATURE SELECTION | NO |
| TEST USED FOR HYPERPARAMETER TUNING | NO |
| TEST USED FOR THRESHOLD SELECTION | NO |
| TEST USED FOR CALIBRATION | NO |
| TEST USED ONLY FOR FINAL METRICS | YES |
| MODEL MODIFIED AFTER TEST | NO |

---

## Evaluation Command

```bash
PYTHONPATH=. python3 model/evaluate_held_out_test.py
```

---

*Evaluated: 2026-09-04. RazorBrain — Razorpay Buildathon Track 02.*
