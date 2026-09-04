# Razorpay Serving Model — Independent Risk Decision Policy

## 1. Purpose of the Policy
The calibrated serving model produces a single probability-like risk estimate (0.0 to 1.0) indicating the likelihood of fraud for a transaction. The Decision Policy converts this continuous risk score into a discrete operational action (`ALLOW`, `REVIEW`, or `BLOCK`) based on business constraints (review team capacity) and assumed operational costs. 

## 2. Calibrated Risk vs. Final Decision
- **Calibrated Risk**: A continuous score representing model uncertainty.
- **Decision**: A discrete action. The model itself does not make the decision; the policy engine applies the `T_review` and `T_block` thresholds deterministically to the risk score.

## 3. Exact Cost Assumptions
The grid search evaluated thousands of threshold combinations against a uniform operational cost function. The base cost model assumes:
- **C_FN** (False Negative / Fraud Allowed): `100` units
- **C_FP_BLOCK** (False Positive / Legit Blocked): `15` units
- **C_FP_REVIEW** (False Positive / Legit Reviewed): `5` units
- **C_REVIEW** (Operational cost to review a transaction): `2` units

## 4. Why these are assumptions, not measured Razorpay costs
We do not have access to real Razorpay operational metrics, dispute rates, chargeback fees, or manual-review labor costs. These units represent a relative cost ratio used strictly to guide threshold selection on the IEEE-CIS derived validation set.

## 5. Policy Search Methodology
- **Optimization Dataset**: The 88,581-row `VALIDATION` set.
- **Constraints**: 1%, 2%, 5%, and 10% review capacity limits.
- **Method**: Grid search over all possible pairs `T_review < T_block`.
- **Target**: Minimize the total transaction cost without exceeding the review capacity limit.

## 6. Review Capacity Analysis & Unconstrained Policy

| Capacity | T_review | T_block | Review Rate | Block Rate | Fraud Caught | Total Cost |
|---|---|---|---|---|---|---|
| Unconstrained | 0.0797 | 0.2322 | 7.83% | 1.83% | 1,249 | 231,276 |
| 10% | 0.0797 | 0.2322 | 7.83% | 1.83% | 1,249 | 231,276 |
| **5% (Selected)** | **0.1213** | **0.2053** | **4.52%** | **2.21%** | **1,116** | **238,543** |
| 2% | 0.1385 | 0.2053 | 1.89% | 2.21% | 836 | 251,612 |
| 1% | 0.1246 | 0.1385 | 0.85% | 4.10% | 947 | 256,142 |

*Note: The unconstrained optimum requires ~7.8% review capacity. As capacity drops, the model is forced to route marginal cases into `ALLOW` (missing fraud) or `BLOCK` (false positives).*

## 12. Sensitivity Analysis (at 5% capacity)

| Cost Scenario | T_review | T_block | Review Rate | Notes |
|---|---|---|---|---|
| BASE | 0.1213 | 0.2053 | 4.52% | Baseline |
| High False-Negative Cost (C_FN=200) | 0.0978 | 0.1863 | 4.96% | Lowers both thresholds to capture more fraud, maxing out review capacity. |
| High False-Positive Block Cost (C_FP_BLOCK=30) | 0.1246 | 0.2322 | 3.97% | Raises T_block significantly to avoid blocking legitimate users. |

## 13. Selected Demo Policy

The **5% Capacity Base Cost** policy is selected as the default operational demo. It balances reasonable operational costs against practical review team limits.

## 14. Exact Thresholds
- **T_review**: `0.1213`
- **T_block**: `0.2053`

*Rule:*
- Risk < 0.1213 ➞ `ALLOW`
- 0.1213 ≤ Risk < 0.2053 ➞ `REVIEW`
- Risk ≥ 0.2053 ➞ `BLOCK`

## 15. Expected Operational Tradeoffs (on VALIDATION set)
- **Review Rate**: 4.52%
- **Block Rate**: 2.21%
- **Fraud Caught by Review**: 524
- **Fraud Caught by Block**: 592
- **Total Fraud Caught**: 1,116 (Recall: 36.6%)
- **Fraud Missed (Allowed)**: 1,926
- **False Blocks (Legit Blocked)**: 1,369
- **False Reviews (Legit Reviewed)**: 3,480

## 16. Cross-Domain Limitations

> [!CAUTION]
> A `BLOCK` decision does **not** mean certain fraud. It means the model-estimated fraud risk is high enough (≥ 20.5%) that the operational cost equation favors immediate blocking over manual review.
>
> Furthermore, because this policy was optimized on IEEE-CIS data, these thresholds are **not validated Razorpay production thresholds**. Real-world Razorpay transaction distributions may vary radically, altering the true review rates and costs.

## 17. Excluded Test Set Confirmation

> [!IMPORTANT]
> This policy was **NOT** optimized on the frozen serving test. The `RAZORPAY_SERVING_TEST` dataset (`data/razorpay_serving_dataset/test.csv`) was never loaded or used to select these thresholds. It remains permanently reserved for final reporting only.
