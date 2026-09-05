import os
import json
import joblib
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from sklearn.metrics import roc_auc_score, precision_score, recall_score, f1_score, confusion_matrix, roc_curve, precision_recall_curve
import shap

os.makedirs("outputs", exist_ok=True)
plt.style.use('ggplot')

# 1. Load Model and Data
print("Loading model and validation data...")
artifact = joblib.load("data/razorpay_serving_model_uncalibrated.joblib")
pipeline = artifact["model_artifact"]
metadata = artifact["metadata"]
features = metadata["features"]

val_df = pd.read_csv("data/razorpay_serving_dataset/validation.csv")
X_val = val_df[features]
y_val = val_df["isFraud"].values

# 2. Extract configuration
config = {
    "framework": metadata.get("selected_model", "XGBoost"),
    "num_features": len(features),
    "validation_size": len(val_df),
}
print(config)

# 3. Generate probabilities
print("Generating predictions...")
scores = pipeline.predict_proba(X_val)[:, 1]

# 4. Determine Thresholds
# We need two thresholds: HIGH_PRECISION and BALANCED
# If the repo already has them in a policy, we can load them, but let's calculate them dynamically from validation.
# HIGH_PRECISION: target FPR ~ 0.001
# BALANCED: maximize F1

fpr_arr, tpr_arr, thresh_arr = roc_curve(y_val, scores)
high_prec_idx = np.where(fpr_arr <= 0.0015)[0][-1]
threshold_high_prec = thresh_arr[high_prec_idx]

prec_arr, rec_arr, thresh_pr_arr = precision_recall_curve(y_val, scores)
f1_arr = 2 * (prec_arr * rec_arr) / (prec_arr + rec_arr + 1e-9)
best_f1_idx = np.argmax(f1_arr)
threshold_balanced = thresh_pr_arr[best_f1_idx]

def get_metrics(y_true, scores, threshold):
    preds = (scores >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_true, preds).ravel()
    return {
        "threshold": float(threshold),
        "auc_roc": float(roc_auc_score(y_true, scores)),
        "precision": float(precision_score(y_true, preds, zero_division=0)),
        "recall": float(recall_score(y_true, preds)),
        "fpr": float(fp / (fp + tn)),
        "f1": float(f1_score(y_true, preds)),
        "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)}
    }

metrics = {
    "HIGH_PRECISION": get_metrics(y_val, scores, threshold_high_prec),
    "BALANCED": get_metrics(y_val, scores, threshold_balanced),
    "config": config
}

# 5. Save metrics
with open("outputs/metrics.json", "w") as f:
    json.dump(metrics, f, indent=4)

metrics_df = pd.DataFrame({
    "Mode": ["HIGH_PRECISION", "BALANCED"],
    "Threshold": [threshold_high_prec, threshold_balanced],
    "AUC-ROC": [metrics["HIGH_PRECISION"]["auc_roc"], metrics["BALANCED"]["auc_roc"]],
    "Precision": [metrics["HIGH_PRECISION"]["precision"], metrics["BALANCED"]["precision"]],
    "Recall": [metrics["HIGH_PRECISION"]["recall"], metrics["BALANCED"]["recall"]],
    "FPR": [metrics["HIGH_PRECISION"]["fpr"], metrics["BALANCED"]["fpr"]],
    "F1": [metrics["HIGH_PRECISION"]["f1"], metrics["BALANCED"]["f1"]]
})
metrics_df.to_csv("outputs/metrics.csv", index=False)
print("Metrics saved.")

# 6. Generate Plots
# ROC Curve
plt.figure(figsize=(8, 6))
plt.plot(fpr_arr, tpr_arr, label=f"ROC (AUC = {metrics['HIGH_PRECISION']['auc_roc']:.4f})", color='#1683d8')
plt.plot([0, 1], [0, 1], 'k--')
plt.xlabel('False Positive Rate')
plt.ylabel('True Positive Rate')
plt.title('ROC Curve')
plt.legend()
plt.tight_layout()
plt.savefig("outputs/roc_curve.png", dpi=150)
plt.close()

# PR Curve
plt.figure(figsize=(8, 6))
plt.plot(rec_arr, prec_arr, label=f"PR Curve", color='#27945b')
plt.xlabel('Recall')
plt.ylabel('Precision')
plt.title('Precision-Recall Curve')
plt.legend()
plt.tight_layout()
plt.savefig("outputs/precision_recall_curve.png", dpi=150)
plt.close()

