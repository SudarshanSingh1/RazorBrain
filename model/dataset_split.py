"""
Chronological dataset splitting module for RazorBrain.

Provides deterministic, time-aware splitting of the transaction dataset
into train, validation, and held-out test sets.
"""

from __future__ import annotations

import logging

import pandas as pd

logger = logging.getLogger(__name__)


def split_chronological(
    df: pd.DataFrame, 
    train_frac: float = 0.70, 
    val_frac: float = 0.15, 
    test_frac: float = 0.15
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Split the dataset chronologically into train, validation, and test sets.
    
    The splits are strictly ordered by time: 
    Train < Validation < Test.
    
    Parameters
    ----------
    df : pd.DataFrame
        The full dataset to split.
    train_frac : float
        Fraction of data for the training set.
    val_frac : float
        Fraction of data for the validation set.
    test_frac : float
        Fraction of data for the held-out test set.
        
    Returns
    -------
    tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]
        The (train, val, test) DataFrames.
        
    Raises
    ------
    ValueError
        If the fractions do not sum to 1.0 (within epsilon), or if 
        the dataset is empty.
    """
    total = train_frac + val_frac + test_frac
    if abs(total - 1.0) > 1e-5:
        raise ValueError(f"Split fractions must sum to 1.0, got {total}")
        
    if len(df) == 0:
        raise ValueError("Cannot split an empty DataFrame.")
        
    # Ensure strict temporal ordering
    df = df.sort_values("timestamp").reset_index(drop=True)
    n = len(df)
    
    train_end = int(n * train_frac)
    val_end = train_end + int(n * val_frac)
    
    train_df = df.iloc[:train_end].copy()
    val_df = df.iloc[train_end:val_end].copy()
    test_df = df.iloc[val_end:].copy()
    
    logger.info(
        "Split %d rows: Train=%d, Val=%d, Test=%d", 
        n, len(train_df), len(val_df), len(test_df)
    )
    
    return train_df, val_df, test_df
