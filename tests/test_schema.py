"""
Tests for the canonical Transaction schema (data/schema.py).

These tests verify:
- Valid transactions are accepted.
- Invalid values are rejected with informative errors.
- The feature/target separation API works correctly.
- Timezone-aware timestamp enforcement.
- Boundary conditions for constrained numeric fields.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from data.schema import PaymentMethod, Transaction


# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------


def _valid_payload(**overrides) -> dict:
    """Return a minimal valid transaction payload, with optional overrides."""
    payload = {
        "transaction_id": "txn_001",
        "customer_id": "cust_0001",
        "merchant_id": "merch_001",
        "device_id": "dev_0001",
        "ip_address": "10.0.0.1",
        "timestamp": datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
        "amount": 150.00,
        "payment_method": PaymentMethod.CARD,
        "location": "London",
        "customer_account_age_days": 365,
        "previous_transaction_count": 50,
        "previous_fraud_count": 0,
        "failed_attempt_count_24h": 0,
        "txns_last_5min": 0,
        "txns_last_1h": 1,
        "txns_last_24h": 3,
        "avg_customer_amount": 150.00,
        "amount_deviation": 0.00,
        "merchant_fraud_rate": 0.02,
        "new_device_flag": False,
        "new_location_flag": False,
        "is_fraud": False,
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# Acceptance tests
# ---------------------------------------------------------------------------


class TestValidTransaction:
    def test_accepts_minimal_valid_transaction(self):
        txn = Transaction.model_validate(_valid_payload())
        assert txn.transaction_id == "txn_001"
        assert txn.is_fraud is False

    def test_accepts_optional_fields_as_none(self):
        txn = Transaction.model_validate(
            _valid_payload(ip_address=None, location=None)
        )
        assert txn.ip_address is None
        assert txn.location is None

    def test_accepts_zero_amount(self):
        txn = Transaction.model_validate(_valid_payload(amount=0.0, amount_deviation=0.0, avg_customer_amount=0.0))
        assert txn.amount == 0.0

    def test_accepts_fraud_true(self):
        txn = Transaction.model_validate(_valid_payload(is_fraud=True))
        assert txn.is_fraud is True

    def test_accepts_all_payment_methods(self):
        for method in PaymentMethod:
            txn = Transaction.model_validate(_valid_payload(payment_method=method))
            assert txn.payment_method == method

    def test_accepts_merchant_fraud_rate_at_boundaries(self):
        for rate in (0.0, 1.0):
            txn = Transaction.model_validate(_valid_payload(merchant_fraud_rate=rate))
            assert txn.merchant_fraud_rate == rate

    def test_accepts_new_customer_with_zero_history(self):
        txn = Transaction.model_validate(
            _valid_payload(
                customer_account_age_days=0,
                previous_transaction_count=0,
                previous_fraud_count=0,
                avg_customer_amount=0.0,
                amount_deviation=0.0,
            )
        )
        assert txn.customer_account_age_days == 0


# ---------------------------------------------------------------------------
# Rejection tests
# ---------------------------------------------------------------------------


class TestInvalidTransaction:
    def test_rejects_negative_amount(self):
        with pytest.raises(ValidationError, match="amount"):
            Transaction.model_validate(_valid_payload(amount=-0.01, amount_deviation=0.0))

    def test_rejects_merchant_fraud_rate_above_one(self):
        with pytest.raises(ValidationError, match="merchant_fraud_rate"):
            Transaction.model_validate(_valid_payload(merchant_fraud_rate=1.01))

    def test_rejects_merchant_fraud_rate_below_zero(self):
        with pytest.raises(ValidationError, match="merchant_fraud_rate"):
            Transaction.model_validate(_valid_payload(merchant_fraud_rate=-0.01))

    def test_rejects_naive_timestamp(self):
        naive_ts = datetime(2024, 6, 1, 12, 0, 0)  # no tzinfo
        with pytest.raises(ValidationError, match="timezone"):
            Transaction.model_validate(_valid_payload(timestamp=naive_ts))

    def test_rejects_negative_transaction_count(self):
        with pytest.raises(ValidationError, match="previous_transaction_count"):
            Transaction.model_validate(_valid_payload(previous_transaction_count=-1))

    def test_rejects_negative_fraud_count(self):
        with pytest.raises(ValidationError, match="previous_fraud_count"):
            Transaction.model_validate(_valid_payload(previous_fraud_count=-1))

    def test_rejects_negative_account_age(self):
        with pytest.raises(ValidationError, match="customer_account_age_days"):
            Transaction.model_validate(_valid_payload(customer_account_age_days=-1))

    def test_rejects_negative_failed_attempts(self):
        with pytest.raises(ValidationError, match="failed_attempt_count_24h"):
            Transaction.model_validate(_valid_payload(failed_attempt_count_24h=-1))

    def test_rejects_negative_amount_deviation(self):
        with pytest.raises(ValidationError, match="amount_deviation"):
            Transaction.model_validate(_valid_payload(amount_deviation=-1.0, avg_customer_amount=0.0))

    def test_rejects_empty_transaction_id(self):
        with pytest.raises(ValidationError):
            Transaction.model_validate(_valid_payload(transaction_id=""))

    def test_rejects_inconsistent_amount_deviation(self):
        # amount=500, avg=100 → expected deviation ≈ 400; providing 5 is wrong.
        with pytest.raises(ValidationError, match="amount_deviation"):
            Transaction.model_validate(
                _valid_payload(amount=500.0, avg_customer_amount=100.0, amount_deviation=5.0)
            )


# ---------------------------------------------------------------------------
# Feature / target separation tests
# ---------------------------------------------------------------------------


class TestFeatureTargetSeparation:
    def test_target_column_is_is_fraud(self):
        assert Transaction.target_column() == "is_fraud"

    def test_is_fraud_not_in_feature_columns(self):
        assert "is_fraud" not in Transaction.feature_columns()

    def test_transaction_id_not_in_feature_columns(self):
        assert "transaction_id" not in Transaction.feature_columns()

    def test_feature_columns_non_empty(self):
        assert len(Transaction.feature_columns()) > 0

    def test_feature_columns_include_key_risk_signals(self):
        features = Transaction.feature_columns()
        expected = {
            "amount",
            "txns_last_5min",
            "txns_last_1h",
            "failed_attempt_count_24h",
            "new_device_flag",
            "new_location_flag",
            "merchant_fraud_rate",
            "amount_deviation",
        }
        assert expected.issubset(set(features)), (
            f"Missing key risk signals from feature_columns(): "
            f"{expected - set(features)}"
        )
