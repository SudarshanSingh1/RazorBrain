# SHAP Evidence Generation

## 1. What SHAP Explains
SHAP (SHapley Additive exPlanations) is used to explain the relative contributions of individual input features to the underlying model's prediction for a specific transaction.

## 2. Explanation Target
SHAP explicitly explains the **raw output of the base XGBoost estimator (Model C)** (the margin). It does **NOT** directly explain the Platt-calibrated risk probability. The calibrated probability relies on the aggregate output of the model to produce an operational threshold, while SHAP explains which features formed that underlying model output.

## 3. Transformed Feature Mapping
The exact frozen model's preprocessing pipeline generates a 438-dimensional feature representation. The SHAP implementation uses `preprocessor.get_feature_names_out()` to deterministically map each column in the 438-dimensional matrix to its correct transformed feature name (e.g., `cat__email_suffix_com` rather than inventing a raw name). The SHAP values map 1:1 with these transformed features.

## 4. Positive and Negative Contributions
- **Positive (`INCREASES_RISK`)**: The feature value pushed the base model's raw output toward a higher fraud likelihood.
- **Negative (`DECREASES_RISK`)**: The feature value pushed the base model's raw output toward a lower fraud likelihood (legitimate).

## 5. Top-K Evidence
To remain compact and interpretable, the API only returns the top K contributors by absolute weight:
- Up to **5 positive** contributors
- Up to **3 negative** contributors
Features with exactly zero contribution (`INFORMATIONAL`) are generally omitted from the top-K list unless no other evidence exists.

## 6. Deterministic Summary
A structured, deterministic text summary is generated (e.g., `"Model evidence: V294 and R_emaildomain contributed most toward higher model risk, while feature X contributed toward lower risk."`). This summary is purely algorithmic and uses the exact SHAP feature names. **No LLM or AI generation is used for this summary.**

## 7. Failure Behavior
If SHAP computation fails, the scoring transaction **does not fail**. The decision is returned based on the valid calibrated risk. The explanation evidence gracefully degrades to a single item with `"code": "MODEL_EXPLANATION"`, `"description": "unavailable"`.

## 8. Performance Considerations
SHAP using `TreeExplainer` on an XGBoost model is highly optimized, but still adds overhead compared to pure inference. It is intended to be executed on an as-needed basis (e.g., for explicitly flagged transactions, manual investigations, or detailed API requests) rather than over the entire dataset uniformly.

## 9. Feature Semantic Limitations
Features originating from IEEE-CIS (such as the `V-series`, `id-series`, and other anonymized variables) are opaque. We **do not invent business interpretations** for these variables. SHAP evidence descriptions refer strictly to the `"transformed feature X"`. 

## 10. Temporal Availability Limitations
SHAP evidence can only explain features that were physically available to the model at scoring time. The `available_at_scoring` flag preserves whether a specific feature was present. We do not claim all IEEE-CIS features are available at real-time Razorpay webhooks; the evidence strictly reflects what the model actually received.

## 11. SHAP Does Not Prove Fraud
**SHAP identifies features that contributed to the model's prediction; it does not establish that the transaction is fraudulent.** It is an explainability tool for the model's logic, not a cryptographic proof of real-world financial fraud.

## 12. SHAP Does Not Modify Decisions
**SHAP generation is strictly read-only.** It cannot mutate `calibrated_risk`, `raw_model_score`, or the ultimate `ALLOW / REVIEW / BLOCK` decision. Model execution, calibration, and decision logic form an immutable path that SHAP evaluates but never alters.
