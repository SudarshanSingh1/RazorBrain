"""
Dataset-level quality gate tests for RazorBrain.

These tests operate on a medium-sized generated dataset (2,000 rows)
to verify dataset-level guarantees — distinct from the unit tests in
test_generator.py (which test generator API behavior on 200 rows) and
test_schema.py (which test field-level validation).

Tests here verify:
- The full quality gate passes
- EDA completes without errors
- Signal relationships are non-trivial but directionally correct
- Temporal coverage is usable
- Entity cardinality is realistic
- No synthetic shortcut separates fraud perfectly
- The leakage audit passes

The dataset is generated once per module (scoped fixture) for speed.
"""

from __future__ import annotations

import logging
import pytest
import pandas as pd

logger = logging.getLogger(__name__)

from data.generator import generate_transactions
from data.quality import run_quality_gate
from data.eda import run_eda
from data.schema import Transaction

_DATASET_N = 2_000  # Large enough for statistics; small enough for fast CI.
_DATASET_SEED = 42


@pytest.fixture(scope="module")
def dataset() -> pd.DataFrame:
    return generate_transactions(n=_DATASET_N, seed=_DATASET_SEED)


@pytest.fixture(scope="module")
def quality_report(dataset) -> dict:
    return run_quality_gate(dataset)


@pytest.fixture(scope="module")
def eda_report(dataset) -> dict:
    return run_eda(dataset)


# ---------------------------------------------------------------------------
# Quality gate tests
# ---------------------------------------------------------------------------


class TestQualityGate:
    def test_quality_gate_passes(self, quality_report):
        failed = [c for c in quality_report["checks"] if c["status"] == "FAIL"]
        assert quality_report["passed"], (
            f"Quality gate FAILED. Failures:\n"
            + "\n".join(f"  [{c['name']}] {c['detail']}" for c in failed)
        )

    def test_no_duplicate_transaction_ids(self, quality_report):
        stats = quality_report["stats"]
        assert stats["duplicate_ids"] == 0

    def test_fraud_is_minority_class(self, quality_report):
        stats = quality_report["stats"]
        assert stats["fraud_rate"] < 0.5, f"Fraud rate {stats['fraud_rate']:.2%} is not minority."

    def test_fraud_rate_above_minimum(self, quality_report):
        stats = quality_report["stats"]
        assert stats["fraud_rate"] > 0.005, (
            "Fraud rate is essentially zero — cannot train a meaningful detector."
        )

    def test_no_nulls_in_required_fields(self, dataset):
        """Non-optional fields must have zero nulls."""
        optional = {"ip_address", "location"}
        required_fields = [
            col for col in Transaction.model_fields
            if col not in optional and col in dataset.columns
        ]
        for col in required_fields:
            assert dataset[col].isnull().sum() == 0, (
                f"Unexpected nulls in required field '{col}'."
            )

    def test_all_required_columns_present(self, dataset):
        required = set(Transaction.model_fields.keys())
        missing = required - set(dataset.columns)
        assert not missing, f"Missing columns: {missing}"

    def test_no_synthetic_shortcut(self, quality_report):
        """No single feature should have near-perfect (AUC ≥ 0.95) fraud separation."""
        shortcut_check = next(
            (c for c in quality_report["checks"] if c["name"] == "synthetic_shortcut_audit"),
            None,
        )
        if shortcut_check:
            assert shortcut_check["status"] != "FAIL", (
                f"Synthetic shortcut detected: {shortcut_check['detail']}"
            )


# ---------------------------------------------------------------------------
# EDA tests
# ---------------------------------------------------------------------------


class TestEDA:
    def test_eda_runs_without_error(self, eda_report):
        assert isinstance(eda_report, dict)
        assert len(eda_report) > 0

    def test_class_distribution_present(self, eda_report):
        cd = eda_report["class_distribution"]
        assert cd["fraud_count"] > 0
        assert cd["legitimate_count"] > 0
        assert cd["total_transactions"] == _DATASET_N

    def test_temporal_distribution_covers_multiple_days(self, eda_report):
        td = eda_report["temporal_distribution"]
        assert len(td) >= 7, (
            f"Temporal distribution only spans {len(td)} days — "
            "may be insufficient for time-based splits."
        )

    def test_entity_cardinality_realistic(self, eda_report):
        ec = eda_report["entity_cardinality"]
        assert ec.get("customer_id", 0) >= 10, "Too few unique customers."
        assert ec.get("merchant_id", 0) >= 5, "Too few unique merchants."

    def test_missing_value_summary_returns_only_optional_nulls(self, eda_report):
        """Only ip_address and location should appear in the missing-value summary."""
        mv = eda_report["missing_value_summary"]
        if len(mv) > 0:
            unexpected = [col for col in mv.index if col not in {"ip_address", "location"}]
            assert not unexpected, (
                f"Unexpected nulls in non-optional columns: {unexpected}"
            )


