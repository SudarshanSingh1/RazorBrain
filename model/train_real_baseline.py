import logging
import joblib
from datetime import datetime

import pandas as pd

# These imports will fail if not installed, we'll handle them.
try:
    from sklearn.compose import ColumnTransformer
    from sklearn.preprocessing import StandardScaler, OneHotEncoder
    from sklearn.pipeline import Pipeline
    from sklearn.impute import SimpleImputer
    from sklearn.metrics import roc_auc_score, average_precision_score, precision_score, recall_score, f1_score, confusion_matrix
    from xgboost import XGBClassifier
except ImportError as e:
    print(f"IMPORT ERROR: {e}")
    # We will raise later if we can't bypass sandbox to install

from model.real_feature_pipeline import RealFeaturePipeline
from model.real_feature_contract import PRIMARY_REAL_FEATURE_SET, REJECTED_FEATURES

logger = logging.getLogger(__name__)

def train_and_evaluate():
    logger.info("Initializing RealFeaturePipeline...")
    pipeline = RealFeaturePipeline()
    
    logger.info("Loading and joining IEEE-CIS dataset...")
    df = pipeline.load_and_join()
    
    logger.info(f"Raw dataset rows: {len(df)}")
    
    logger.info("Building real features...")
    df_features = pipeline.build_real_features(df)
    
    logger.info("Validating feature contract...")
    is_valid = pipeline.validate_feature_contract(df_features)
    if not is_valid:
        raise ValueError("Feature contract validation failed. Aborting training.")
        
    logger.info("Chronologically splitting dataset...")
    train, val, test = pipeline.split_temporally(df_features, train_frac=0.7, val_frac=0.15)
    
    logger.info(f"Train rows: {len(train)}, Val rows: {len(val)}, Test rows: {len(test)}")
    
    target_col = "isFraud"
    
    # 1. Check feature contract
    feature_names = list(PRIMARY_REAL_FEATURE_SET.keys())
    logger.info(f"Primary Features ({len(feature_names)}): {feature_names}")
    
    if target_col in feature_names:
        raise ValueError("Target column is explicitly in primary features!")
        
    for rf in REJECTED_FEATURES:
        if rf in feature_names:
            raise ValueError(f"Rejected feature {rf} found in primary features!")
            
    # Verify chronological split boundaries
    assert train["TransactionDT"].max() <= val["TransactionDT"].min()
    assert val["TransactionDT"].max() <= test["TransactionDT"].min()
    
    # Prepare X and y
    X_train = train[feature_names].copy()
    y_train = train[target_col].copy()
    
    X_val = val[feature_names].copy()
    y_val = val[target_col].copy()
    
    X_test = test[feature_names].copy()
    
    categorical_cols = ["product_type", "card_network", "card_type", "card_issuer_proxy", "card_country_proxy", "billing_region_proxy", "billing_country_proxy", "email_domain", "email_suffix", "network_product_combo"]
    categorical_cols = [c for c in categorical_cols if c in X_train.columns]
    
    for c in categorical_cols:
        X_train[c] = X_train[c].astype(str).replace("nan", "UNKNOWN")
        X_val[c] = X_val[c].astype(str).replace("nan", "UNKNOWN")
        X_test[c] = X_test[c].astype(str).replace("nan", "UNKNOWN")

    
    logger.info(f"Train fraud prevalence: {y_train.mean():.4f}")
    logger.info(f"Val fraud prevalence: {y_val.mean():.4f}")
    
    # Identify categorical and numeric columns
    numeric_cols = [c for c in feature_names if c not in categorical_cols]
    
    logger.info("Building preprocessing pipeline...")
    # Strict missing value and encoding strategy
    # Categoricals: Impute missing with 'UNKNOWN', then OneHotEncode
    cat_transformer = Pipeline(steps=[
        ('imputer', SimpleImputer(strategy='constant', fill_value='UNKNOWN')),
        ('encoder', OneHotEncoder(handle_unknown='ignore', sparse_output=False))
    ])
    
    # Numerics: Impute missing with 0 (since many are counts/amounts where missing ~ 0)
    num_transformer = Pipeline(steps=[
        ('imputer', SimpleImputer(strategy='constant', fill_value=0.0)),
        ('scaler', StandardScaler())
    ])
    
    preprocessor = ColumnTransformer(
        transformers=[
            ('num', num_transformer, numeric_cols),
            ('cat', cat_transformer, categorical_cols)
        ])
    
    # Calculate scale_pos_weight from TRAIN only
    pos_count = y_train.sum()
    neg_count = len(y_train) - pos_count
    scale_pos_weight = neg_count / pos_count if pos_count > 0 else 1.0
    
    logger.info("Initializing XGBoost classifier...")
    # XGBoost Baseline
    model = XGBClassifier(
        n_estimators=100,
        max_depth=6,
        learning_rate=0.1,
        scale_pos_weight=scale_pos_weight,
        random_state=42,
        eval_metric='logloss',
        n_jobs=-1
    )
    
    pipeline_xgb = Pipeline(steps=[('preprocessor', preprocessor),
                                   ('classifier', model)])
    
    logger.info("Fitting model on training data...")
    pipeline_xgb.fit(X_train, y_train)
    
    logger.info("Evaluating model...")
    y_train_prob = pipeline_xgb.predict_proba(X_train)[:, 1]
    
    # Evaluate on Validation
    y_val_pred = pipeline_xgb.predict(X_val)
    y_val_prob = pipeline_xgb.predict_proba(X_val)[:, 1]
    
    train_roc = roc_auc_score(y_train, y_train_prob)
    train_pr = average_precision_score(y_train, y_train_prob)
    val_roc = roc_auc_score(y_val, y_val_prob)
    val_pr = average_precision_score(y_val, y_val_prob)
    
    val_precision = precision_score(y_val, y_val_pred)
    val_recall = recall_score(y_val, y_val_pred)
    val_f1 = f1_score(y_val, y_val_pred)
    
    cm = confusion_matrix(y_val, y_val_pred)
    tn, fp, fn, tp = cm.ravel()
    val_fpr = fp / (fp + tn)
    val_fnr = fn / (fn + tp)
    
    # Feature Importance
    logger.info("Extracting feature importance...")
    xgb_model = pipeline_xgb.named_steps['classifier']
    feature_importances = xgb_model.feature_importances_
    # We need the transformed feature names
    cat_encoder = pipeline_xgb.named_steps['preprocessor'].named_transformers_['cat'].named_steps['encoder']
    cat_feature_names = cat_encoder.get_feature_names_out(categorical_cols)
    all_feature_names = numeric_cols + list(cat_feature_names)
    
    importance_df = pd.DataFrame({
        'Feature': all_feature_names,
        'Importance': feature_importances
    }).sort_values(by='Importance', ascending=False)
    
    print("\nTop 10 Feature Importances:")
    print(importance_df.head(10))
    
    # Create Offline Artifact
    artifact = {
        "model_artifact": {"model": pipeline_xgb},
        "feature_contract": PRIMARY_REAL_FEATURE_SET,
        "feature_order": feature_names,
        "training_dataset": "IEEE-CIS",
        "training_rows": len(train),
        "validation_rows": len(val),
        "test_rows": len(test),
        "train_roc_auc": train_roc,
        "train_pr_auc": train_pr,
        "val_roc_auc": val_roc,
        "val_pr_auc": val_pr,
        "val_precision": val_precision,
        "val_recall": val_recall,
        "val_f1": val_f1,
        "val_fpr": val_fpr,
        "val_fnr": val_fnr,
        "confusion_matrix": cm.tolist(),
        "creation_timestamp": datetime.now().isoformat(),
        "model_version": "0.1.0-baseline"
    }
    
    artifact_path = "data/offline_model_artifact.joblib"
    joblib.dump(artifact, artifact_path)
    logger.info(f"Model artifact saved to {artifact_path}")
    
    print(f"\nTRAIN ROC-AUC: {train_roc:.4f}")
    print(f"TRAIN PR-AUC: {train_pr:.4f}")
    print(f"VALIDATION ROC-AUC: {val_roc:.4f}")
    print(f"VALIDATION PR-AUC: {val_pr:.4f}")
    
    print(f"VALIDATION PRECISION: {val_precision:.4f}")
    print(f"VALIDATION RECALL: {val_recall:.4f}")
    print(f"VALIDATION F1: {val_f1:.4f}")
    print(f"VALIDATION FALSE POSITIVE RATE: {val_fpr:.4f}")
    print(f"VALIDATION FALSE NEGATIVE RATE: {val_fnr:.4f}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    train_and_evaluate()
