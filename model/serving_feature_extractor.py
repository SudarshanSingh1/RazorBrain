"""
Authoritative serving feature extractor for the Razorpay Serving Model.
Produces exactly the 15 features defined by the feature contract.
Uses only information genuinely available at scoring time from a Razorpay payment.
Does not fabricate values. Does not use ground-truth labels.
Does not use the serving test set.
"""
import math
import datetime
import logging
from typing import Any, Dict, Optional, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

# Canonical 15-feature contract (order matches training)
SERVING_FEATURES = [
    "amount",
    "log_amount",
    "hour_of_day",
    "day_of_week",
    "email_domain",
    "email_domain_missing",
    "card_network",
    "card_type",
    "previous_transaction_count",
    "is_new_customer",
    "avg_customer_amount",
    "amount_deviation",
    "amount_ratio",
    "txns_last_1h",
    "txns_last_24h",
]

# Features that must never enter the model
REJECTED_FEATURES = {
    "V1", "V2", "V3", "V95", "V96",  # IEEE-CIS V-series
    "id_01", "id_02", "id_30", "id_31",  # IEEE-CIS id-series
    "DeviceType", "DeviceInfo",  # IEEE-CIS device
    "TransactionDT",  # IEEE-CIS epoch — not real time
    "isFraud",  # Ground truth — never
    "card1", "card2", "card3", "card4", "card5", "card6",  # IEEE-CIS cards
    "addr1", "addr2",  # IEEE-CIS address
    "dist1", "dist2",  # IEEE-CIS distance
    "P_emaildomain", "R_emaildomain",  # IEEE-CIS email
    "M1", "M2", "M3", "M4", "M5", "M6", "M7", "M8", "M9",  # IEEE-CIS match flags
}

# Safe cold-start defaults for history-derived features
_COLD_START = {
    "previous_transaction_count": 0,
    "is_new_customer": 1,
    "avg_customer_amount": 0.0,
    "amount_deviation": 0.0,
    "amount_ratio": 1.0,
    "txns_last_1h": 0,
    "txns_last_24h": 0,
}

# Availability flags template
_AVAILABILITY_DEFAULTS = {f: False for f in SERVING_FEATURES}


class ServingFeatureExtractorError(Exception):
    pass


def _extract_email_domain(email: Optional[str]) -> Tuple[str, int]:
    """Returns (domain_str, missing_flag). Never fabricates."""
    if not email or "@" not in email:
        return "MISSING", 1
    parts = email.split("@")
    domain = parts[-1].strip().lower()
    if not domain:
        return "MISSING", 1
    return domain, 0


def _extract_timestamp_features(timestamp_iso: str) -> Tuple[Optional[int], Optional[int]]:
    """
    Extract hour_of_day and day_of_week from a real ISO-8601 UTC timestamp.
    Returns (None, None) if timestamp is unparseable.
    Does NOT derive these from IEEE-CIS TransactionDT — that is not real time.
    """
    try:
        ts = datetime.datetime.fromisoformat(timestamp_iso.replace("Z", "+00:00"))
        return ts.hour, ts.weekday()  # weekday(): 0=Monday … 6=Sunday
    except Exception:
        logger.warning(f"Could not parse timestamp: {timestamp_iso!r}")
        return None, None


