"""
Deterministic synthetic transaction generator for RazorBrain.

PURPOSE
-------
Generates realistic-but-synthetic transaction datasets for development,
testing, and model training.  All generation is controlled by a random
seed to ensure full reproducibility.

DESIGN PRINCIPLES
-----------------
1. Entity reuse — transactions are generated against a fixed pool of
   customers, merchants, devices, and locations.  This lets later behavioral
   feature engineering find meaningful patterns across a customer's history.

2. Realistic signal relationships — fraud probability is elevated by
   combinations of risk signals rather than any single flag.  Legitimate
   users can trigger individual signals (new device, high amount, etc.)
   without being labelled fraudulent.  Fraudulent transactions can
   occasionally look normal.  This preserves the statistical challenge that
   makes fraud detection non-trivial.

3. Class imbalance — fraud is the minority class, roughly resembling a
   real-world detection setting.  The exact rate is a tunable parameter,
   not a claim about industry statistics.

4. No target leakage — historical features (previous_fraud_count,
   merchant_fraud_rate, etc.) are derived from synthetic pre-computed entity
   histories, never from the current transaction's label.

PERFORMANCE
-----------
Bulk array operations (customer selection, amounts, timestamps, payment
methods, device/location novelty draws, velocity Poisson draws, IP draws,
UUID generation) are all pre-computed as NumPy arrays before the
row-assembly loop.  This makes the generator practical for 100 k rows on
a normal developer machine without any parallelism or external dependencies.

DATA LEAKAGE WARNING
--------------------
All historical fields (previous_*, avg_customer_amount, merchant_fraud_rate)
must represent information available BEFORE the transaction being scored.
This module approximates that by sampling each entity's attributes from
pre-seeded distributions.  A proper production implementation would compute
these from time-ordered event streams.

USAGE
-----
    from data.generator import generate_transactions

    df = generate_transactions(n=1000, seed=42)
    # df is a pandas DataFrame conforming to the Transaction schema.
    # Each row passes Transaction.model_validate(row.to_dict()).
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from data.schema import PaymentMethod, Transaction

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Generation parameters — all tunable, all in one place.
# ---------------------------------------------------------------------------

# Approximate target minority-class fraud rate.  Not a real-world claim.
_BASE_FRAUD_RATE: float = 0.04  # ~4 % fraud overall before signal boosting

# Simulation time window: transactions span the last N days.
_SIMULATION_WINDOW_DAYS: int = 90

# Entity pool sizes.
#
# Calibrated for 100 k-scale generation while preserving realistic overlap:
#
# Customers  : 1,000  → avg 100 transactions per customer at 100 k scale.
#              Enough to model behavioral history; low enough that customers
#              repeat meaningfully.
#
# Merchants  :    80  → avg 1,250 transactions per merchant at 100 k scale.
#              Covers variety in merchant risk profiles.
#
# Devices    : 1,500  → ~1.5× customers; simulates shared/secondary devices
#              without creating a purely unique device per transaction.
#
# Locations  :    50  → coarse geographic labels; enough variation to
#              create meaningful new-location signals.
#
# IPs        : 2,000  → shared infrastructure; multiple customers can share
#              an IP (corporate NAT, shared wifi, etc.).
_N_CUSTOMERS: int = 1_000
_N_MERCHANTS: int = 80
_N_DEVICES: int = 1_500
_N_LOCATIONS: int = 50
_N_IP_POOLS: int = 2_000

# Amount distribution (log-normal parameters in log-space).
_AMOUNT_LOG_MEAN: float = 4.0   # e^4 ≈ $55
_AMOUNT_LOG_STD: float = 1.2

# Payment method distribution.
_PAYMENT_METHODS: list[str] = [m.value for m in PaymentMethod]
_PAYMENT_METHOD_WEIGHTS: list[float] = [0.55, 0.25, 0.15, 0.05]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_transactions(n: int, seed: int) -> pd.DataFrame:
    """
    Generate a synthetic transaction dataset.

    Parameters
    ----------
    n : int
        Number of transactions to generate.  Must be >= 1.
    seed : int
        Random seed.  The same (n, seed) pair always produces the same dataset.

    Returns
    -------
    pd.DataFrame
        One row per transaction.  All columns match the ``Transaction`` schema.
        The DataFrame includes ``is_fraud`` (the target) alongside feature
        columns.  Callers must separate target from features before model
        training — use ``Transaction.feature_columns()`` and
        ``Transaction.target_column()``.

    Raises
    ------
    ValueError
        If ``n < 1``.
    """
    if n < 1:
        raise ValueError(f"n must be >= 1, got {n}.")

    rng = np.random.default_rng(seed)
    logger.info("Generating %d synthetic transactions (seed=%d).", n, seed)

    # -----------------------------------------------------------------------
    # Build entity pools with consistent, seeded attributes.
    # -----------------------------------------------------------------------
    customers = _build_customer_pool(rng)
    merchants = _build_merchant_pool(rng)
    devices = [f"dev_{i:04d}" for i in range(_N_DEVICES)]
    locations = [f"LOC_{i:02d}" for i in range(_N_LOCATIONS)]

    # Build IP pool — pre-generate the full address strings once.
    ip_hi = rng.integers(0, 256, size=_N_IP_POOLS)
    ip_lo = rng.integers(0, 256, size=_N_IP_POOLS)
    ip_pool = [f"10.{h}.{l}.1" for h, l in zip(ip_hi.tolist(), ip_lo.tolist())]

    # -----------------------------------------------------------------------
    # Pre-compute all per-transaction bulk arrays — vectorised for performance.
    # -----------------------------------------------------------------------

    # Customer and merchant index assignments.
    cust_ids = rng.integers(0, _N_CUSTOMERS, size=n)
    merch_ids = rng.integers(0, _N_MERCHANTS, size=n)

    # Timestamps spread across the simulation window (UTC, timezone-aware).
    # Sort so the DataFrame is time-ordered, supporting velocity features.
    start_ts = datetime.now(timezone.utc) - timedelta(days=_SIMULATION_WINDOW_DAYS)
    offset_seconds = np.sort(rng.integers(0, _SIMULATION_WINDOW_DAYS * 86400, size=n))
    start_epoch = start_ts.timestamp()
    epoch_times = start_epoch + offset_seconds.astype(float)

    # Transaction amounts from a log-normal distribution.
    amounts = np.round(
        rng.lognormal(mean=_AMOUNT_LOG_MEAN, sigma=_AMOUNT_LOG_STD, size=n), 2
    )

    # Payment methods.
    payment_methods = rng.choice(
        _PAYMENT_METHODS, size=n, p=_PAYMENT_METHOD_WEIGHTS
    )

    # Device novelty draws — one per transaction.
    new_device_draws = rng.random(size=n)
    new_device_loc_draws = rng.integers(0, _N_DEVICES, size=n)

    # Location novelty draws — one per transaction.
    new_location_draws = rng.random(size=n)
    new_location_loc_draws = rng.integers(0, _N_LOCATIONS, size=n)

    # Velocity Poisson draws — three per transaction (5min, 1h, 24h deltas).
    vel_5min = rng.poisson(
        [customers[c]["velocity_5min_base"] for c in cust_ids.tolist()]
    ).clip(0)
    vel_1h_extra = rng.poisson(
        [customers[c]["velocity_1h_base"] for c in cust_ids.tolist()]
    ).clip(0)
    vel_24h_extra = rng.poisson(
        [customers[c]["velocity_24h_base"] for c in cust_ids.tolist()]
    ).clip(0)
    failed_draws = rng.poisson(
        [customers[c]["failed_attempt_base"] for c in cust_ids.tolist()]
    ).clip(0)

    # IP draws — one uniform draw (null decision) + one index draw per transaction.
    ip_null_draws = rng.random(size=n)
    ip_idx_draws = rng.integers(0, _N_IP_POOLS, size=n)

    # UUID generation — 2 × int63 per transaction, pre-generated in bulk.
    uuid_hi = rng.integers(0, 2**63, size=n)
    uuid_lo = rng.integers(0, 2**63, size=n)

    # Fraud probability noise — one draw per transaction.
    fraud_noise = rng.normal(0, 0.005, size=n)

    # Final fraud outcome draw — one uniform draw per transaction.
    fraud_outcome_draws = rng.random(size=n)

    # -----------------------------------------------------------------------
    # Assemble rows — per-transaction logic only (no inner RNG calls).
    # -----------------------------------------------------------------------
    rows: list[dict] = []
    for i in range(n):
        cust = customers[cust_ids[i]]
        merch = merchants[merch_ids[i]]
        amount = float(amounts[i])

        # --- Device assignment -------------------------------------------
        new_device = bool(new_device_draws[i] < cust["new_device_prob"])
        device_id = (
            devices[int(new_device_loc_draws[i])]
            if new_device
            else cust["primary_device"]
        )

        # --- Location assignment ------------------------------------------
        new_location = bool(new_location_draws[i] < cust["new_location_prob"])
        location = (
            locations[int(new_location_loc_draws[i])]
            if new_location
            else cust["primary_location"]
        )

        # --- Velocity signals --------------------------------------------
        txns_last_5min = int(vel_5min[i])
        txns_last_1h = txns_last_5min + int(vel_1h_extra[i])
        txns_last_24h = txns_last_1h + int(vel_24h_extra[i])
        failed_24h = int(failed_draws[i])

        # --- Amount deviation --------------------------------------------
        avg_amount = cust["avg_amount"]
        deviation = round(abs(amount - avg_amount), 2)

        # --- IP address (occasionally missing) ---------------------------
        ip_address = (
            None if ip_null_draws[i] < 0.05
            else ip_pool[int(ip_idx_draws[i])]
        )

        # --- Fraud label -------------------------------------------------
        fraud_prob = _compute_fraud_probability(
            base_rate=_BASE_FRAUD_RATE,
            new_device=new_device,
            new_location=new_location,
            txns_last_5min=txns_last_5min,
            failed_24h=failed_24h,
            deviation=deviation,
            avg_amount=avg_amount,
            customer_fraud_history=cust["previous_fraud_count"],
            account_age_days=cust["account_age_days"],
            merchant_fraud_rate=merch["fraud_rate"],
            noise=float(fraud_noise[i]),
        )
        is_fraud = bool(fraud_outcome_draws[i] < fraud_prob)

        # --- Timestamp (from pre-sorted epoch array) ----------------------
        ts = datetime.fromtimestamp(float(epoch_times[i]), tz=timezone.utc)

        rows.append(
            {
                "transaction_id": str(
                    uuid.UUID(int=(int(uuid_hi[i]) << 64) | int(uuid_lo[i]))
                ),
                "customer_id": cust["customer_id"],
                "merchant_id": merch["merchant_id"],
                "device_id": device_id,
                "ip_address": ip_address,
                "timestamp": ts,
                "amount": amount,
                "payment_method": payment_methods[i],
                "location": location,
                "customer_account_age_days": cust["account_age_days"],
                "previous_transaction_count": cust["previous_transaction_count"],
                "previous_fraud_count": cust["previous_fraud_count"],
                "failed_attempt_count_24h": failed_24h,
                "txns_last_5min": txns_last_5min,
                "txns_last_1h": txns_last_1h,
                "txns_last_24h": txns_last_24h,
                "avg_customer_amount": avg_amount,
                "amount_deviation": deviation,
                "merchant_fraud_rate": merch["fraud_rate"],
                "new_device_flag": new_device,
                "new_location_flag": new_location,
                "is_fraud": is_fraud,
            }
        )

    df = pd.DataFrame(rows)
    logger.info(
        "Generated %d transactions — fraud rate: %.2f%%.",
        n,
        df["is_fraud"].mean() * 100,
    )
    return df


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_customer_pool(rng: np.random.Generator) -> list[dict]:
    """
    Build a fixed pool of synthetic customer entities.

    Each customer has stable attributes sampled once from seeded distributions.
    These attributes represent the customer's PRIOR history and behavioral
    profile — they do not depend on any generated transaction label.

    Customer behavioural diversity:
    - ~60% are standard customers (moderate spending, moderate velocity)
    - ~25% are high-value customers (larger avg amounts, more active)
    - ~15% are occasional/new customers (lower history, variable behaviour)
    """
    customers = []
    for i in range(_N_CUSTOMERS):
        # Stratify customers into three behavioural segments for diversity.
        segment_draw = rng.random()
        if segment_draw < 0.60:
            # Standard customer
            avg_amount = round(float(rng.lognormal(3.8, 1.0)), 2)   # ~$45 median
            prev_txn_count = int(rng.integers(20, 300))
            velocity_5min = float(rng.exponential(0.3))
            velocity_1h = float(rng.exponential(1.0))
            velocity_24h = float(rng.exponential(3.0))
        elif segment_draw < 0.85:
            # High-value customer
            avg_amount = round(float(rng.lognormal(5.0, 0.8)), 2)   # ~$150 median
            prev_txn_count = int(rng.integers(100, 500))
            velocity_5min = float(rng.exponential(0.5))
            velocity_1h = float(rng.exponential(1.5))
            velocity_24h = float(rng.exponential(5.0))
        else:
            # Occasional / new customer
            avg_amount = round(float(rng.lognormal(3.5, 1.3)), 2)   # ~$33 median
            prev_txn_count = int(rng.integers(0, 30))
            velocity_5min = float(rng.exponential(0.1))
            velocity_1h = float(rng.exponential(0.4))
            velocity_24h = float(rng.exponential(1.5))

        customers.append(
            {
                "customer_id": f"cust_{i:04d}",
                "account_age_days": int(rng.integers(1, 3650)),
                "previous_transaction_count": prev_txn_count,
                "previous_fraud_count": int(rng.integers(0, 3)),
                "avg_amount": avg_amount,
                # Per-customer risk tendencies.
                "new_device_prob": float(rng.beta(1.2, 10)),
                "new_location_prob": float(rng.beta(1.2, 10)),
                "velocity_5min_base": velocity_5min,
                "velocity_1h_base": velocity_1h,
                "velocity_24h_base": velocity_24h,
                "failed_attempt_base": float(rng.exponential(0.5)),
                # Primary device chosen from the lower half of the pool
                # (upper half reserved for "new" device draws).
                "primary_device": f"dev_{rng.integers(0, _N_DEVICES // 2):04d}",
                "primary_location": f"LOC_{rng.integers(0, _N_LOCATIONS // 2):02d}",
            }
        )
    return customers


def _build_merchant_pool(rng: np.random.Generator) -> list[dict]:
    """
    Build a fixed pool of synthetic merchant entities with pre-assigned
    historical fraud rates.

    The fraud rate represents HISTORICAL experience and does not include
    the current transaction being generated, avoiding leakage.

    Merchant behavioural diversity:
    - ~70% low-risk merchants  (Beta(1.5, 40)  → median ~3.6%)
    - ~20% medium-risk         (Beta(2.0, 20)  → median ~9%)
    - ~10% higher-risk         (Beta(3.0, 10)  → median ~23%)
    """
    merchants = []
    for i in range(_N_MERCHANTS):
        segment_draw = rng.random()
        if segment_draw < 0.70:
            fraud_rate = float(np.clip(rng.beta(1.5, 40), 0.0, 1.0))
        elif segment_draw < 0.90:
            fraud_rate = float(np.clip(rng.beta(2.0, 20), 0.0, 1.0))
        else:
            fraud_rate = float(np.clip(rng.beta(3.0, 10), 0.0, 1.0))

        merchants.append(
            {
                "merchant_id": f"merch_{i:03d}",
                "fraud_rate": round(fraud_rate, 4),
            }
        )
    return merchants


def _compute_fraud_probability(
    *,
    base_rate: float,
    new_device: bool,
    new_location: bool,
    txns_last_5min: int,
    failed_24h: int,
    deviation: float,
    avg_amount: float,
    customer_fraud_history: int,
    account_age_days: int,
    merchant_fraud_rate: float,
    noise: float,
) -> float:
    """
    Compute the probability that this transaction is fraudulent.

    Design invariants
    -----------------
    - No single weak signal independently causes a very high fraud probability.
    - Risk accumulates from COMBINATIONS of signals.
    - Legitimate users can trigger each signal in isolation.
    - The noise parameter (pre-drawn by the caller) keeps the function pure
      (no internal RNG state), enabling future unit testing of the logic alone.

    Parameters mirror those documented in Transaction schema fields.
    """
    p = base_rate

    # Accumulate risk multipliers — each signal has a moderate individual
    # effect; they compound only when co-occurring.
    multiplier = 1.0

    # Velocity spike
    if txns_last_5min >= 3:
        multiplier += 0.8
    elif txns_last_5min >= 2:
        multiplier += 0.3

    # Failed attempts
    if failed_24h >= 5:
        multiplier += 0.9
    elif failed_24h >= 3:
        multiplier += 0.4

    # Large amount deviation (relative to customer baseline)
    if avg_amount > 0:
        relative_dev = deviation / avg_amount
        if relative_dev > 5.0:
            multiplier += 0.7
        elif relative_dev > 2.0:
            multiplier += 0.3

    # Device and location novelty — each moderate alone, additive together
    if new_device:
        multiplier += 0.25
    if new_location:
        multiplier += 0.25
    if new_device and new_location:
        multiplier += 0.5   # additional co-occurrence penalty

    # Customer fraud history
    if customer_fraud_history >= 2:
        multiplier += 1.2
    elif customer_fraud_history == 1:
        multiplier += 0.5

    # New account (higher susceptibility / less behavioural history)
    if account_age_days < 7:
        multiplier += 0.6
    elif account_age_days < 30:
        multiplier += 0.2

    # Merchant risk profile
    if merchant_fraud_rate > 0.1:
        multiplier += 0.6 * merchant_fraud_rate
    elif merchant_fraud_rate > 0.05:
        multiplier += 0.3 * merchant_fraud_rate

    # Apply multiplier and add calibration noise for realism.
    p = min(p * multiplier + noise, 1.0)
    return max(p, 0.0)
