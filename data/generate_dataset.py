"""
Dataset generation script for RazorBrain development.

Generates and saves the synthetic transaction dataset for local
development, EDA, and model training.

Usage:
    python -m data.generate_dataset [--n N] [--seed SEED] [--output PATH]

Defaults:
    --n      100000    (100 k transactions, primary development scale)
    --seed   42        (reproducible)
    --output data/generated/transactions.parquet

Generated files are excluded from source control (see .gitignore).
Regenerate anytime with the same seed to reproduce the exact dataset.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

from data.generator import generate_transactions

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

_DEFAULT_N: int = 100_000
_DEFAULT_SEED: int = 42
_DEFAULT_OUTPUT: Path = Path("data/generated/transactions.parquet")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate the RazorBrain synthetic transaction dataset."
    )
    parser.add_argument(
        "--n",
        type=int,
        default=_DEFAULT_N,
        help=f"Number of transactions to generate (default: {_DEFAULT_N:,}).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=_DEFAULT_SEED,
        help=f"Random seed for reproducibility (default: {_DEFAULT_SEED}).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=_DEFAULT_OUTPUT,
        help=f"Output file path (default: {_DEFAULT_OUTPUT}). "
        "Supports .parquet and .csv extensions.",
    )
    return parser.parse_args(argv)


def generate_and_save(n: int, seed: int, output: Path) -> pd.DataFrame:
    """
    Generate a synthetic transaction dataset and persist it to disk.

    Parameters
    ----------
    n : int
        Number of transactions.
    seed : int
        Random seed.
    output : Path
        Destination file path.  Parent directories are created automatically.

    Returns
    -------
    pd.DataFrame
        The generated dataset (same object that was saved).
    """
    logger.info("Generating %d transactions with seed=%d …", n, seed)
    df = generate_transactions(n=n, seed=seed)

    output.parent.mkdir(parents=True, exist_ok=True)

    ext = output.suffix.lower()
    if ext == ".parquet":
        df.to_parquet(output, index=False)
    elif ext == ".csv":
        df.to_csv(output, index=False)
    else:
        raise ValueError(
            f"Unsupported output format '{ext}'. Use .parquet or .csv."
        )

    fraud_count = int(df["is_fraud"].sum())
    fraud_pct = df["is_fraud"].mean() * 100
    logger.info("Saved %d rows → %s", len(df), output)
    logger.info(
        "Fraud: %d (%.2f%%)  Legitimate: %d (%.2f%%)",
        fraud_count,
        fraud_pct,
        len(df) - fraud_count,
        100 - fraud_pct,
    )
    return df


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    generate_and_save(n=args.n, seed=args.seed, output=args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
