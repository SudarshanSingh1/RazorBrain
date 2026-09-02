"""
Tests for Rule Engine.
"""

import pytest
import pandas as pd
import numpy as np

from data.generator import generate_transactions
from model.feature_engineering import compute_historical_features, fit_transform_features, transform_features, get_feature_matrix
from model.dataset_split import split_chronological
from model.rule_engine import extract_training_thresholds, evaluate_rules


@pytest.fixture(scope="module")
def rule_fixtures():
    df = generate_transactions(n=1000, seed=42)
    df_hist = compute_historical_features(df)
    train, val, test = split_chronological(df_hist)
    
    train_feat, state = fit_transform_features(train)
    X_train = get_feature_matrix(train_feat)
    
    thresholds = extract_training_thresholds(X_train)
    return thresholds, X_train


def test_extract_thresholds(rule_fixtures):
    thresholds, _ = rule_fixtures
    assert "amount_p99" in thresholds
    assert "txns_last_24h_p99" in thresholds
    assert thresholds["merchant_fraud_rate_p95"] >= 0.05  # Guardrail test


def test_normal_transaction_no_rules_triggered(rule_fixtures):
    thresholds, X_train = rule_fixtures
    
    # Construct normal transaction (below thresholds)
    txn = pd.DataFrame([X_train.iloc[0].to_dict()])
    for col in txn.columns:
        txn[col] = 0.0
        
    evidence_batch = evaluate_rules(txn, thresholds)
    assert len(evidence_batch) == 1
    assert len(evidence_batch[0]) == 0  # No rules triggered


def test_velocity_new_device(rule_fixtures):
    thresholds, X_train = rule_fixtures
    
    txn = pd.DataFrame([X_train.iloc[0].to_dict()])
    txn["txns_last_24h"] = thresholds["txns_last_24h_p99"] + 10
    txn["new_device_flag"] = 1.0
    
    evidence_batch = evaluate_rules(txn, thresholds)
    triggered = [e["rule_id"] for e in evidence_batch[0]]
    assert "velocity_new_device" in triggered
    
    # Check Severity and Status
    rule_evidence = [e for e in evidence_batch[0] if e["rule_id"] == "velocity_new_device"][0]
    assert rule_evidence["severity"] == "HIGH"
    assert rule_evidence["status"] == "TRIGGERED"
    assert "txns_last_24h" in rule_evidence["observed_values"]
    assert "txns_last_24h_p99" in rule_evidence["thresholds"]


def test_single_signal_safety(rule_fixtures):
    """
    Test that a single weak signal (high amount) triggers only LOW severity.
    """
    thresholds, X_train = rule_fixtures
    
    txn = pd.DataFrame([X_train.iloc[0].to_dict()])
    txn["amount"] = thresholds["amount_p99"] + 1000
    
    evidence_batch = evaluate_rules(txn, thresholds)
    triggered = [e["rule_id"] for e in evidence_batch[0]]
    assert "extreme_amount_single_signal" in triggered
    
    rule_evidence = [e for e in evidence_batch[0] if e["rule_id"] == "extreme_amount_single_signal"][0]
    assert rule_evidence["severity"] == "LOW"  # Safety check
    assert rule_evidence["status"] == "TRIGGERED"


def test_missing_data_rule(rule_fixtures):
    thresholds, X_train = rule_fixtures
    
    txn = pd.DataFrame([X_train.iloc[0].to_dict()])
    txn["ip_is_missing"] = 1.0
    
    evidence_batch = evaluate_rules(txn, thresholds)
    triggered = [e["rule_id"] for e in evidence_batch[0]]
    assert "missing_critical_context" in triggered
    
    rule_evidence = [e for e in evidence_batch[0] if e["rule_id"] == "missing_critical_context"][0]
    assert rule_evidence["severity"] == "INFO"


def test_unavailable_handling(rule_fixtures):
    thresholds, X_train = rule_fixtures
    
    txn = pd.DataFrame([X_train.iloc[0].to_dict()])
    txn["amount"] = np.nan  # Break amount rule
    
    evidence_batch = evaluate_rules(txn, thresholds)
    triggered = [e["rule_id"] for e in evidence_batch[0]]
    assert "extreme_amount_single_signal" not in triggered


def test_determinism(rule_fixtures):
    thresholds, X_train = rule_fixtures
    
    txn = pd.DataFrame([X_train.iloc[0].to_dict()])
    txn["amount"] = thresholds["amount_p99"] + 1000
    txn["txns_last_24h"] = thresholds["txns_last_24h_p99"] + 10
    txn["new_device_flag"] = 1.0
    
    ev1 = evaluate_rules(txn, thresholds)
    ev2 = evaluate_rules(txn, thresholds)
    
    assert ev1 == ev2
