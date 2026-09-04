import json
import logging
import joblib
import pandas as pd

from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, average_precision_score, confusion_matrix, precision_score, recall_score, f1_score
from xgboost import XGBClassifier

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

TRAIN_DATA_PATH = "data/razorpay_serving_dataset/train.csv"
VAL_DATA_PATH = "data/razorpay_serving_dataset/validation.csv"
CONTRACT_PATH = "data/razorpay_serving_feature_contract.json"
OUTPUT_MODEL_PATH = "data/razorpay_serving_model_uncalibrated.joblib"

def load_data():
    logger.info("Loading training and validation datasets...")
    train_df = pd.read_csv(TRAIN_DATA_PATH)
    val_df = pd.read_csv(VAL_DATA_PATH)
    
    with open(CONTRACT_PATH, "r") as f:
        contract = json.load(f)
        
    features = [f["name"] for f in contract["features"]]
    
    # Enforce contract
    for f in features:
        if f not in train_df.columns:
            raise ValueError(f"Feature {f} missing from training data")
            
    if "isFraud" in features or "TransactionID" in features:
        raise ValueError("Leakage detected in feature contract")

    categorical_features = [f["name"] for f in contract["features"] if f["type"] == "categorical"]
    numerical_features = [f["name"] for f in contract["features"] if f["type"] == "numeric"]

    return train_df, val_df, features, categorical_features, numerical_features

def evaluate_model(model, name, X_val, y_val):
    preds_proba = model.predict_proba(X_val)[:, 1]
    preds = model.predict(X_val)
    
    roc_auc = roc_auc_score(y_val, preds_proba)
    pr_auc = average_precision_score(y_val, preds_proba)
    precision = precision_score(y_val, preds)
    recall = recall_score(y_val, preds)
    f1 = f1_score(y_val, preds)
    
    tn, fp, fn, tp = confusion_matrix(y_val, preds).ravel()
    fpr = fp / (fp + tn)
    fnr = fn / (fn + tp)
    specificity = tn / (tn + fp)
    
    metrics = {
        "model": name,
        "roc_auc": roc_auc,
        "pr_auc": pr_auc,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "fpr": fpr,
        "fnr": fnr,
        "specificity": specificity,
        "tn": int(tn),
        "fp": int(fp),
        "fn": int(fn),
        "tp": int(tp)
    }
    
    logger.info(f"--- Evaluation for {name} ---")
    logger.info(f"ROC-AUC: {roc_auc:.4f} | PR-AUC: {pr_auc:.4f}")
    logger.info(f"Precision: {precision:.4f} | Recall: {recall:.4f} | F1: {f1:.4f}")
    logger.info(f"Confusion Matrix: TN={tn}, FP={fp}, FN={fn}, TP={tp}")
    return metrics

def train_and_select():
    train_df, val_df, features, cat_feats, num_feats = load_data()
    
    X_train, y_train = train_df[features], train_df['isFraud']
    X_val, y_val = val_df[features], val_df['isFraud']
    
    logger.info(f"TRAIN: {len(X_train)} rows, {y_train.sum()} fraud")
    logger.info(f"VALIDATION: {len(X_val)} rows, {y_val.sum()} fraud")
    
    # Preprocessing
    logger.info("Building preprocessing pipeline...")
    preprocessor = ColumnTransformer(
        transformers=[
            ('num', StandardScaler(), num_feats),
            ('cat', OneHotEncoder(handle_unknown='ignore', sparse_output=False), cat_feats)
        ]
    )
    
    scale_weight = (len(y_train) - y_train.sum()) / y_train.sum()
    
    # Model A: Logistic Regression
    logger.info("Training Model A: Logistic Regression...")
    lr_pipeline = Pipeline([
        ('preprocessor', preprocessor),
        ('classifier', LogisticRegression(max_iter=1000, class_weight='balanced', random_state=42))
    ])
    lr_pipeline.fit(X_train, y_train)
    lr_metrics = evaluate_model(lr_pipeline, "Logistic Regression", X_val, y_val)
    
    # Model B: XGBoost
    logger.info("Training Model B: XGBoost...")
    # We must fit preprocessor to transform validation data for early stopping
    X_train_trans = preprocessor.fit_transform(X_train)
    X_val_trans = preprocessor.transform(X_val)
    
    xgb = XGBClassifier(
        n_estimators=100,
        max_depth=4,
        learning_rate=0.1,
        scale_pos_weight=scale_weight,
        eval_metric='aucpr',
        early_stopping_rounds=10,
        random_state=42
    )
    
    xgb.fit(
        X_train_trans, y_train,
        eval_set=[(X_val_trans, y_val)],
        verbose=False
    )
    
    xgb_pipeline = Pipeline([
        ('preprocessor', preprocessor),
        ('classifier', xgb)
    ])
    
    xgb_metrics = evaluate_model(xgb_pipeline, "XGBoost", X_val, y_val)
    
    # Selection
    metrics_list = [lr_metrics, xgb_metrics]
    best_model_name = "XGBoost" if xgb_metrics["pr_auc"] >= lr_metrics["pr_auc"] else "Logistic Regression"
    best_pipeline = xgb_pipeline if best_model_name == "XGBoost" else lr_pipeline
    best_metrics = xgb_metrics if best_model_name == "XGBoost" else lr_metrics
    
    logger.info(f"*** Selected Model: {best_model_name} (PR-AUC: {best_metrics['pr_auc']:.4f}) ***")
    
    # Save Artifact
    artifact = {
        "model_artifact": best_pipeline,
        "metadata": {
            "version": "1.0",
            "model_track": "RAZORPAY_SERVING_MODEL",
            "selected_model": best_model_name,
            "train_rows": len(X_train),
            "val_rows": len(X_val),
            "features": features,
            "random_seed": 42,
            "validation_metrics": best_metrics
        }
    }
    
    joblib.dump(artifact, OUTPUT_MODEL_PATH)
    logger.info(f"Model artifact saved to {OUTPUT_MODEL_PATH}")
    
    # Save metrics for reporting
    with open("data/razorpay_serving_model_metrics.json", "w") as f:
        json.dump({"candidates": metrics_list, "selected": best_metrics}, f, indent=4)

if __name__ == "__main__":
    train_and_select()
