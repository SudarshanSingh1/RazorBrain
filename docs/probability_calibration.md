# Probability Calibration

## Methodology
- **Base Model:** Frozen Model C (147 features), trained on 413,378 rows.
- **Calibration Split:** Validation set chronologically split into `val_calib` (44,290 rows) and `val_eval` (44,291 rows).
- **Fitting:** Calibrators fit on `val_calib` using raw predictions from frozen Model C.
- **Evaluation:** Evaluated purely on untouched `val_eval`. 
- **Test Set Firewall:** Test set was completely excluded.

## Results on `val_eval`
| Method | Brier Score | Log Loss | ROC-AUC | PR-AUC |
|---|---|---|---|---|
| Raw XGBoost | 0.10466 | 0.35397 | 0.86879 | 0.31 |
| Platt (Logistic) | 0.02678 | 0.10705 | 0.86879 | 0.31 |
| Isotonic | 0.02657 | 0.10919 | 0.86789 | 0.29971 |

## Conclusion
Selected method: **PLATT** (lowest log_loss). 
Saved artifact: `data/model_c_calibrated.joblib`