# Score Distribution
plt.figure(figsize=(10, 6))
plt.hist(scores[y_val == 0], bins=50, color='blue', alpha=0.5, label='Legitimate', density=True)
plt.hist(scores[y_val == 1], bins=50, color='red', alpha=0.5, label='Fraud', density=True)
plt.axvline(threshold_high_prec, color='black', linestyle='--', label=f'HIGH_PRECISION ({threshold_high_prec:.3f})')
plt.axvline(threshold_balanced, color='gray', linestyle='--', label=f'BALANCED ({threshold_balanced:.3f})')
plt.xlabel('Predicted Fraud Probability')
plt.ylabel('Density')
plt.title('Score Distribution by Class')
plt.legend()
plt.tight_layout()
plt.savefig("outputs/score_distribution.png", dpi=150)
plt.close()

# Class Balance
plt.figure(figsize=(6, 5))
class_counts = val_df['isFraud'].value_counts()
plt.bar(class_counts.index.astype(str), class_counts.values, color=["#1683d8", "#e63946"])
plt.xticks([0, 1], ['Legitimate (0)', 'Fraud (1)'])
plt.ylabel('Count')
plt.title('Validation Class Balance')
for i, count in enumerate(class_counts.values):
    plt.text(i, count, str(count), ha='center', va='bottom')
plt.tight_layout()
plt.savefig("outputs/class_balance.png", dpi=150)
plt.close()

# Missing values
plt.figure(figsize=(10, 6))
missing = X_val.isnull().sum()
missing = missing[missing > 0].sort_values(ascending=False).head(15)
if len(missing) > 0:
    plt.barh(missing.index, missing.values, color='#27945b')
    plt.xlabel('Missing Count')
    plt.title('Top Missing Features')
    plt.tight_layout()
    plt.savefig("outputs/missing_values.png", dpi=150)
else:
    # create empty
    plt.figure(figsize=(6,2))
    plt.text(0.5, 0.5, "No Missing Values", ha='center', va='center')
    plt.savefig("outputs/missing_values.png", dpi=150)
plt.close()

# Transaction Distribution
if "amount" in val_df.columns:
    plt.figure(figsize=(10, 6))
    plt.hist(np.log1p(val_df["amount"]), bins=50, color='#815ac7')
    plt.xlabel('Log(Amount + 1)')
    plt.title('Transaction Amount Distribution')
    plt.tight_layout()
    plt.savefig("outputs/transaction_distribution.png", dpi=150)
    plt.close()

# EDA Snapshot (Combine some for the README)
fig, axs = plt.subplots(1, 3, figsize=(18, 5))
if "amount" in val_df.columns:
    axs[0].hist(np.log1p(val_df["amount"]), bins=30, color='#815ac7')
    axs[0].set_title('Log Amount')
class_counts = val_df['isFraud'].value_counts()
axs[1].bar(class_counts.index.astype(str), class_counts.values, color=["#1683d8", "#e63946"])
axs[1].set_title('Class Balance')
axs[1].set_xticks([0, 1])
axs[1].set_xticklabels(['Legit', 'Fraud'])
if "hour_of_day" in val_df.columns:
    fraud_by_hour = val_df.groupby("hour_of_day")["isFraud"].mean()
    axs[2].plot(fraud_by_hour.index, fraud_by_hour.values, color="#d97706", marker="o")
    axs[2].set_title('Fraud Rate by Hour')
plt.tight_layout()
plt.savefig("outputs/eda.png", dpi=150)
plt.close()

# SHAP Importance
print("Calculating SHAP...")
try:
    # Use preprocessor from pipeline
    preprocessor = pipeline.named_steps["preprocessor"]
    xgb_model = pipeline.named_steps["classifier"]
    
    # Transform a sample
    sample_size = min(2000, len(X_val))
    X_sample = X_val.sample(sample_size, random_state=42)
    X_trans = preprocessor.transform(X_sample)
    
    # Get feature names after transformation if available, else use raw names
    if hasattr(preprocessor, "get_feature_names_out"):
        trans_features = preprocessor.get_feature_names_out(features)
    else:
        trans_features = features
        
    explainer = shap.TreeExplainer(xgb_model)
    shap_values = explainer.shap_values(X_trans)
    
    plt.figure(figsize=(10, 8))
    shap.summary_plot(shap_values, X_trans, feature_names=trans_features, show=False)
    plt.title("SHAP Feature Importance (Validation Sample)")
    plt.tight_layout()
    plt.savefig("outputs/shap_importance.png", dpi=150)
    plt.close()
    
    # Save SHAP feature importance to CSV
    mean_abs_shap = np.abs(shap_values).mean(axis=0)
    shap_df = pd.DataFrame({"feature": trans_features, "importance": mean_abs_shap})
    shap_df = shap_df.sort_values("importance", ascending=False)
    shap_df.to_csv("outputs/shap_importance.csv", index=False)
    
except Exception as e:
    print(f"SHAP generation failed: {e}")

print("Report generation completed successfully!")
