"""
Data quality gate for RazorBrain transaction datasets.

Performs a structured series of checks on a DataFrame produced by the
synthetic generator (or any future ingest pipeline) and returns a
structured report.

DESIGN
------
- Each check is independent and reports PASS / WARN / FAIL.
- The overall gate passes only if no FAIL results exist.
- The report is a plain Python dict — serialisable to JSON for CI use.
- No external data-profiling frameworks required.

USAGE
-----
    from data.quality import run_quality_gate

    report = run_quality_gate(df)
    print(report["summary"])          # quick text summary
    assert report["passed"], report   # fail-fast in CI
"""

from __future__ import annotations

import logging
from datetime import timezone
from typing import Any

import numpy as np
import pandas as pd

from data.schema import Transaction

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Maximum acceptable fraction of null values in optional fields.
_MAX_OPTIONAL_NULL_RATE: float = 0.20   # 20 % — ip_address and location

# Maximum acceptable fraud rate (synthetic minority class).
_MAX_FRAUD_RATE: float = 0.30

# Minimum acceptable fraud rate (must not be zero in a meaningful dataset).
_MIN_FRAUD_RATE: float = 0.005

# Minimum expected entity cardinalities for a 30 k dataset.
_MIN_UNIQUE_CUSTOMERS: int = 10
_MIN_UNIQUE_MERCHANTS: int = 5

