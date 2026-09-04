"""
Tests for the synthetic transaction generator (data/generator.py).

These tests verify:
- Determinism: same seed → same output.
- Variation: different seed → different output.
- Output shape: requested row count is produced.
- Schema conformance: every generated row passes Transaction validation.
- Target existence: is_fraud column is present.
- Class imbalance: fraud is the minority class.
- No obvious target leakage in the generated feature set.
- Basic value constraints across all rows.
- Required columns are all present.
"""

from __future__ import annotations

import pandas as pd
import pytest

from data.generator import generate_transactions
from data.schema import Transaction


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SMALL_N = 200    # Fast for test runs — not a production-size dataset.
_SEED_A = 42
_SEED_B = 99

_REQUIRED_COLUMNS = [
    "label_available_at",
    "transaction_id",
    "customer_id",
    "merchant_id",
    "device_id",
    "ip_address",
    "timestamp",
    "amount",
    "payment_method",
    "location",
    "customer_account_age_days",
    "previous_transaction_count",
    "previous_fraud_count",
    "failed_attempt_count_24h",
    "txns_last_5min",
    "txns_last_1h",
    "txns_last_24h",
    "avg_customer_amount",
    "amount_deviation",
    "merchant_fraud_rate",
    "new_device_flag",
    "new_location_flag",
    "is_fraud",
    "label_available_at",
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def df_a() -> pd.DataFrame:
    return generate_transactions(n=_SMALL_N, seed=_SEED_A)


@pytest.fixture(scope="module")
def df_b() -> pd.DataFrame:
    return generate_transactions(n=_SMALL_N, seed=_SEED_B)


@pytest.fixture(scope="module")
def df_a_repeat() -> pd.DataFrame:
    """Second generation with the same seed — must be identical to df_a."""
    return generate_transactions(n=_SMALL_N, seed=_SEED_A)


# ---------------------------------------------------------------------------
# Shape and structure tests
# ---------------------------------------------------------------------------


class TestOutputShape:
    def test_returns_dataframe(self, df_a):
        assert isinstance(df_a, pd.DataFrame)

    def test_correct_row_count(self, df_a):
        assert len(df_a) == _SMALL_N

    def test_all_required_columns_present(self, df_a):
        missing = [c for c in _REQUIRED_COLUMNS if c not in df_a.columns]
        assert missing == [], f"Missing columns: {missing}"

    def test_no_extra_unlisted_columns(self, df_a):
        extra = [c for c in df_a.columns if c not in _REQUIRED_COLUMNS]
        assert extra == [], f"Unexpected extra columns: {extra}"


# ---------------------------------------------------------------------------
# Determinism tests
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_same_seed_produces_identical_transaction_ids(self, df_a, df_a_repeat):
        assert list(df_a["transaction_id"]) == list(df_a_repeat["transaction_id"])

    def test_same_seed_produces_identical_amounts(self, df_a, df_a_repeat):
        assert list(df_a["amount"]) == list(df_a_repeat["amount"])

    def test_same_seed_produces_identical_fraud_labels(self, df_a, df_a_repeat):
        assert list(df_a["is_fraud"]) == list(df_a_repeat["is_fraud"])

    def test_different_seeds_produce_different_transaction_ids(self, df_a, df_b):
        # With 200 rows from independent seeds this should virtually never collide.
        assert list(df_a["transaction_id"]) != list(df_b["transaction_id"])

    def test_different_seeds_produce_different_fraud_vectors(self, df_a, df_b):
        assert list(df_a["is_fraud"]) != list(df_b["is_fraud"])


# ---------------------------------------------------------------------------
# Class imbalance test
# ---------------------------------------------------------------------------


class TestClassImbalance:
    def test_fraud_is_minority_class(self, df_a):
        fraud_rate = df_a["is_fraud"].mean()
        assert fraud_rate < 0.5, (
            f"Fraud rate {fraud_rate:.2%} is not minority — "
            "check generator class imbalance logic."
        )

    def test_fraud_class_is_not_empty(self, df_a):
        assert df_a["is_fraud"].any(), (
            "No fraudulent transactions generated. "
            "Consider increasing n or checking fraud probability logic."
        )

    def test_legitimate_class_exists(self, df_a):
        assert not df_a["is_fraud"].all(), (
            "All transactions are fraudulent — generator is misconfigured."
        )


# ---------------------------------------------------------------------------
# Value constraint tests
# ---------------------------------------------------------------------------


class TestValueConstraints:
    def test_all_amounts_non_negative(self, df_a):
        assert (df_a["amount"] >= 0).all()

    def test_all_account_ages_non_negative(self, df_a):
        assert (df_a["customer_account_age_days"] >= 0).all()

    def test_all_counts_non_negative(self, df_a):
        count_cols = [
            "previous_transaction_count",
            "previous_fraud_count",
            "failed_attempt_count_24h",
            "txns_last_5min",
            "txns_last_1h",
            "txns_last_24h",
        ]
        for col in count_cols:
            assert (df_a[col] >= 0).all(), f"Negative values found in {col}"

    def test_merchant_fraud_rate_in_bounds(self, df_a):
        assert (df_a["merchant_fraud_rate"] >= 0).all()
        assert (df_a["merchant_fraud_rate"] <= 1).all()

    def test_amount_deviation_non_negative(self, df_a):
        assert (df_a["amount_deviation"] >= 0).all()

    def test_timestamps_are_timezone_aware(self, df_a):
        for ts in df_a["timestamp"]:
            assert ts.tzinfo is not None, f"Naive timestamp found: {ts}"

    def test_all_transaction_ids_are_unique(self, df_a):
        assert df_a["transaction_id"].nunique() == len(df_a)


# ---------------------------------------------------------------------------
# No target leakage test
# ---------------------------------------------------------------------------


class TestNoTargetLeakage:
    def test_is_fraud_not_in_feature_columns(self):
        """
        The Transaction schema's feature_columns() helper must exclude is_fraud.
        This test acts as a regression guard against accidental leakage.
        """
        feature_cols = Transaction.feature_columns()
        assert "is_fraud" not in feature_cols, (
            "LEAKAGE DETECTED: is_fraud appears in feature_columns()."
        )

    def test_transaction_id_not_in_feature_columns(self):
        feature_cols = Transaction.feature_columns()
        assert "transaction_id" not in feature_cols

    def test_feature_target_split_yields_correct_shape(self, df_a):
        feature_cols = Transaction.feature_columns()
        target_col = Transaction.target_column()
        X = df_a[feature_cols]
        y = df_a[target_col]
        assert X.shape == (_SMALL_N, len(feature_cols))
        assert y.shape == (_SMALL_N,)
        assert target_col not in X.columns


# ---------------------------------------------------------------------------
# Schema conformance test (sampled for speed)
# ---------------------------------------------------------------------------


class TestSchemaConformance:
    def test_sample_rows_conform_to_transaction_schema(self, df_a):
        """
        Validate a sample of generated rows against the Pydantic Transaction
        schema.  Validates 10 rows to keep test runtime fast.
        """
        sample = df_a.sample(n=min(10, len(df_a)), random_state=0)
        for _, row in sample.iterrows():
            try:
                Transaction.model_validate(row.to_dict())
            except Exception as exc:
                pytest.fail(
                    f"Generated row failed Transaction schema validation: {exc}\n"
                    f"Row data: {row.to_dict()}"
                )


# ---------------------------------------------------------------------------
# API contract tests
# ---------------------------------------------------------------------------


class TestGeneratorAPI:
    def test_raises_on_zero_n(self):
        with pytest.raises(ValueError, match="n must be >= 1"):
            generate_transactions(n=0, seed=42)

    def test_raises_on_negative_n(self):
        with pytest.raises(ValueError, match="n must be >= 1"):
            generate_transactions(n=-10, seed=42)

    def test_n_equals_one_produces_single_row(self):
        df = generate_transactions(n=1, seed=42)
        assert len(df) == 1
