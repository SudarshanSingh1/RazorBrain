# Razorpay Serving Model — SHAP Explanation Layer

## 1. Why Serving-Model SHAP Is Separate from Model C SHAP

Model C uses 438 transformed features (86 Vesta V-series, 21 identity device features, etc.). The Razorpay Serving Model uses exactly 15 Razorpay-compatible features. They have different preprocessing pipelines, XGBoost weights, SHAP base values, and score distributions. Applying Model C's SHAP explainer to serving model predictions would produce meaningless results. The two explanation layers are fully independent.

## 2. Exact Model Being Explained

```
Artifact: data/razorpay_serving_model_calibrated.joblib
Pipeline step: classifier (XGBClassifier)
SHAP target: frozen XGBoost internal model weights
```

The calibration layer (Isotonic Regression) is **NOT** what SHAP explains. SHAP is applied directly to the frozen XGBoost model embedded inside the pipeline.

## 3. Exact Preprocessing Being Explained

```
Pipeline step: preprocessor (ColumnTransformer)
  - StandardScaler → 12 numerical features
  - OneHotEncoder(handle_unknown='ignore') → 3 categorical features
    (email_domain: 72 OHE columns, card_network: 5, card_type: 5)
```

The preprocessor is used frozen (no refit). SHAP values are computed in the transformed (scaled + OHE) space and then aggregated back to the 15 original source features.

## 4. SHAP Algorithm

**`shap.TreeExplainer`** — the exact SHAP path-dependent algorithm for tree-based models. This guarantees local accuracy (additivity holds) and does not use approximations or surrogate models.

## 5. Raw-Output / Margin Semantics

```
explained_output: "UNCALIBRATED_XGBOOST_MARGIN"
```

TreeExplainer explains the XGBoost raw log-odds margin output. This is **not** the calibrated risk probability. The mapping from this raw margin to a usable probability is performed by the Isotonic calibrator, which is a separate downstream step.

The base value (~0.001) represents the mean model output in the training background distribution. A margin of ~0.98 corresponds to a high model score, but it requires the isotonic calibration step to map to an interpretable risk probability.

## 6. Feature-Name Mapping

The ColumnTransformer produces names like `num__amount`, `cat__email_domain_gmail.com`. These are mapped back:

| Transformed Name | Original Feature |
|---|---|
| `num__amount` | `amount` |
| `num__log_amount` | `log_amount` |
| `cat__email_domain_gmail.com` | `email_domain` |
| `cat__card_network_visa` | `card_network` |
| `cat__card_type_credit` | `card_type` |

No raw OHE column names (`cat__`, `num__` prefixed) appear in the explanation output.

## 7. Categorical Aggregation

For one-hot encoded categorical features, the SHAP contributions of all OHE columns that belong to the same source feature are summed. For a transaction with `card_type = "credit"`, the active OHE column is `cat__card_type_credit`. Its SHAP value and all inactive columns' contributions are aggregated under the single feature name `card_type`.

## 8. Positive/Negative Direction

| SHAP value | Direction | Meaning |
|---|---|---|
| Positive (> 0) | `INCREASES_MODEL_SCORE` | This feature pushed the XGBoost output higher for this transaction |
| Negative (< 0) | `DECREASES_MODEL_SCORE` | This feature pushed the XGBoost output lower for this transaction |

This is strictly a model explanation. It does **not** mean the feature proves fraud or legitimacy.

## 9. Additivity Validation

SHAP TreeExplainer satisfies the additivity property exactly:

```
base_value + Σ(all SHAP values) = XGBoost raw margin output
```

Verified on the deterministic fixture transaction: `delta = 0.0` (tolerance = 1e-3).

## 10. Latency Benchmark

Measured on the deterministic fixture transaction (25 warm-started runs, not test data):

| Metric | Value |
|---|---|
| Median | **1.78ms** |
| p95 | **1.86ms** |

> [!IMPORTANT]
> This latency is measured for the explanation step only on a development machine. It does NOT represent production Razorpay payment handling latency. Because even sub-2ms is non-trivial for a synchronous payment path, **SHAP explanations should be generated asynchronously or on-demand for investigation**, not inserted into the real-time payment decision path.

## 11. Failure Behavior

If SHAP fails for any reason (invalid input, preprocessing error, internal exception), the explainer returns:

```json
{"status": "UNAVAILABLE", "reason": "<machine-readable reason>"}
```

A SHAP failure **NEVER** modifies the calibrated risk or the ALLOW/REVIEW/BLOCK decision. The explanation is a read-only layer.

## 12. Decision/Risk Independence

```
features → XGBoost → SHAP → explanation           (read-only)
features → XGBoost → calibration → policy → decision  (unmodified)
```

These two paths are structurally separate. The `ServingSHAPExplainer` class has no reference to thresholds, policy, or the calibrator.

## 13. Cross-Domain Limitations

> [!CAUTION]
> This model was trained on IEEE-CIS data. SHAP values reflect which features influence the XGBoost model's output **in the IEEE-CIS domain**. The relative importance of features may differ in actual Razorpay production traffic. For example, `card_type` being the top contributor in the fixture does not mean `card_type` is the most important fraud signal in Indian payment networks.

## 14. SHAP Is Explanation, NOT Proof of Fraud

> [!IMPORTANT]
> A high positive SHAP value for a feature means that feature **increased the model score** for this transaction relative to the baseline. It does **NOT** mean:
> - The transaction is fraudulent
> - The feature is a fraudulent indicator in general
> - The feature causes fraud
>
> SHAP is a model explanation tool, not a fraud evidence system.

## 15. SHAP Does Not Change Calibrated Risk or Policy Decision

> [!IMPORTANT]
> The SHAP explanation layer is strictly read-only. Running or not running SHAP on a transaction produces the same calibrated risk and the same ALLOW/REVIEW/BLOCK decision every time.
