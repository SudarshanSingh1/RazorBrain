PHASE 21C-A STATUS: PASS WITH PROVENANCE CLARIFICATION

1. Evaluation Status
The pipeline demonstrated valid mathematical evaluation offline, but the documentation and test provenance required correction to properly identify the origin and nature of the test dataset. No model parameters, thresholds, or test data were modified during this audit.

2. Test Dataset Provenance
The original Phase 21A Test dataset is stored on disk (`data/generated/transactions.parquet`), but it represents a structurally flawed data generation algorithm (e.g. 1,000 customers). The dataset evaluated in this phase is a **newly generated 100,000-row dataset** created via `generate_transactions(n=100000, seed=42)`. The Phase 21C evaluation strictly measures the test split of this *new* dataset.

3. Why This Is a New Held-Out Test
Because Phase 21B altered the generator to increase customer pool size and strengthen signal multipliers, the old Phase 21A test data became functionally obsolete. The Phase 21C evaluation measures the model against the chronological Test split (last 15,000 rows) of the newly generated Phase 21B data. This test split was completely held out during Phase 21B; no test labels were ever observed during the model selection, calibration removal, or hyperparameter tuning stages.

4. Test Integrity
Strict test isolation was maintained. The new 100,000-row dataset was split chronologically. The Train and Validation splits were used in Phase 21B. The Test split (rows 85,000 to 100,000) was completely ignored until Phase 21C execution. No test rows were used for tuning generator multipliers. No test labels were used for XGBoost selection. 

5. Dataset Statistics
- Total test rows: 15,000
- Fraud: 2,294
- Legitimate: 12,706
- Fraud prevalence: 15.29%

6. Fraud Prevalence Explanation
Fraud prevalence increased from 7.29% (Phase 21A) to 15.29%. This is physically caused by the Phase 21B modifications to `_compute_fraud_probability` in `data/generator.py`, where the additive risk multipliers for anomaly triggers (e.g., `new_device`, `new_location`, `deviation`) were substantially increased from weak values (0.25) to strong values (2.0 - 3.0) to establish a viable predictive structure.

7. Authoritative Model
- Model Class: XGBClassifier (Native logloss objective)
- Feature Count: 21 (Order identical to Train)
- Preprocessing: StandardScaler + frequency encoding
- Calibration: Not applied (method="none")
- Random Seed: 42

8. Offline/Deployed Consistency
The `model/final_test_evaluation.py` explicitly utilizes the same functions (`fuse_risk_batch`, `make_decision`) and the same XGBoost configurations as the `api/lifespan.py` startup sequence.

9. Final Test Metrics
- ROC-AUC: 0.7274
- PR-AUC: 0.3129
- Precision: 0.4506
- Recall: 0.0497
- F1: 0.0895

10. Confusion Matrix
*(Note: Binary model classification strictly at probability >= 0.40)*
- TP: 114
- TN: 12567
- FP: 139
- FN: 2180

11. ALLOW / REVIEW / BLOCK
*(Note: RazorBrain Operational Decisions including Guardrails)*
Legitimate:
- ALLOW: 6366
- REVIEW: 6339
- BLOCK: 1

Fraud:
- ALLOW: 392
- REVIEW: 1900
- BLOCK: 2

12. Block Guardrail Analysis
253 transactions achieved a raw probability >= 0.40. However, the independent rule guardrails safely rejected 250 of these from being automatically blocked because they lacked deterministic corroborating evidence (such as `risky_merchant_new_customer`). Only 3 transactions satisfied both the ML threshold and the rule guardrails, resulting in 3 actual BLOCK decisions.

13. Business Cost
- Fraud Allowed Cost: $196000
- Fraud Reviewed Cost: $95000
- Legit Reviewed Cost: $316950
- Legit Blocked Cost: $100
- Total Test Business Cost: $608050

14. Probability Distribution
- Min: 0.0530
- Max: 0.6691
- Median: 0.1112
- Count >= 0.10: 8242
- Count >= 0.40: 253

