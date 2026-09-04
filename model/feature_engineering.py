"""
Canonical feature engineering pipeline for RazorBrain.

This module provides the strictly time-aware feature transformations
required for model training and inference. It ensures that no future
information or target labels leak into the historical aggregates.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from data.schema import PaymentMethod, Transaction

logger = logging.getLogger(__name__)

# Define the definitive order and metadata for model features.
# This ensures consistency between training and future inference.
FEATURE_METADATA: dict[str, dict[str, str]] = {
    "amount": {"type": "float", "description": "Transaction amount in INR"},
    "customer_account_age_days": {"type": "int", "description": "Days since account creation"},
    "previous_transaction_count": {"type": "int", "description": "Count of prior transactions for this customer"},
    "previous_fraud_count": {"type": "int", "description": "Count of prior fraudulent transactions for this customer where label was available before scoring time"},
    "avg_customer_amount": {"type": "float", "description": "Average amount of prior transactions for this customer (0 if new)"},
    "amount_deviation": {"type": "float", "description": "Absolute deviation from customer's prior average (0 if new)"},
    "amount_ratio": {"type": "float", "description": "Ratio of amount to customer average amount"},
    "is_new_customer": {"type": "int", "description": "1 if customer has no prior transactions, 0 otherwise"},
    "time_since_last_txn": {"type": "float", "description": "Seconds since customer's last transaction (86400 if new)"},
    
    "merchant_fraud_rate": {"type": "float", "description": "Rate of fraud in prior labeled transactions for this merchant (0 if new/no labels)"},
    "previous_merchant_transaction_count": {"type": "int", "description": "Total prior transactions seen at this merchant"},
    "is_new_merchant": {"type": "int", "description": "1 if merchant has no prior transactions, 0 otherwise"},
    
    "customer_merchant_interaction_count": {"type": "int", "description": "Total prior interactions between customer and merchant"},
    
    "txns_last_5min": {"type": "int", "description": "Customer transactions in the 5 minutes preceding this transaction"},
    "txns_last_1h": {"type": "int", "description": "Customer transactions in the 1 hour preceding this transaction"},
    "txns_last_24h": {"type": "int", "description": "Customer transactions in the 24 hours preceding this transaction"},
    
    "hour_of_day": {"type": "int", "description": "Hour of the day from timestamp (0-23)"},
    "day_of_week": {"type": "int", "description": "Day of the week from timestamp (0-6)"},
    
    "ip_is_missing": {"type": "int", "description": "1 if ip_address is null, 0 otherwise"},
}

# Add one-hot encoded payment method features to metadata
for method in PaymentMethod:
    FEATURE_METADATA[f"payment_method_{method.value}"] = {
        "type": "int", 
        "description": f"1 if payment_method is {method.value}, 0 otherwise"
    }



def compute_historical_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute strictly time-aware rolling aggregates on the full dataset.
    This must be run BEFORE chronological splitting so that later partitions
    correctly see their preceding history.
    """
    out = df.copy()
    
    if "is_fraud" not in out.columns:
        out["is_fraud"] = 0
        
    out["timestamp"] = pd.to_datetime(out["timestamp"])
    
    # Label availability column
    if "label_available_at" in out.columns:
        out["label_available_at"] = pd.to_datetime(out["label_available_at"], format='ISO8601')
    else:
        out["label_available_at"] = pd.NaT
        
    # 0. Global Chronological Sort
    out = out.sort_values("timestamp").reset_index(drop=True)
    
    # 1. Customer History Features
    out = out.sort_values(["customer_id", "timestamp"])
    out["previous_transaction_count"] = out.groupby("customer_id").cumcount()
    
    # previous_fraud_count respecting label_available_at
    # We must only count fraud where label_available_at < current transaction timestamp
    # This requires a custom merge_asof or iterative approach.
    
    # Sort for merge_asof
    out = out.sort_values("timestamp")
    
    # Create a frame of just available labels
    fraud_labels = out[out["is_fraud"] == 1][["customer_id", "merchant_id", "label_available_at"]].copy()
    fraud_labels = fraud_labels.dropna(subset=["label_available_at"])
    fraud_labels["fraud_count"] = 1
    
    # We need cumulative fraud per customer available at each timestamp
    fraud_labels = fraud_labels.sort_values(["customer_id", "label_available_at"])
    fraud_labels["cum_fraud"] = fraud_labels.groupby("customer_id")["fraud_count"].cumsum()
    fraud_labels = fraud_labels.rename(columns={"label_available_at": "timestamp"})
    
    if not fraud_labels.empty:
        merged_cust = pd.merge_asof(
            out.sort_values("timestamp"), 
            fraud_labels[["customer_id", "timestamp", "cum_fraud"]].sort_values("timestamp"),
            on="timestamp",
            by="customer_id",
            direction="backward",
            allow_exact_matches=False  # Must be strictly before
        )
        out["previous_fraud_count"] = merged_cust["cum_fraud"].fillna(0).astype(int)
    else:
        out["previous_fraud_count"] = 0
        
    # Resort customer_id
    out = out.sort_values(["customer_id", "timestamp"])
    cum_amount = out.groupby("customer_id")["amount"].transform(lambda x: x.cumsum().shift(1).fillna(0))
    out["is_new_customer"] = (out["previous_transaction_count"] == 0).astype(int)
    out["avg_customer_amount"] = np.where(
        out["previous_transaction_count"] > 0, 
        cum_amount / out["previous_transaction_count"], 
        0.0
    )
    out["amount_deviation"] = np.where(
        out["previous_transaction_count"] > 0, 
        np.abs(out["amount"] - out["avg_customer_amount"]), 
        0.0
    )
    
    out["amount_ratio"] = np.where(
        out["avg_customer_amount"] > 0,
        out["amount"] / out["avg_customer_amount"],
        1.0
    )
    
    # Calculate time since last transaction for the customer
    # out is already sorted by customer_id and timestamp here
    last_txn_time = out.groupby("customer_id")["timestamp"].shift(1)
    out["time_since_last_txn"] = (out["timestamp"] - last_txn_time).dt.total_seconds().fillna(86400.0)
    
    # Temporal features
    out["hour_of_day"] = out["timestamp"].dt.hour
    out["day_of_week"] = out["timestamp"].dt.dayofweek
    
    # 2. Customer Velocity Features
    out = out.set_index("timestamp")
    out["txns_last_5min"] = (out.groupby("customer_id")["transaction_id"].rolling("5min").count().reset_index(level=0, drop=True) - 1).astype(int)
    out["txns_last_1h"] = (out.groupby("customer_id")["transaction_id"].rolling("1h").count().reset_index(level=0, drop=True) - 1).astype(int)
    out["txns_last_24h"] = (out.groupby("customer_id")["transaction_id"].rolling("24h").count().reset_index(level=0, drop=True) - 1).astype(int)
    out = out.reset_index()
    
    # 3. Merchant History Features
    out = out.sort_values(["merchant_id", "timestamp"])
    out["previous_merchant_transaction_count"] = out.groupby("merchant_id").cumcount()
    out["is_new_merchant"] = (out["previous_merchant_transaction_count"] == 0).astype(int)
    
    out = out.sort_values(["customer_id", "merchant_id", "timestamp"])
    out["customer_merchant_interaction_count"] = out.groupby(["customer_id", "merchant_id"]).cumcount()
    
    # merchant_fraud_rate respecting label_available_at
    # Both numerator and denominator must come from labeled rows
    # In training, every row is eventually labeled. But at time T, only rows with
    # transaction_timestamp + label_delay <= T are "labeled"
    
    # Create a frame of all labeled transactions (fraud and legit)
    labeled_txns = out[["merchant_id", "is_fraud", "label_available_at"]].copy()
    labeled_txns = labeled_txns.dropna(subset=["label_available_at"])
    labeled_txns["labeled_count"] = 1
    
    if not labeled_txns.empty:
        labeled_txns = labeled_txns.sort_values(["merchant_id", "label_available_at"])
        labeled_txns["cum_labeled"] = labeled_txns.groupby("merchant_id")["labeled_count"].cumsum()
        labeled_txns["cum_fraud"] = labeled_txns.groupby("merchant_id")["is_fraud"].cumsum()
        labeled_txns = labeled_txns.rename(columns={"label_available_at": "timestamp"})
        
        merged_merch = pd.merge_asof(
            out.sort_values("timestamp"), 
            labeled_txns[["merchant_id", "timestamp", "cum_labeled", "cum_fraud"]].sort_values("timestamp"),
            on="timestamp",
            by="merchant_id",
            direction="backward",
            allow_exact_matches=False
        )
        
        cum_labeled = merged_merch["cum_labeled"].fillna(0)
        cum_fraud = merged_merch["cum_fraud"].fillna(0)
        out["merchant_fraud_rate"] = np.where(
            cum_labeled > 0, 
            cum_fraud / cum_labeled, 
            0.0
        )
    else:
        out["merchant_fraud_rate"] = 0.0
        
    # 4. Context & Missing Data Indicators
    out = out.sort_values("timestamp").reset_index(drop=True)
    
    if "ip_address" not in out.columns:
        out["ip_address"] = pd.NA
        
    out["ip_is_missing"] = out["ip_address"].isna().astype(int)
    
    # Payment Method One-Hot Encoding
    for method in PaymentMethod:
        col_name = f"payment_method_{method.value}"
        out[col_name] = (out["payment_method"] == method.value).astype(int)
        
    return out