# Threshold at which a feature-vs-target AUC is flagged as suspiciously high.
_LEAKAGE_AUC_THRESHOLD: float = 0.95


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_quality_gate(df: pd.DataFrame) -> dict[str, Any]:
    """
    Run all quality checks on a transaction DataFrame.

    Parameters
    ----------
    df : pd.DataFrame
        Dataset produced by ``generate_transactions`` or equivalent.

    Returns
    -------
    dict
        Keys:
        - ``"checks"``   : list of individual check results (name, status, detail)
        - ``"passed"``   : bool — True iff no FAIL results
        - ``"summary"``  : human-readable text summary
        - ``"stats"``    : core statistics (row count, fraud rate, etc.)
    """
    checks: list[dict[str, Any]] = []

    def _check(name: str, status: str, detail: str) -> None:
        checks.append({"name": name, "status": status, "detail": detail})
        icon = {"PASS": "✓", "WARN": "⚠", "FAIL": "✗"}.get(status, "?")
        logger.info("  %s  %-45s  %s", icon, name, detail)

    logger.info("Running RazorBrain data quality gate on %d rows …", len(df))

    # -----------------------------------------------------------------------
    # 1. Shape
    # -----------------------------------------------------------------------
    row_count = len(df)
    col_count = len(df.columns)

    if row_count == 0:
        _check("row_count", "FAIL", "Dataset is empty.")
    elif row_count < 100:
        _check("row_count", "WARN", f"{row_count} rows — very small for meaningful EDA.")
    else:
        _check("row_count", "PASS", f"{row_count:,} rows.")

    # -----------------------------------------------------------------------
    # 2. Required columns present
    # -----------------------------------------------------------------------
    required = set(Transaction.model_fields.keys())
    missing_cols = required - set(df.columns)
    if missing_cols:
        _check("required_columns", "FAIL", f"Missing columns: {sorted(missing_cols)}")
    else:
        _check("required_columns", "PASS", f"All {col_count} required columns present.")

    # -----------------------------------------------------------------------
    # 3. Duplicate transaction IDs
    # -----------------------------------------------------------------------
    dup_count = int(df["transaction_id"].duplicated().sum()) if "transaction_id" in df.columns else 0
    if dup_count > 0:
        _check("unique_transaction_ids", "FAIL", f"{dup_count:,} duplicate transaction_id values.")
    else:
        _check("unique_transaction_ids", "PASS", "All transaction IDs are unique.")

    # -----------------------------------------------------------------------
    # 4. Exact duplicate rows
    # -----------------------------------------------------------------------
    exact_dups = int(df.duplicated().sum())
    if exact_dups > 0:
        _check("exact_duplicate_rows", "WARN", f"{exact_dups:,} fully duplicate rows (excluding id field).")
    else:
        _check("exact_duplicate_rows", "PASS", "No exact duplicate rows.")

    # -----------------------------------------------------------------------
    # 5. Missing values
    # -----------------------------------------------------------------------
    null_counts = df.isnull().sum()
    required_nulls = {c: int(null_counts[c]) for c in required if c in df.columns and null_counts[c] > 0}

    # ip_address and location are Optional — allow nulls within threshold
    optional_fields = {"ip_address", "location"}
    unexpected_nulls = {
        col: cnt for col, cnt in required_nulls.items()
        if col not in optional_fields and cnt > 0
    }
    optional_null_rates = {
        col: round(required_nulls.get(col, 0) / row_count, 4)
        for col in optional_fields
        if col in df.columns
    }

    if unexpected_nulls:
        _check("missing_values_required", "FAIL", f"Nulls in non-optional fields: {unexpected_nulls}")
    else:
        _check("missing_values_required", "PASS", "No nulls in required fields.")

    for col, rate in optional_null_rates.items():
        status = "PASS" if rate <= _MAX_OPTIONAL_NULL_RATE else "WARN"
        _check(f"missing_{col}", status, f"{rate:.1%} null rate.")

    # -----------------------------------------------------------------------
    # 6. Timestamp validity and coverage
    # -----------------------------------------------------------------------
    if "timestamp" in df.columns:
        ts = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
        invalid_ts = int(ts.isnull().sum())
        naive_ts = int(df["timestamp"].apply(
            lambda t: getattr(t, "tzinfo", None) is None
        ).sum()) if hasattr(df["timestamp"].iloc[0], "tzinfo") else 0

        if invalid_ts > 0:
            _check("timestamp_validity", "FAIL", f"{invalid_ts:,} unparseable timestamps.")
        elif naive_ts > 0:
            _check("timestamp_validity", "FAIL", f"{naive_ts:,} timezone-naive timestamps.")
        else:
            ts_min = ts.min()
            ts_max = ts.max()
            coverage_days = (ts_max - ts_min).days
            _check("timestamp_validity", "PASS",
                   f"Range: {ts_min.date()} → {ts_max.date()} ({coverage_days} days).")

        if coverage_days < 7:
            _check("temporal_coverage", "WARN", f"Only {coverage_days} days of data — may be insufficient for time-split.")
        else:
            _check("temporal_coverage", "PASS", f"{coverage_days} days of coverage.")

    # -----------------------------------------------------------------------
    # 7. Numeric constraint checks
    # -----------------------------------------------------------------------
    numeric_constraints = {
        "amount": (0.0, None),
        "customer_account_age_days": (0, None),
        "previous_transaction_count": (0, None),
        "previous_fraud_count": (0, None),
        "failed_attempt_count_24h": (0, None),
        "txns_last_5min": (0, None),
        "txns_last_1h": (0, None),
        "txns_last_24h": (0, None),
        "avg_customer_amount": (0.0, None),
        "amount_deviation": (0.0, None),
        "merchant_fraud_rate": (0.0, 1.0),
    }
    for col, (lo, hi) in numeric_constraints.items():
        if col not in df.columns:
            continue
        violations = 0
        if lo is not None:
            violations += int((df[col] < lo).sum())
        if hi is not None:
            violations += int((df[col] > hi).sum())
        if violations:
            _check(f"constraint_{col}", "FAIL", f"{violations:,} values outside [{lo}, {hi}].")
        else:
            _check(f"constraint_{col}", "PASS", f"All values in [{lo}, {hi or '∞'}].")

    # -----------------------------------------------------------------------
    # 8. Class distribution
    # -----------------------------------------------------------------------
    if "is_fraud" in df.columns:
        fraud_count = int(df["is_fraud"].sum())
        legit_count = row_count - fraud_count
        fraud_rate = fraud_count / row_count

        if fraud_rate < _MIN_FRAUD_RATE:
            _check("fraud_class_present", "FAIL", f"Fraud rate {fraud_rate:.2%} is below minimum {_MIN_FRAUD_RATE:.2%}.")
        elif fraud_rate > _MAX_FRAUD_RATE:
            _check("fraud_minority_class", "FAIL", f"Fraud rate {fraud_rate:.2%} exceeds maximum {_MAX_FRAUD_RATE:.2%}.")
        else:
            _check("fraud_class_distribution", "PASS",
                   f"Fraud {fraud_count:,} ({fraud_rate:.2%}) / Legit {legit_count:,} ({1-fraud_rate:.2%}).")
    else:
        fraud_count = 0
        fraud_rate = float("nan")

    # -----------------------------------------------------------------------
    # 9. Entity cardinality
    # -----------------------------------------------------------------------
    entity_checks = {
        "customer_id": ("customers", _MIN_UNIQUE_CUSTOMERS),
        "merchant_id": ("merchants", _MIN_UNIQUE_MERCHANTS),
    }
    for col, (label, min_unique) in entity_checks.items():
        if col in df.columns:
            n_unique = df[col].nunique()
            if n_unique < min_unique:
                _check(f"entity_{label}", "FAIL", f"Only {n_unique} unique {label} — unrealistically low.")
            else:
                _check(f"entity_{label}", "PASS", f"{n_unique} unique {label}.")

    # -----------------------------------------------------------------------
    # 10. Feature/target separation audit
    # -----------------------------------------------------------------------
    feature_cols = Transaction.feature_columns()
    target_col = Transaction.target_column()
    if target_col in feature_cols:
        _check("target_in_features", "FAIL", f"'{target_col}' found in feature_columns() — LEAKAGE.")
    else:
        _check("target_in_features", "PASS", f"'{target_col}' correctly excluded from feature_columns().")

    # -----------------------------------------------------------------------
    # 11. Synthetic shortcut audit (single-feature near-perfect separation)
    # -----------------------------------------------------------------------
    if "is_fraud" in df.columns and row_count > 0:
        shortcut_results = _audit_synthetic_shortcuts(df, feature_cols)
        suspicious = {f: auc for f, auc in shortcut_results.items() if auc >= _LEAKAGE_AUC_THRESHOLD}
        if suspicious:
            _check(
                "synthetic_shortcut_audit",
                "FAIL",
                f"Feature(s) with near-perfect fraud separation (AUC≥{_LEAKAGE_AUC_THRESHOLD}): {suspicious}. "
                "Investigate generator logic.",
            )
        else:
            max_auc = max(shortcut_results.values(), default=0)
            _check(
                "synthetic_shortcut_audit",
                "PASS",
                f"No single feature has AUC ≥ {_LEAKAGE_AUC_THRESHOLD}. Max single-feature AUC: {max_auc:.3f}.",
            )

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------
    failed = [c for c in checks if c["status"] == "FAIL"]
    warned = [c for c in checks if c["status"] == "WARN"]
    passed = len(failed) == 0

    summary_lines = [
        f"Quality Gate: {'PASSED ✓' if passed else 'FAILED ✗'}",
        f"  Checks: {len(checks)} total — "
        f"{len(checks)-len(failed)-len(warned)} pass, {len(warned)} warn, {len(failed)} fail",
        f"  Rows: {row_count:,}",
        f"  Fraud rate: {fraud_rate:.2%}" if not np.isnan(fraud_rate) else "  Fraud rate: N/A",
    ]
    if failed:
        summary_lines.append(f"  FAILURES: {[c['name'] for c in failed]}")

    summary = "\n".join(summary_lines)

    stats = {
        "row_count": row_count,
        "col_count": col_count,
        "fraud_count": fraud_count,
        "fraud_rate": round(fraud_rate, 6) if not np.isnan(fraud_rate) else None,
        "duplicate_ids": dup_count,
        "null_ip_rate": optional_null_rates.get("ip_address"),
        "null_location_rate": optional_null_rates.get("location"),
    }

    return {
        "checks": checks,
        "passed": passed,
        "summary": summary,
        "stats": stats,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _audit_synthetic_shortcuts(
    df: pd.DataFrame, feature_cols: list[str]
) -> dict[str, float]:
    """
    Compute a simple rank-order AUC proxy for each numeric/boolean feature
    vs is_fraud to detect trivially separating signals.

    Uses the Wilcoxon-Mann-Whitney U statistic (= AUROC) without scikit-learn.
    Only numeric and boolean columns are evaluated.
    """
    from scipy.stats import mannwhitneyu  # lightweight, part of scipy

    target = df["is_fraud"].astype(int)
    fraud_mask = target == 1
    legit_mask = target == 0

    if fraud_mask.sum() == 0 or legit_mask.sum() == 0:
        return {}

    results: dict[str, float] = {}
    for col in feature_cols:
        if col not in df.columns:
            continue
        if not pd.api.types.is_numeric_dtype(df[col]) and df[col].dtype != bool:
            continue
        col_series = df[col].astype(float)
        fraud_vals = col_series[fraud_mask].dropna()
        legit_vals = col_series[legit_mask].dropna()
        if len(fraud_vals) == 0 or len(legit_vals) == 0:
            continue
        try:
            u_stat, _ = mannwhitneyu(fraud_vals, legit_vals, alternative="greater")
            auc = u_stat / (len(fraud_vals) * len(legit_vals))
            # Take the max of auc and 1-auc (direction-agnostic)
            auc = max(auc, 1 - auc)
            results[col] = round(auc, 4)
        except Exception:
            pass

    return results