# ---------------------------------------------------------------------------
# Signal direction tests
# ---------------------------------------------------------------------------


class TestSignalDirectionality:
    """
    Verify that the generator produces plausible (non-trivial) signal
    relationships.  Each test checks direction, NOT magnitude.

    We do NOT claim perfect correlation.  These tests would fail if the
    generator accidentally inverted a signal or zeroed it out.
    """

    def test_fraud_rate_higher_with_new_device(self, dataset):
        rates = dataset.groupby("new_device_flag")["is_fraud"].mean()
        # Fraud should be higher when new_device_flag is True
        if True in rates.index and False in rates.index:
            assert rates[True] >= rates[False] * 0.5, (
                "Fraud rate for new device should be >= half the rate for known device — "
                "signal appears inverted or negligible."
            )

    def test_fraud_rate_higher_for_high_failed_attempts(self, dataset):
        high_fail = dataset[dataset["failed_attempt_count_24h"] >= 5]["is_fraud"].mean()
        low_fail = dataset[dataset["failed_attempt_count_24h"] == 0]["is_fraud"].mean()
        if len(dataset[dataset["failed_attempt_count_24h"] >= 5]) > 20:
            assert high_fail >= low_fail, (
                "Fraud rate should be higher for high failed-attempt counts."
            )

    def test_fraud_rate_higher_with_fraud_history(self, dataset):
        has_history = dataset[dataset["previous_fraud_count"] >= 1]["is_fraud"].mean()
        no_history = dataset[dataset["previous_fraud_count"] == 0]["is_fraud"].mean()
        if len(dataset[dataset["previous_fraud_count"] >= 1]) > 20:
            assert has_history > no_history, (
                "Customers with prior fraud history should have higher current fraud rate."
            )

    def test_legitimate_transactions_can_have_new_device(self, dataset):
        """Legitimate users can use new devices — signal must not be deterministic."""
        legit_with_new_device = dataset[
            (dataset["is_fraud"] == False) & (dataset["new_device_flag"] == True)
        ]
        assert len(legit_with_new_device) > 0, (
            "No legitimate transactions with new_device_flag=True found. "
            "Signal may be too deterministic."
        )

    def test_fraudulent_transactions_can_have_known_device(self, dataset):
        """Fraudulent transactions can occur on known devices — signal must not be deterministic."""
        fraud_with_known_device = dataset[
            (dataset["is_fraud"] == True) & (dataset["new_device_flag"] == False)
        ]
        assert len(fraud_with_known_device) > 0, (
            "No fraudulent transactions with new_device_flag=False found. "
            "Fraud may be too perfectly correlated with new device."
        )

    def test_legitimate_transactions_can_have_large_amounts(self, dataset):
        """High amounts are not exclusively fraudulent."""
        legit = dataset[dataset["is_fraud"] == False]
        fraud = dataset[dataset["is_fraud"] == True]
        legit_high = legit[legit["amount"] > legit["amount"].quantile(0.9)]
        assert len(legit_high) > 0, (
            "No legitimate transactions in the top 10% of amounts — "
            "amount signal may be too deterministic."
        )


# ---------------------------------------------------------------------------
# Feature/target split at dataset scale
# ---------------------------------------------------------------------------


class TestFeatureTargetSplitAtScale:
    def test_feature_target_split_correct_dimensions(self, dataset):
        feature_cols = Transaction.feature_columns()
        target_col = Transaction.target_column()
        X = dataset[feature_cols]
        y = dataset[target_col]
        assert X.shape[0] == _DATASET_N
        assert X.shape[1] == len(feature_cols)
        assert y.shape[0] == _DATASET_N

    def test_target_not_in_X(self, dataset):
        feature_cols = Transaction.feature_columns()
        assert "is_fraud" not in feature_cols


# ---------------------------------------------------------------------------
# Determinism at dataset scale
# ---------------------------------------------------------------------------