def fit_transform_features(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    """
    Fit learned preprocessing (like category frequencies and scalers) on the 
    TRAINING split, and transform it.
    """
    out = df.copy()
    
    # In live API inference, the target 'is_fraud' is not present. 
    if "is_fraud" not in out.columns:
        out["is_fraud"] = 0
        
    out["timestamp"] = pd.to_datetime(out["timestamp"])
    state: dict[str, Any] = {}
    
    # (No learned state required for the current 17-feature contract)
    
    return out, state

def transform_features(df: pd.DataFrame, state: dict[str, Any]) -> pd.DataFrame:
    """
    Transform VALIDATION or TEST splits using exactly the state fitted on TRAIN.
    """
    if state is None:
        raise ValueError("state must be provided to transform_features")
        
    out = df.copy()
    
    # (No learned state required for the current 17-feature contract)
    
    return out

def get_feature_matrix(df: pd.DataFrame) -> pd.DataFrame:
    """
    Extract the strict numerical feature matrix (X) for model input.
    
    Drops identifiers, timestamps, string columns, and the target.
    Retains only columns defined in FEATURE_METADATA in exactly that order.
    """
    feature_cols = list(FEATURE_METADATA.keys())
    
    # Verify all expected columns are present
    missing = [c for c in feature_cols if c not in df.columns]
    if missing:
        raise ValueError(f"DataFrame is missing required engineered features: {missing}")
        
    # Verify the target is excluded from the returned matrix
    if "is_fraud" in feature_cols:
        raise ValueError("CRITICAL LEAKAGE: 'is_fraud' found in FEATURE_METADATA")
        
    return df[feature_cols].copy()


def get_target(df: pd.DataFrame) -> pd.Series:
    """
    Extract the target vector (y) for model evaluation/training.
    """
    return df[Transaction.target_column()].copy()
