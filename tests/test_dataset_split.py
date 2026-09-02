"""
Tests for the chronological dataset splitting.

Verifies:
- Split fractions are respected.
- Temporal ordering is perfectly maintained.
- No transaction exists in multiple splits.
"""

import pytest
import pandas as pd

from data.generator import generate_transactions
from model.dataset_split import split_chronological


@pytest.fixture(scope="module")
def sample_dataset() -> pd.DataFrame:
    return generate_transactions(n=1000, seed=42)


def test_split_sizes(sample_dataset):
    train, val, test = split_chronological(sample_dataset, 0.7, 0.15, 0.15)
    
    assert len(train) == 700
    assert len(val) == 150
    assert len(test) == 150
    assert len(train) + len(val) + len(test) == len(sample_dataset)


def test_chronological_ordering(sample_dataset):
    train, val, test = split_chronological(sample_dataset, 0.7, 0.15, 0.15)
    
    train_max_time = train["timestamp"].max()
    val_min_time = val["timestamp"].min()
    val_max_time = val["timestamp"].max()
    test_min_time = test["timestamp"].min()
    
    # Assert strictly ordered boundaries
    assert train_max_time <= val_min_time
    assert val_max_time <= test_min_time


def test_no_overlap(sample_dataset):
    train, val, test = split_chronological(sample_dataset, 0.7, 0.15, 0.15)
    
    train_ids = set(train["transaction_id"])
    val_ids = set(val["transaction_id"])
    test_ids = set(test["transaction_id"])
    
    # Assert mutually exclusive
    assert train_ids.isdisjoint(val_ids)
    assert train_ids.isdisjoint(test_ids)
    assert val_ids.isdisjoint(test_ids)


def test_invalid_fractions(sample_dataset):
    with pytest.raises(ValueError, match="sum to 1.0"):
        split_chronological(sample_dataset, 0.5, 0.5, 0.5)


def test_empty_dataframe():
    empty_df = pd.DataFrame()
    with pytest.raises(ValueError, match="empty DataFrame"):
        split_chronological(empty_df)
