# Razorpay Serving Model Prototype

This document outlines the training and evaluation of the FIRST Razorpay Serving Model prototype, a lightweight machine learning pipeline designed to eventually score Razorpay Test Mode transactions.

## 1. Why This Model Exists Separately
The original **Model C** is an IEEE-CIS research benchmark that achieves ROC-AUC 0.8663. However, Model C relies heavily on 124 proprietary Vesta features (e.g., V-series, device identity) which are entirely absent from Razorpay webhook payloads. The Razorpay Serving Model Prototype was trained on a strictly feature-restricted subset of IEEE-CIS to establish an honest baseline of what is achievable using *only* the telemetry actually present at Razorpay serving time.

## 2. Feature Contract
The model uses exactly the 15 features defined in `data/razorpay_serving_feature_contract.json`:
- `amount`, `log_amount`, `hour_of_day`, `day_of_week`
- `email_domain`, `email_domain_missing`
- `card_network`, `card_type`
- `previous_transaction_count`, `is_new_customer`, `avg_customer_amount`, `amount_deviation`, `amount_ratio`
- `txns_last_1h`, `txns_last_24h`

## 3. Candidate Models Evaluated
Two models were evaluated on the validation set:
1. **Logistic Regression (Baseline)**: A simple linear model suitable for scaled numerical and one-hot encoded categorical data.
2. **XGBoost Classifier**: A nonlinear tree-based model.

## 4. Preprocessing Methodology
- **Categoricals** (`email_domain`, `card_network`, `card_type`): `OneHotEncoder` with `handle_unknown='ignore'`.
- **Numericals** (amount features, velocity counts, time proxies): `StandardScaler`.
- **Safety**: The preprocessing pipeline (`ColumnTransformer`) was fit strictly on the `TRAIN` set to prevent data leakage.

## 5. Class Imbalance Handling
The natural class imbalance of the dataset (~3.5% fraud) was preserved. No synthetic oversampling (e.g., SMOTE) was applied. Instead, class weights were used. For XGBoost, the `scale_pos_weight` parameter was computed exactly from the `TRAIN` split fraud ratio (ratio of negative to positive samples).

## 6. Training/Validation Split
The chronological split of the feature-restricted dataset was preserved:
- **TRAIN**: 413,378 rows, 14,538 fraud
- **VALIDATION**: 88,581 rows, 3,042 fraud
- **RAZORPAY_SERVING_TEST**: 88,581 rows (Untouched)

## 7. Model-Selection Methodology
Candidate models were evaluated strictly on the `VALIDATION` set. The primary selection metric was **PR-AUC** rather than ROC-AUC, as PR-AUC is more sensitive to false positives in highly imbalanced datasets.

## 8. Validation Metrics

### Logistic Regression
- **ROC-AUC**: 0.7024
- **PR-AUC**: 0.1063
- **Precision**: 0.0703 | **Recall**: 0.6131 | **F1**: 0.1262

### XGBoost
- **ROC-AUC**: 0.7651
- **PR-AUC**: 0.1806
- **Precision**: 0.0859 | **Recall**: 0.6312 | **F1**: 0.1512

## 9. Confusion Matrix (Validation Set)

### Logistic Regression
- **True Negative (TN)**: 60,884
- **False Positive (FP)**: 24,655
- **False Negative (FN)**: 1,177
- **True Positive (TP)**: 1,865

### XGBoost
- **True Negative (TN)**: 65,112
- **False Positive (FP)**: 20,427
- **False Negative (FN)**: 1,122
- **True Positive (TP)**: 1,920

## 10. Precision/Recall Tradeoff
At its default uncalibrated operating point (0.5), the XGBoost model catches 63.1% of fraud but blocks 20,427 legitimate transactions to do so, yielding a precision of ~8.6%. While this translates to a high false-positive cost, the underlying PR-AUC of 0.1806 shows that the model does separate the classes better than Logistic Regression (PR-AUC 0.1063), and better operating thresholds can be chosen during future threshold optimization.

## 11. Selected Model
**XGBoost** was selected because it achieved a significantly higher PR-AUC (0.1806 vs 0.1063) and ROC-AUC (0.7651 vs 0.7024) compared to the baseline Logistic Regression, indicating a superior ability to identify nonlinear fraud patterns within the restricted feature space.

## 12. Known Limitations
1. **Model C Performance Gap**: As expected, removing 124 features significantly degraded performance. Model C achieved an ROC-AUC of 0.87, whereas this restricted model achieved 0.76.
2. **High False Positive Rate**: Without threshold calibration, the model currently flags too many legitimate transactions.

## 13. Test Data Isolation
**CRITICAL**: The `RAZORPAY_SERVING_TEST` dataset (`data/razorpay_serving_dataset/test.csv`) was NEVER used for model selection, hyperparameter tuning, feature selection, or early stopping. It remains a completely untouched holdout.

## 14. Cross-Domain Bootstrap Warning
**CRITICAL**: This is a cross-domain bootstrap model trained on public IEEE-CIS data (US e-commerce), NOT a model trained on real Razorpay fraud labels. 

## 15. Production Performance Warning
**CRITICAL**: The validation results reported here reflect performance on the restricted IEEE-CIS dataset. They do NOT represent true Razorpay production performance. Genuine Razorpay accuracy can only be established through live shadow scoring and actual chargeback labels.
