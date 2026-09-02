"""
Exploratory data analysis for RazorBrain synthetic transaction datasets.

Produces concise, engineering-focused summaries useful for:
- understanding signal relationships
- validating generator realism
- detecting leakage or degenerate distributions
- informing feature engineering decisions

Does NOT produce decorative plots for presentation.
All analysis uses pandas and numpy — no plotting library required for
the core analysis; optional matplotlib/seaborn figures can be generated
if available.

USAGE
-----
    from data.eda import run_eda

    report = run_eda(df)
    # report is a dict of analysis sections, each a DataFrame or dict.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from data.schema import Transaction

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_eda(df: pd.DataFrame) -> dict[str, Any]:
    """
    Run the full EDA suite on a transaction DataFrame.

    Returns
    -------
    dict with keys:
        - "class_distribution"        : fraud vs legit counts / rates
        - "amount_summary"            : amount stats by class
        - "velocity_summary"          : velocity stats by class
        - "fraud_by_new_device"       : fraud rate for new vs known devices
        - "fraud_by_new_location"     : fraud rate for new vs known locations
        - "fraud_by_failed_attempts"  : fraud rate binned by failed attempts
        - "fraud_by_account_age"      : fraud rate binned by account age
        - "fraud_by_fraud_history"    : fraud rate by previous_fraud_count
        - "temporal_distribution"     : transaction count per day
        - "entity_cardinality"        : unique counts per entity column
        - "missing_value_summary"     : null counts per column
        - "leakage_audit"             : per-feature notes on leakage risk
        - "merchant_risk_distribution": distribution of merchant_fraud_rate
    """
    logger.info("Running EDA on %d rows …", len(df))
    report: dict[str, Any] = {}

    report["class_distribution"] = _class_distribution(df)
    report["amount_summary"] = _amount_summary(df)
    report["velocity_summary"] = _velocity_summary(df)
    report["fraud_by_new_device"] = _fraud_rate_by_flag(df, "new_device_flag")
    report["fraud_by_new_location"] = _fraud_rate_by_flag(df, "new_location_flag")
    report["fraud_by_failed_attempts"] = _fraud_by_failed_attempts(df)
    report["fraud_by_account_age"] = _fraud_by_account_age(df)
    report["fraud_by_fraud_history"] = _fraud_by_fraud_history(df)
    report["temporal_distribution"] = _temporal_distribution(df)
    report["entity_cardinality"] = _entity_cardinality(df)
    report["missing_value_summary"] = _missing_value_summary(df)
    report["leakage_audit"] = _leakage_audit(df)
    report["merchant_risk_distribution"] = _merchant_risk_distribution(df)

    logger.info("EDA complete.")
    return report


def print_eda_report(report: dict[str, Any]) -> None:
    """Pretty-print the EDA report to stdout."""
    _divider = "─" * 65

    def _section(title: str, content: Any) -> None:
        print(f"\n{_divider}")
        print(f"  {title}")
        print(_divider)
        if isinstance(content, pd.DataFrame):
            print(content.to_string(index=True))
        elif isinstance(content, dict):
            for k, v in content.items():
                print(f"  {k:<40} {v}")
        else:
            print(content)

    for key, value in report.items():
        _section(key.replace("_", " ").title(), value)
    print(f"\n{_divider}")


# ---------------------------------------------------------------------------
# Individual analysis functions
# ---------------------------------------------------------------------------


def _class_distribution(df: pd.DataFrame) -> dict[str, Any]:
    total = len(df)
    fraud = int(df["is_fraud"].sum())
    legit = total - fraud
    return {
        "total_transactions": total,
        "fraud_count": fraud,
        "legitimate_count": legit,
        "fraud_rate": f"{fraud/total:.4%}",
        "legitimate_rate": f"{legit/total:.4%}",
        "note": "Synthetic data — fraud rate does not represent real-world statistics.",
    }


def _amount_summary(df: pd.DataFrame) -> pd.DataFrame:
    return (
        df.groupby("is_fraud")["amount"]
        .agg(["count", "mean", "median", "std", "min", "max"])
        .rename(index={False: "legitimate", True: "fraud"})
        .round(2)
    )


def _velocity_summary(df: pd.DataFrame) -> pd.DataFrame:
    cols = ["txns_last_5min", "txns_last_1h", "txns_last_24h", "failed_attempt_count_24h"]
    available = [c for c in cols if c in df.columns]
    return (
        df.groupby("is_fraud")[available]
        .mean()
        .rename(index={False: "legitimate", True: "fraud"})
        .round(3)
    )


def _fraud_rate_by_flag(df: pd.DataFrame, flag_col: str) -> pd.DataFrame:
    if flag_col not in df.columns:
        return pd.DataFrame()
    return (
        df.groupby(flag_col)["is_fraud"]
        .agg(["sum", "count", "mean"])
        .rename(columns={"sum": "fraud_count", "count": "total", "mean": "fraud_rate"})
        .assign(fraud_rate=lambda x: x["fraud_rate"].round(4))
    )


def _fraud_by_failed_attempts(df: pd.DataFrame) -> pd.DataFrame:
    if "failed_attempt_count_24h" not in df.columns:
        return pd.DataFrame()
    bins = [-1, 0, 1, 2, 4, 100]
    labels = ["0", "1", "2", "3–4", "5+"]
    df = df.copy()
    df["_fail_bin"] = pd.cut(df["failed_attempt_count_24h"], bins=bins, labels=labels)
    return (
        df.groupby("_fail_bin", observed=True)["is_fraud"]
        .agg(["sum", "count", "mean"])
        .rename(columns={"sum": "fraud_count", "count": "total", "mean": "fraud_rate"})
        .assign(fraud_rate=lambda x: x["fraud_rate"].round(4))
    )


def _fraud_by_account_age(df: pd.DataFrame) -> pd.DataFrame:
    if "customer_account_age_days" not in df.columns:
        return pd.DataFrame()
    bins = [-1, 7, 30, 90, 365, 10000]
    labels = ["<1w", "1w–1m", "1m–3m", "3m–1y", ">1y"]
    df = df.copy()
    df["_age_bin"] = pd.cut(df["customer_account_age_days"], bins=bins, labels=labels)
    return (
        df.groupby("_age_bin", observed=True)["is_fraud"]
        .agg(["sum", "count", "mean"])
        .rename(columns={"sum": "fraud_count", "count": "total", "mean": "fraud_rate"})
        .assign(fraud_rate=lambda x: x["fraud_rate"].round(4))
    )


def _fraud_by_fraud_history(df: pd.DataFrame) -> pd.DataFrame:
    if "previous_fraud_count" not in df.columns:
        return pd.DataFrame()
    return (
        df.groupby("previous_fraud_count")["is_fraud"]
        .agg(["sum", "count", "mean"])
        .rename(columns={"sum": "fraud_count", "count": "total", "mean": "fraud_rate"})
        .assign(fraud_rate=lambda x: x["fraud_rate"].round(4))
    )


def _temporal_distribution(df: pd.DataFrame) -> pd.DataFrame:
    if "timestamp" not in df.columns:
        return pd.DataFrame()
    ts = pd.to_datetime(df["timestamp"], utc=True)
    by_day = ts.dt.date.value_counts().sort_index().rename("transaction_count")
    by_day.index.name = "date"
    summary = pd.DataFrame(by_day)
    summary["cumulative"] = summary["transaction_count"].cumsum()
    return summary


def _entity_cardinality(df: pd.DataFrame) -> dict[str, int]:
    entity_cols = ["customer_id", "merchant_id", "device_id", "ip_address", "location"]
    return {
        col: int(df[col].nunique(dropna=True))
        for col in entity_cols
        if col in df.columns
    }


def _missing_value_summary(df: pd.DataFrame) -> pd.DataFrame:
    null_counts = df.isnull().sum()
    null_rates = df.isnull().mean().round(4)
    result = pd.DataFrame({"null_count": null_counts, "null_rate": null_rates})
    return result[result["null_count"] > 0] if result["null_count"].sum() > 0 else result.head(0)


def _leakage_audit(df: pd.DataFrame) -> dict[str, str]:
    """
    Structured commentary on leakage risks for each historical feature.

    This is a qualitative audit, not an automated detection.
    The notes document the generator's approach and known simplifications.
    """
    return {
        "is_fraud": (
            "TARGET — correctly excluded from feature_columns(). "
            "Never passes to model input."
        ),
        "previous_fraud_count": (
            "HISTORICAL — derived from customer entity pool, seeded before any "
            "transaction label is assigned.  Does NOT include current transaction. "
            "Simplification: fixed per customer; a time-ordered stream would recompute this."
        ),
        "merchant_fraud_rate": (
            "HISTORICAL — assigned from merchant entity pool before transactions are generated. "
            "Does NOT include the current transaction. "
            "Simplification: static rate; a production system uses time-windowed pre-computation."
        ),
        "avg_customer_amount": (
            "HISTORICAL — sampled from customer baseline distribution. "
            "Does NOT include current transaction amount. "
            "Simplification: fixed; production uses rolling average over prior transactions."
        ),
        "amount_deviation": (
            "TRANSACTION-TIME — computed as abs(amount - avg_customer_amount). "
            "avg_customer_amount excludes current transaction, so no leakage."
        ),
        "txns_last_5min / txns_last_1h / txns_last_24h": (
            "HISTORICAL — sampled from customer velocity distributions. "
            "Does NOT include the current transaction. "
            "Simplification: Poisson-sampled baseline, not event-sourced."
        ),
        "failed_attempt_count_24h": (
            "HISTORICAL — sampled from customer failed-attempt distribution. "
            "Does NOT include the current transaction."
        ),
        "new_device_flag / new_location_flag": (
            "TRANSACTION-TIME — evaluated at scoring time against customer primary profile. "
            "No leakage concern."
        ),
        "customer_account_age_days": (
            "HISTORICAL — age at transaction time, derived from customer pool. "
            "No leakage concern."
        ),
        "SUMMARY": (
            "No direct target leakage identified. "
            "All historical fields use pre-seeded entity attributes, not derived from "
            "is_fraud of the current transaction. "
            "Known simplification: static entity attributes approximate time-ordered "
            "computations — acceptable for synthetic development data."
        ),
    }


def _merchant_risk_distribution(df: pd.DataFrame) -> pd.DataFrame:
    if "merchant_fraud_rate" not in df.columns:
        return pd.DataFrame()
    bins = [0, 0.01, 0.03, 0.05, 0.10, 1.01]
    labels = ["<1%", "1–3%", "3–5%", "5–10%", ">10%"]
    df = df.copy()
    df["_mfr_bin"] = pd.cut(df["merchant_fraud_rate"], bins=bins, labels=labels, right=False)
    return (
        df.groupby("_mfr_bin", observed=True)["is_fraud"]
        .agg(["sum", "count", "mean"])
        .rename(columns={"sum": "fraud_count", "count": "total", "mean": "fraud_rate"})
        .assign(fraud_rate=lambda x: x["fraud_rate"].round(4))
    )
