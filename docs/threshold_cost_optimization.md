# Validation-Based Threshold Optimization

## Methodology
- Evaluated thresholds on `val_eval` using PLATT probabilities.
- Cost grid search ensuring `T_review < T_block`.
- **Test Set Firewall:** Test labels were never used.

## Cost Assumptions
- `C_FN` (Fraud allowed) = 100.0
- `C_FP_BLOCK` (Legit blocked) = 15.0
- `C_FP_REVIEW` (Legit reviewed) = 5.0
- `C_REVIEW` (Manual ops cost) = 2.0

## Optimal Policies by Review Capacity
| Capacity | T_review | T_block | Actual Rev% | Fraud Caught | Cost |
|---|---|---|---|---|---|
| 1% | 0.1793 | 0.2165 | 1.00% | 668 | 101694.0 |
| 2% | 0.1498 | 0.2165 | 2.00% | 729 | 98390.0 |
| 5% | 0.1258 | 0.3125 | 5.00% | 785 | 90283.0 |
| 10% | 0.1086 | 0.4845 | 8.00% | 822 | 85241.0 |
| 100% | 0.1086 | 0.4845 | 8.00% | 822 | 85241.0 |

## Sensitivity Analysis (5% Capacity Target)

| Scenario | C_FN | C_FP_BLOCK | C_FP_REVIEW | C_REVIEW | T_review | T_block | Review % | Fraud Caught | Total Cost |
|---|---|---|---|---|---|---|---|---|---|
| A (Base) | 100.0 | 15.0 | 5.0 | 2.0 | 0.1258 | 0.3125 | 5.00% | 785 | 90283.0 |
| B (High FN Cost) | 200.0 | 15.0 | 5.0 | 2.0 | 0.1086 | 0.2589 | 5.00% | 822 | 154803.0 |
| C (High Block Cost) | 100.0 | 30.0 | 5.0 | 2.0 | 0.1793 | 0.4845 | 5.00% | 668 | 93218.0 |
| D (High Review FP) | 100.0 | 15.0 | 10.0 | 2.0 | 0.1258 | 0.3125 | 5.00% | 785 | 99583.0 |
| E (High Ops Cost) | 100.0 | 15.0 | 5.0 | 5.0 | 0.1258 | 0.3125 | 5.00% | 785 | 96925.0 |


## Validation-Selected Demonstration Policy
Selected the 5% capacity constraint as a realistic operational target.
- **T_review:** 0.1258
- **T_block:** 0.3125
- **Saved to:** `data/validation_selected_policy.json`

*The held-out test set was not used to select this policy.*