15. Calibration Assessment
- Brier Score: 0.1177
- Log Loss: 0.3842
The uncalibrated XGBoost probabilities achieved a Brier score of 0.1177. This is better than the prevalence-only baseline Brier score of 0.1295 (calculated as p * (1-p) for p=0.1529). Calibration was not fitted during this final evaluation.

16. Rule Evidence
- Total Rule Triggers: 5314
- Triggers by Rule ID: {"missing_critical_context": 743, "repeated_fraud": 4376, "extreme_amount_single_signal": 136, "risky_merchant_new_customer": 37, "deviation_new_location": 21, "velocity_new_device": 1}
- Severity Distribution: {"INFO": 743, "LOW": 136, "MEDIUM": 58, "HIGH": 4377}
- Blocking-eligible rule triggers: 59
*(Note: Rule triggers represent independent firings, not unique suspicious transactions).*

17. SHAP Evidence
The SHAP system successfully natively supports `shap.TreeExplainer(model)`.
- Top Features with highest average negative SHAP contributions (when reducing risk): ['previous_fraud_count', 'amount', 'new_device_flag']
- Top Features with highest average positive SHAP contributions (when elevating risk): ['previous_fraud_count', 'new_device_flag', 'new_location_flag']
*(Note: SHAP values explain model contribution; they are not risk points or percentages).*

18. Model/Rule Conflicts
Transactions where rules triggered blocking-eligible severity but the model returned very low risk (< 0.10): 7.

19. Review Workload
- Total REVIEW rate: 54.93% (8,239 / 15,000)
- Legitimate REVIEW rate: 49.89%
- Fraud REVIEW rate: 82.82%
This exceptionally high operational review workload stems from the highly conservative 0.10 ALLOW threshold.

20. False Positive Analysis
Of the 12,706 legitimate transactions, 6,339 were assigned REVIEW and 1 was BLOCKED. A REVIEW is an operational triage routing, not a hard false-positive classification. The high REVIEW volume is the physical manifestation of the system safely preventing automatic blocks when ML precision is low.

21. False Negative Analysis
Of the 2,294 actual fraud transactions, 392 were incorrectly placed in ALLOW (an actual False Negative operational escape). 1,900 were properly escalated to REVIEW, but lacked independent catastrophic rule evidence required to comfortably cross the hard BLOCK threshold.

22. Risk Segments
The behavioral novelty indicators (`new_device_flag`, `new_location_flag`, `merchant_fraud_rate`) paired with historical fraud counts form the primary discriminating axis for SHAP attribution.

23. Temporal Leakage
Point-in-time correctness across the test set was fully maintained via chronological `.shift(1)` operations during the dataset generation and feature extraction.

24. Data Quality
- No missing targets: True
- Both classes present: True

25. Reconciliation
- Total test rows (15,000) = TP (114) + TN (12,567) + FP (139) + FN (2,180)
- Total test rows (15,000) = Legit (12,706) + Fraud (2,294)
- Legit (12,706) = Allow (6366) + Review (6339) + Block (1)
- Fraud (2,294) = Allow (392) + Review (1900) + Block (2)
All counts reconcile precisely.

26. Reproducibility
- Seed: 42
- Feature Schema: Fixed 21 columns
- Model: XGBClassifier
The full evaluation run can be exactly replicated by executing `model/final_test_evaluation.py`.

27. Tests
The integrity of the ecosystem was verified locally: `pytest -q tests/` resulted in 219 tests passing. 

28. Limitations
While the XGBoost PR-AUC (0.3129) is a significant improvement over the base rate (0.1529), the operational review workload (54.9%) remains unsustainably high for a production workforce. The system relies almost entirely on manual operational triage because the model's confidence rarely aligns with independent deterministic blocking rules.

29. Final Assessment
The Phase 21B XGBoost pipeline demonstrated materially stronger discrimination on the newly generated held-out test set than the Phase 21A Logistic Regression pipeline. However, the test set is a regenerated dataset created after the synthetic-data-generator correction, so it is strictly identified as a new independently held-out evaluation rather than the original Phase 21A test. The system remains extremely conservative at the BLOCK boundary and routes a large fraction of transactions to REVIEW, highlighting an operational limitation that must be addressed in subsequent architectural phases.
