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
    "amount": {"type": "float", "description": "Transaction amount"},
    "customer_account_age_days": {"type": "int", "description": "Account age at transaction time"},
    
    # Time-aware historical features (superseding the static generator approximations)
    "previous_transaction_count": {"type": "int", "description": "Count of prior transactions for this customer"},
    "previous_fraud_count": {"type": "int", "description": "Count of prior fraudulent transactions for this customer"},
    "avg_customer_amount": {"type": "float", "description": "Average amount of prior transactions for this customer (0 if new)"},
    "amount_deviation": {"type": "float", "description": "Absolute deviation from customer's prior average (0 if new)"},
    "is_new_customer": {"type": "int", "description": "1 if customer has no prior transactions, 0 otherwise"},
    
    "merchant_fraud_rate": {"type": "float", "description": "Rate of fraud in prior transactions for this merchant (0 if new)"},
    "is_new_merchant": {"type": "int", "description": "1 if merchant has no prior transactions, 0 otherwise"},
    
    # Time-aware velocity features
    "txns_last_5min": {"type": "int", "description": "Customer transactions in the 5 minutes preceding this transaction"},
    "txns_last_1h": {"type": "int", "description": "Customer transactions in the 1 hour preceding this transaction"},
    "txns_last_24h": {"type": "int", "description": "Customer transactions in the 24 hours preceding this transaction"},
    
    # Context features
    "new_device_flag": {"type": "int", "description": "1 if the device was drawn from outside the primary pool, 0 otherwise"},
    "new_location_flag": {"type": "int", "description": "1 if the location was drawn from outside the primary pool, 0 otherwise"},
    "ip_is_missing": {"type": "int", "description": "1 if ip_address is null, 0 otherwise"},
    "location_is_missing": {"type": "int", "description": "1 if location is null, 0 otherwise"},
    "location_freq": {"type": "float", "description": "Frequency encoding of location based on historical occurrence (0 if missing)"},
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
    
    # 0. Global Chronological Sort
    out = out.sort_values("timestamp").reset_index(drop=True)
    
    # 1. Customer History Features
    out = out.sort_values(["customer_id", "timestamp"])
    out["previous_transaction_count"] = out.groupby("customer_id").cumcount()
    out["previous_fraud_count"] = (
        out.groupby("customer_id")["is_fraud"]
        .transform(lambda x: x.cumsum().shift(1).fillna(0))
        .astype(int)
    )
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
    
    # 2. Customer Velocity Features
    out = out.set_index("timestamp")
    out["txns_last_5min"] = (out.groupby("customer_id")["transaction_id"].rolling("5min").count().reset_index(level=0, drop=True) - 1).astype(int)
    out["txns_last_1h"] = (out.groupby("customer_id")["transaction_id"].rolling("1h").count().reset_index(level=0, drop=True) - 1).astype(int)
    out["txns_last_24h"] = (out.groupby("customer_id")["transaction_id"].rolling("24h").count().reset_index(level=0, drop=True) - 1).astype(int)
    out = out.reset_index()
    
    # 3. Merchant History Features
    out = out.sort_values(["merchant_id", "timestamp"])
    merchant_txns_before = out.groupby("merchant_id").cumcount()
    merchant_fraud_before = (
        out.groupby("merchant_id")["is_fraud"]
        .transform(lambda x: x.cumsum().shift(1).fillna(0))
    )
    out["is_new_merchant"] = (merchant_txns_before == 0).astype(int)
    out["merchant_fraud_rate"] = np.where(
        merchant_txns_before > 0, 
        merchant_fraud_before / merchant_txns_before, 
        0.0
    )
    
    # 4. Context & Missing Data Indicators (No learned state required)
    out = out.sort_values("timestamp").reset_index(drop=True)
    out["ip_is_missing"] = out["ip_address"].isna().astype(int)
    out["location_is_missing"] = out["location"].isna().astype(int)
    out["new_device_flag"] = out["new_device_flag"].astype(int)
    out["new_location_flag"] = out["new_location_flag"].astype(int)
    
    # Payment Method One-Hot Encoding (Deterministic based on enum)
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
    state: dict[str, Any] = {}
    
    # 1. Location Frequency Encoding
    state["location_freqs"] = out["location"].value_counts(normalize=True).to_dict()
    out["location_freq"] = out["location"].map(state["location_freqs"]).fillna(0.0)
    
    return out, state


def transform_features(df: pd.DataFrame, state: dict[str, Any]) -> pd.DataFrame:
    """
    Transform VALIDATION or TEST splits using exactly the state fitted on TRAIN.
    """
    if state is None:
        raise ValueError("state must be provided to transform_features")
        
    out = df.copy()
    
    # 1. Location Frequency Encoding (using train state)
    out["location_freq"] = out["location"].map(state.get("location_freqs", {})).fillna(0.0)
    
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
