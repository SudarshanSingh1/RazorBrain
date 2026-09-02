# Synthetic Dataset Notes

## Purpose

RazorBrain uses synthetic transaction data for development, testing, and model training.  Synthetic data is used because:

- Real payment transaction data is private and regulated.
- Synthetic data allows full control over fraud signal relationships.
- Labels (is_fraud) are ground-truth by construction — no label noise.
- The dataset can be freely shared and reproduced.

This data is NOT real payment data and does NOT represent any real customers, merchants, or fraud activity.

---

## Generation Parameters

| Parameter | Value | Notes |
|-----------|-------|-------|
| Default size | **100,000 transactions** | Configurable via `--n` |
| Random seed | 42 | Reproducible; configurable via `--seed` |
| Simulation window | 90 days | UTC timestamps; rows sorted chronologically |
| Base fraud rate | ~4% | Before signal boosting; synthetic only |
| Customer pool | **1,000 entities** | ~100 transactions per customer at 100k scale |
| Merchant pool | **80 entities** | Stratified into low/medium/high-risk tiers |
| Device pool | **1,500 entities** | ~1.5× customers; simulates shared/secondary devices |
| Location pool | **50 entities** | Coarse geographic labels |
| IP pool | **2,000 entries** | Shared infrastructure; 5% chance of None |

Regenerate the exact dataset with:
```bash
python -m data.generate_dataset --n 100000 --seed 42
```

---

## Customer Behavioural Segments

Customers are drawn from three behavioural segments to ensure population diversity:

| Segment | Fraction | Avg Amount | Activity |
|---------|----------|------------|----------|
| Standard | 60% | ~\$45 median | Moderate velocity |
| High-value | 25% | ~\$150 median | Higher velocity |
| Occasional / new | 15% | ~\$33 median | Low velocity |

Each customer has a persistent profile (avg amount, velocity baselines, device/location probabilities) that does not change within a generation run.  This enables meaningful behavioral feature engineering.

---

## Merchant Behavioural Tiers

| Tier | Fraction | Historical Fraud Rate |
|------|----------|----------------------|
| Low-risk | 70% | Beta(1.5, 40) → median ~3.6% |
| Medium-risk | 20% | Beta(2.0, 20) → median ~9% |
| Higher-risk | 10% | Beta(3.0, 10) → median ~23% |

Fraud rates are assigned before any transaction labels are generated — no leakage.

---

## Fraud Signal Relationships

Fraud probability increases with **combinations** of risk signals.  No single signal alone is deterministic.

| Signal | Effect |
|--------|--------|
| Transaction velocity (txns_last_5min ≥ 3) | Moderate increase |
| Failed attempts (≥ 5 in 24h) | Moderate–high increase |
| Large relative amount deviation (>5×) | Moderate increase |
| New device **and** new location together | Elevated (co-occurrence penalty) |
| Previous fraud history (≥ 2 events) | Strong increase |
| Very new account (< 7 days) | Moderate increase |
| High merchant fraud rate (> 10%) | Proportional increase |

Legitimate transactions **can** trigger any individual signal.  
Fraudulent transactions **can** appear normal on all signals.

This preserves the non-trivial nature of the fraud-detection problem.

---

## Temporal Assumptions

- All timestamps are UTC and timezone-aware.
- Transactions are **pre-sorted chronologically** within the 90-day window.
- The dataset supports time-based train/validation/test splitting.
- At 100k rows across 90 days, average density is ~1,111 transactions/day — sufficient for velocity feature engineering.

---

## Leakage Protections & Feature Engineering

The raw synthetic dataset generator approximates historical attributes statically for speed. However, RazorBrain's **canonical feature pipeline** (`model.feature_engineering`) supersedes these static attributes with **strict, time-aware rolling aggregates**.

The feature pipeline ensures:
- **Zero Target Leakage:** `is_fraud` and raw identifiers (`transaction_id`, etc.) are definitively excluded from the final numerical matrix ($X$).
- **Zero Temporal Leakage:** Historical aggregates (like `previous_fraud_count`, `merchant_fraud_rate`, `avg_customer_amount`) are computed dynamically via Pandas `.shift(1)` operations on chronologically sorted grouping. The current transaction's labels and values are mathematically guaranteed to be excluded from its own historical profile.
- **Velocity Tracking:** Counts (e.g., `txns_last_1h`) are calculated via rolling time-windows strictly up to, but not including, the current transaction.
- **Cold-Start Handling:** New entities (merchants, customers, devices) are robustly handled. Missing historical states are zero-imputed and supplemented with binary flags (e.g., `is_new_customer=1`).

---

## Train / Validation / Test Splitting

To prevent future information from influencing the model, dataset splitting in RazorBrain is strictly **chronological** (`model.dataset_split`).

The default proportions are:
- **Train:** 70% (Earliest transactions)
- **Validation:** 15% (Subsequent transactions)
- **Test:** 15% (Latest transactions)

Random shuffling is deliberately **disabled** during the split phase to mimic real-world deployment (training on the past to predict the future).

---

## Class Imbalance

Fraud is the minority class.  The observed fraud rate (~7–8% at 100k scale) is a synthetic parameter.  It is **not a claim** about real-world fraud prevalence.

Do not balance this dataset before evaluation.  The class imbalance is an important part of the problem.

---

## Performance Characteristics (seed=42, n=100,000)

| Metric | Value |
|--------|-------|
| Generation time | ~11s on a standard developer laptop |
| Peak memory | ~163 MB |
| Output (parquet) | ~6 MB |

---

## Known Simplifications

1. Entity attributes are static — real customers evolve over time.
2. Velocity features are Poisson-sampled, not event-sourced.
3. IP addresses are randomly assigned — no geographic clustering.
4. No seasonal patterns are modeled.
5. Merchant fraud rates are fixed — real rates drift over time.
6. No concept drift or adversarial adaptation is modeled.

These simplifications are acceptable for a development and demonstration dataset.  They should be replaced with realistic time-ordered feature engineering in a production system.

---

## Usage

```bash
# Generate primary development dataset (100k rows, seed 42)
python -m data.generate_dataset

# Custom size and seed
python -m data.generate_dataset --n 50000 --seed 123 --output data/generated/custom.parquet

# Small sample for local exploration
python -m data.generate_dataset --n 5000 --seed 42 --output data/generated/sample.parquet

# CSV output
python -m data.generate_dataset --n 5000 --seed 42 --output data/generated/sample.csv
```

Generated files are stored in `data/generated/` and excluded from source control.