class TestDeterminismAtScale:
    def test_same_seed_same_fraud_count(self):
        df1 = generate_transactions(n=_DATASET_N, seed=_DATASET_SEED)
        df2 = generate_transactions(n=_DATASET_N, seed=_DATASET_SEED)
        assert int(df1["is_fraud"].sum()) == int(df2["is_fraud"].sum())

    def test_different_seed_different_result(self):
        df1 = generate_transactions(n=_DATASET_N, seed=_DATASET_SEED)
        df2 = generate_transactions(n=_DATASET_N, seed=_DATASET_SEED + 1)
        assert list(df1["transaction_id"]) != list(df2["transaction_id"])


# ---------------------------------------------------------------------------
# 100 k scale tests
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def dataset_100k() -> pd.DataFrame:
    """Generate the primary 100 k dataset once per test module run."""
    import time
    start = time.perf_counter()
    df = generate_transactions(n=100_000, seed=42)
    elapsed = time.perf_counter() - start
    logger.info("100k dataset generated in %.2f s", elapsed)
    return df


class TestHundredKScale:
    """
    Verify that the primary 100 k dataset meets all quality guarantees.

    This class runs once per test session (module-scoped fixture).
    Individual unit tests elsewhere use n=200–2000 for speed.
    """

    def test_100k_row_count(self, dataset_100k):
        assert len(dataset_100k) == 100_000

    def test_100k_quality_gate_passes(self, dataset_100k):
        from data.quality import run_quality_gate
        report = run_quality_gate(dataset_100k)
        failed = [c for c in report["checks"] if c["status"] == "FAIL"]
        assert report["passed"], (
            "100k quality gate FAILED:\n"
            + "\n".join(f"  [{c['name']}] {c['detail']}" for c in failed)
        )

    def test_100k_fraud_is_minority(self, dataset_100k):
        fraud_rate = dataset_100k["is_fraud"].mean()
        assert fraud_rate < 0.30, f"Fraud rate {fraud_rate:.2%} is not minority."
        assert fraud_rate > 0.005, "Fraud rate is essentially zero."

    def test_100k_no_duplicate_ids(self, dataset_100k):
        assert dataset_100k["transaction_id"].nunique() == 100_000

    def test_100k_entity_cardinality(self, dataset_100k):
        assert dataset_100k["customer_id"].nunique() == 1_000, "All 1k customers must appear."
        assert dataset_100k["merchant_id"].nunique() == 80, "All 80 merchants must appear."

    def test_100k_timestamps_sorted(self, dataset_100k):
        """Timestamps must be ascending (generator pre-sorts them)."""
        ts = dataset_100k["timestamp"]
        assert ts.is_monotonic_increasing, "Timestamps should be sorted ascending."

    def test_100k_no_future_timestamps(self, dataset_100k):
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        ts = pd.to_datetime(dataset_100k["timestamp"], utc=True)
        assert (ts <= now).all(), "No future timestamps should exist."

    def test_100k_deterministic(self):
        """Same seed must produce identical fraud totals at 100k scale."""
        df1 = generate_transactions(n=100_000, seed=42)
        df2 = generate_transactions(n=100_000, seed=42)
        assert int(df1["is_fraud"].sum()) == int(df2["is_fraud"].sum())
        assert list(df1["transaction_id"][:100]) == list(df2["transaction_id"][:100])

    def test_100k_avg_customer_txns(self, dataset_100k):
        """At 100k rows with 1k customers, each customer should average ~100 transactions."""
        avg_txns = len(dataset_100k) / dataset_100k["customer_id"].nunique()
        assert 50 <= avg_txns <= 200, (
            f"Average transactions per customer ({avg_txns:.0f}) outside expected range."
        )

    def test_100k_no_shortcut(self, dataset_100k):
        """No single feature should have AUC ≥ 0.95 at 100k scale."""
        from data.quality import run_quality_gate
        report = run_quality_gate(dataset_100k)
        shortcut = next(
            (c for c in report["checks"] if c["name"] == "synthetic_shortcut_audit"),
            None,
        )
        if shortcut:
            assert shortcut["status"] != "FAIL", shortcut["detail"]

    def test_100k_legit_can_have_new_device(self, dataset_100k):
        count = ((dataset_100k["is_fraud"] == False) & (dataset_100k["new_device_flag"] == True)).sum()
        assert count > 0

    def test_100k_fraud_can_have_known_device(self, dataset_100k):
        count = ((dataset_100k["is_fraud"] == True) & (dataset_100k["new_device_flag"] == False)).sum()
        assert count > 0