def extract_serving_features(
    payment: Dict[str, Any],
    history: Dict[str, Any],
) -> Tuple[pd.DataFrame, Dict[str, bool]]:
    """
    Produce a single-row DataFrame with exactly the 15 contract features.

    Parameters
    ----------
    payment : dict
        Canonical payment fields extracted from the Razorpay adapter:
          - amount (float, main units)
          - timestamp (ISO-8601 UTC string)
          - email (str or None)
          - card_network (str or None)
          - card_type (str or None)
    history : dict
        Pre-computed historical features from the DB. Cold-start safe.
        Expected keys: previous_transaction_count, is_new_customer,
        avg_customer_amount, amount_deviation, amount_ratio,
        txns_last_1h, txns_last_24h.

    Returns
    -------
    (X, availability) where X is a 1-row DataFrame with SERVING_FEATURES columns
    and availability maps each feature to a boolean (True = genuinely available).
    """
    # Reject any rejected features that may have leaked in
    for bad in REJECTED_FEATURES:
        if bad in payment:
            raise ServingFeatureExtractorError(
                f"Rejected feature '{bad}' must not enter serving extraction."
            )

    availability: Dict[str, bool] = dict(_AVAILABILITY_DEFAULTS)
    row: Dict[str, Any] = {}

    # ── amount ────────────────────────────────────────────────────────────────
    amount = float(payment.get("amount", 0.0))
    row["amount"] = amount
    availability["amount"] = True

    # ── log_amount ────────────────────────────────────────────────────────────
    row["log_amount"] = math.log1p(amount)
    availability["log_amount"] = True

    # ── hour_of_day, day_of_week ──────────────────────────────────────────────
    ts_str = payment.get("timestamp", "")
    hour, dow = _extract_timestamp_features(ts_str)
    row["hour_of_day"] = hour if hour is not None else 0
    availability["hour_of_day"] = hour is not None
    row["day_of_week"] = dow if dow is not None else 0
    availability["day_of_week"] = dow is not None

    # ── email_domain, email_domain_missing ────────────────────────────────────
    domain, missing_flag = _extract_email_domain(payment.get("email"))
    row["email_domain"] = domain
    row["email_domain_missing"] = missing_flag
    availability["email_domain"] = missing_flag == 0
    availability["email_domain_missing"] = True  # always computable

    # ── card_network ──────────────────────────────────────────────────────────
    card_network = payment.get("card_network")
    if card_network and isinstance(card_network, str) and card_network.strip():
        row["card_network"] = card_network.strip().lower()
        availability["card_network"] = True
    else:
        row["card_network"] = "MISSING"
        availability["card_network"] = False

    # ── card_type ─────────────────────────────────────────────────────────────
    card_type = payment.get("card_type")
    if card_type and isinstance(card_type, str) and card_type.strip():
        row["card_type"] = card_type.strip().lower()
        availability["card_type"] = True
    else:
        row["card_type"] = "MISSING"
        availability["card_type"] = False

    # ── History-derived features ──────────────────────────────────────────────
    # Use DB-provided values; fall back to cold-start defaults.
    # Current transaction is already excluded by the DB query (strict < timestamp).
    prev_count = history.get("previous_transaction_count", _COLD_START["previous_transaction_count"])
    is_new = history.get("is_new_customer", _COLD_START["is_new_customer"])
    avg_amt = history.get("avg_customer_amount", _COLD_START["avg_customer_amount"])
    deviation = history.get("amount_deviation", _COLD_START["amount_deviation"])
    txns_1h = history.get("txns_last_1h", _COLD_START["txns_last_1h"])
    txns_24h = history.get("txns_last_24h", _COLD_START["txns_last_24h"])

    # amount_ratio: ratio of current amount to customer average; 1.0 if no history
    if avg_amt and avg_amt > 0:
        ratio = amount / avg_amt
    else:
        ratio = 1.0

    row["previous_transaction_count"] = int(prev_count)
    row["is_new_customer"] = int(is_new)
    row["avg_customer_amount"] = float(avg_amt)
    row["amount_deviation"] = float(deviation)
    row["amount_ratio"] = float(ratio)
    row["txns_last_1h"] = int(txns_1h)
    row["txns_last_24h"] = int(txns_24h)

    # Mark history features as available if we have actual history
    hist_available = prev_count > 0
    for feat in ("previous_transaction_count", "is_new_customer", "avg_customer_amount",
                 "amount_deviation", "amount_ratio", "txns_last_1h", "txns_last_24h"):
        availability[feat] = hist_available

    # Always mark count/is_new as available (cold-start is a valid state)
    availability["previous_transaction_count"] = True
    availability["is_new_customer"] = True

    # ── Assemble DataFrame in exact contract order ─────────────────────────────
    X = pd.DataFrame([{f: row[f] for f in SERVING_FEATURES}])

    # Final guard: reject any extra columns that somehow arrived
    extra_cols = [c for c in X.columns if c not in SERVING_FEATURES]
    if extra_cols:
        raise ServingFeatureExtractorError(f"Extra columns after extraction: {extra_cols}")

    return X, availability
