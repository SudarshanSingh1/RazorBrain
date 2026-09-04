
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from model.feature_engineering import FEATURE_METADATA, compute_historical_features

def test_feature_metadata_contract():
    """Phase 36 Contract: Must have exactly 23 specific features"""
    expected_features = {
        "amount", "customer_account_age_days", "previous_transaction_count", 
        "previous_fraud_count", "avg_customer_amount", "amount_deviation", 
        "amount_ratio", "time_since_last_txn", "customer_merchant_interaction_count",
        "is_new_customer", "merchant_fraud_rate", "is_new_merchant", "previous_merchant_transaction_count",
        "txns_last_5min", "txns_last_1h", "txns_last_24h", "ip_is_missing", 
        "hour_of_day", "day_of_week",
        "payment_method_card", "payment_method_bank_transfer", 
        "payment_method_wallet", "payment_method_crypto"
    }
    actual_features = set(FEATURE_METADATA.keys())
    
    assert actual_features == expected_features, "FEATURE_METADATA does not strictly match the 23-feature contract"
    
    assert "new_device_flag" not in actual_features
    assert "new_location_flag" not in actual_features
    assert "location_is_missing" not in actual_features

def test_no_current_row_leakage_fraud_count():
    """
    Phase 33 Contract: previous_fraud_count must only count fraud where 
    label_available_at < current_timestamp
    """
    df = pd.DataFrame([
        # Transaction 1: Fraud, but label not available until after txn 2
        {"transaction_id": "1", "customer_id": "C1", "merchant_id": "M1", 
         "timestamp": "2023-01-01T10:00:00Z", "amount": 100, "is_fraud": 1, 
         "label_available_at": "2023-01-02T10:00:00Z", "payment_method": "card"},
        # Transaction 2: Occurs before txn 1 label is available
        {"transaction_id": "2", "customer_id": "C1", "merchant_id": "M1", 
         "timestamp": "2023-01-01T12:00:00Z", "amount": 100, "is_fraud": 0, 
         "label_available_at": None, "payment_method": "card"},
        # Transaction 3: Occurs after txn 1 label is available
        {"transaction_id": "3", "customer_id": "C1", "merchant_id": "M1", 
         "timestamp": "2023-01-03T10:00:00Z", "amount": 100, "is_fraud": 0, 
         "label_available_at": None, "payment_method": "card"}
    ])
    
    out = compute_historical_features(df)
    
    # Sort just to be sure we check the right rows
    out = out.sort_values("timestamp").reset_index(drop=True)
    
    # Txn 1 has no previous history
    assert out.loc[0, "previous_fraud_count"] == 0
    # Txn 2 should NOT see Txn 1's fraud because label is not available yet
    assert out.loc[1, "previous_fraud_count"] == 0
    # Txn 3 should see Txn 1's fraud
    assert out.loc[2, "previous_fraud_count"] == 1

def test_merchant_rate_denominator_consistent():
    """
    Phase 33 Contract: merchant_fraud_rate must only use labeled transactions 
    for both numerator and denominator.
    """
    df = pd.DataFrame([
        # Transaction 1: Labeled legit, available day 2
        {"transaction_id": "1", "customer_id": "C1", "merchant_id": "M1", 
         "timestamp": "2023-01-01T10:00:00Z", "amount": 100, "is_fraud": 0, 
         "label_available_at": "2023-01-02T10:00:00Z", "payment_method": "card"},
        # Transaction 2: Labeled fraud, available day 3
        {"transaction_id": "2", "customer_id": "C2", "merchant_id": "M1", 
         "timestamp": "2023-01-01T12:00:00Z", "amount": 100, "is_fraud": 1, 
         "label_available_at": "2023-01-03T10:00:00Z", "payment_method": "card"},
        # Transaction 3: Scoring at day 2.5. Should see Txn 1, but NOT Txn 2.
        # Rate = 0 / 1 = 0.0
        {"transaction_id": "3", "customer_id": "C3", "merchant_id": "M1", 
         "timestamp": "2023-01-02T12:00:00Z", "amount": 100, "is_fraud": 0, 
         "label_available_at": None, "payment_method": "card"},
        # Transaction 4: Scoring at day 4. Should see Txn 1 and Txn 2.
        # Rate = 1 / 2 = 0.5
        {"transaction_id": "4", "customer_id": "C4", "merchant_id": "M1", 
         "timestamp": "2023-01-04T12:00:00Z", "amount": 100, "is_fraud": 0, 
         "label_available_at": None, "payment_method": "card"}
    ])
    
    out = compute_historical_features(df)
    out = out.sort_values("timestamp").reset_index(drop=True)
    
    assert out.loc[2, "merchant_fraud_rate"] == 0.0
    assert out.loc[3, "merchant_fraud_rate"] == 0.5
