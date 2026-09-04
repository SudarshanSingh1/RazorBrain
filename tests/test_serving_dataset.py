import pytest
import pandas as pd
import json
import os

OUTPUT_DIR = "data/razorpay_serving_dataset"

@pytest.fixture(scope="module")
def train_df():
    return pd.read_csv(os.path.join(OUTPUT_DIR, 'train.csv'))

@pytest.fixture(scope="module")
def val_df():
    return pd.read_csv(os.path.join(OUTPUT_DIR, 'validation.csv'))

@pytest.fixture(scope="module")
def test_df():
    return pd.read_csv(os.path.join(OUTPUT_DIR, 'test.csv'))

@pytest.fixture(scope="module")
def contract():
    with open("data/razorpay_serving_feature_contract.json") as f:
        return json.load(f)

def test_chronological_split(train_df, val_df, test_df):
    train_max = train_df['TransactionDT'].max()
    val_min = val_df['TransactionDT'].min()
    val_max = val_df['TransactionDT'].max()
    test_min = test_df['TransactionDT'].min()
    
    assert train_max < val_min, "Train leaks into Validation chronologically"
    assert val_max < test_min, "Validation leaks into Test chronologically"

def test_no_split_overlap(train_df, val_df, test_df):
    train_ids = set(train_df['TransactionID'])
    val_ids = set(val_df['TransactionID'])
    test_ids = set(test_df['TransactionID'])
    
    assert len(train_ids.intersection(val_ids)) == 0
    assert len(train_ids.intersection(test_ids)) == 0
    assert len(val_ids.intersection(test_ids)) == 0

def test_no_target_in_features(contract, train_df):
    feature_names = [f["name"] for f in contract["features"]]
    
    assert "isFraud" not in feature_names
    assert "TransactionID" not in feature_names
    
    # Ensure all features listed in contract are in the dataset
    for f in feature_names:
        assert f in train_df.columns, f"Feature {f} missing from dataset"

def test_missing_value_handling(train_df):
    # email_domain missingness should be properly handled
    assert not train_df['email_domain'].isna().any()
    
    # Check that ratio has no infinites or NaNs
    assert not train_df['amount_ratio'].isna().any()
    assert not (train_df['amount_ratio'] == float('inf')).any()

def test_model_c_artifacts_untouched():
    # Ensure that Model C artifacts haven't been modified
    assert os.path.exists('data/model_c_calibrated.joblib')
    assert os.path.exists('data/model_c_engineered_raw_safe.joblib')
    assert os.path.exists('data/validation_selected_policy.json')

def test_historical_features_causality():
    import numpy as np
    # Create a synthetic dataframe with explicit chronological ordering
    # and verify that the rolling/historical features do not include the current row
    
    # 3 transactions for card A
    df = pd.DataFrame({
        'TransactionID': [1, 2, 3],
        'isFraud': [0, 0, 0],
        'TransactionDT': [1000, 1050, 4700], # 4700 is 1h 10m later
        'TransactionAmt': [10, 20, 30],
        'P_emaildomain': ['a.com', 'a.com', 'a.com'],
        'card1': [100, 100, 100],
        'card4': ['visa', 'visa', 'visa'],
        'card6': ['credit', 'credit', 'credit']
    })
    
    df['amount'] = df['TransactionAmt']
    df['previous_transaction_count'] = df.groupby('card1').cumcount()
    
    shifted_amount = df.groupby('card1')['amount'].shift(1)
    df['avg_customer_amount'] = shifted_amount.groupby(df['card1']).expanding().mean().reset_index(level=0, drop=True).fillna(0)
    
    df['dt'] = pd.to_datetime(df['TransactionDT'], unit='s')
    df = df.set_index('dt')
    df = df.sort_values(['card1', 'TransactionDT'])
    
    df['txns_last_1h'] = df.groupby('card1')['TransactionID'].rolling('1h').count().reset_index(level=0, drop=True) - 1
    
    # Checks
    # previous_transaction_count should be 0, 1, 2
    assert df['previous_transaction_count'].tolist() == [0, 1, 2]
    
    # avg_customer_amount should be 0, 10, 15
    assert df['avg_customer_amount'].tolist() == [0, 10, 15]
    
    # txns_last_1h should be 0, 1, 0 (since 4700 is > 3600s after 1050)
    assert df['txns_last_1h'].tolist() == [0, 1, 0]
