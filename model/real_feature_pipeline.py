import pandas as pd
import numpy as np
import logging
from typing import Tuple

from data.dataset_adapter import IEEEDataAdapter
from model.real_feature_contract import (
    ENGINEERED_CORE,
    RAW_SAFE,
    REJECTED_FEATURES,
)

logger = logging.getLogger(__name__)

# Columns actually present in train_transaction.csv (used for selection)
_TX_COLS = (
    {"TransactionAmt", "ProductCD", "card1", "card2", "card3", "card4", "card5", "card6",
     "addr1", "addr2", "dist1", "dist2",
     "P_emaildomain", "R_emaildomain",
     "D1", "D2", "D3", "D4", "D5", "D10", "D15",
     "M1", "M2", "M3", "M4", "M5", "M6", "M7", "M8", "M9",
     "C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8", "C9", "C10", "C11", "C12", "C13", "C14"}
    | {f"V{i}" for i in range(95, 138)}
    | {f"V{i}" for i in range(279, 322)}
    | {f"V{i}" for i in range(53, 95)}
)

_ID_COLS = {
    "id_01", "id_02", "id_03", "id_04", "id_05", "id_06", "id_09", "id_10", "id_11",
    "id_12", "id_13", "id_14", "id_15", "id_16", "id_17", "id_18", "id_19", "id_20",
    "id_28", "id_29", "id_30", "id_31", "id_32", "id_33", "id_34", "id_35", "id_36",
    "id_37", "id_38", "DeviceType", "DeviceInfo",
}


class RealFeaturePipeline:
    def __init__(self, data_dir: str = "data/RAW"):
        self.adapter = IEEEDataAdapter(data_dir=data_dir)

    def load_and_join(self, nrows: int = None) -> pd.DataFrame:
        df = self.adapter.load_and_join(nrows=nrows)
        df = df.sort_values("TransactionDT").reset_index(drop=True)
        return df

    def build_real_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Build the full feature table containing:
          - ENGINEERED_CORE features (22 leakage-safe engineered features)
          - RAW_SAFE columns passthrough
          - Missingness indicators for informative absent columns

        The current transaction is NEVER included in its own rolling aggregate.
        """
        logger.info("Building real features incrementally...")
        features = pd.DataFrame()

        # ── Identifiers kept for splitting / merging ──────────────────────
        features["TransactionID"] = df["TransactionID"]
        features["TransactionDT"] = df["TransactionDT"]
        features["isFraud"] = df["isFraud"]  # label — excluded from X during training

        # ═══════════════════════════════════════════════════════════════════
        # ENGINEERED CORE
        # ═══════════════════════════════════════════════════════════════════

        # Amount
        features["log_amount"] = np.log1p(df["TransactionAmt"])

        # Temporal proxies
        features["time_of_day_proxy"] = (df["TransactionDT"] // 3600) % 24
        features["day_of_week_proxy"] = (df["TransactionDT"] // 86400) % 7

        # Missingness indicators (computed before fillna/imputation)
        features["email_domain_missing"] = df.get("P_emaildomain", pd.Series(index=df.index, dtype=str)).isna().astype(np.int8)
        features["billing_region_missing"] = df.get("addr1", pd.Series(index=df.index, dtype=float)).isna().astype(np.int8)
        features["card_country_missing"] = df.get("card5", pd.Series(index=df.index, dtype=float)).isna().astype(np.int8)
        features["recipient_email_missing"] = df.get("R_emaildomain", pd.Series(index=df.index, dtype=str)).isna().astype(np.int8)
        features["dist1_missing"] = df.get("dist1", pd.Series(index=df.index, dtype=float)).isna().astype(np.int8)

        # Identity presence (join produced NaN for id_01 when no identity row)
        features["identity_present"] = df.get("id_01", pd.Series(index=df.index, dtype=float)).notna().astype(np.int8)

        # M-series match count
        m_cols = [c for c in ["M1", "M2", "M3", "M4", "M5", "M6", "M7", "M8", "M9"] if c in df.columns]
        features["m_match_count"] = df[m_cols].notna().sum(axis=1).astype(np.int8)

        # Email suffix
        email = df.get("P_emaildomain", pd.Series(index=df.index, dtype=str))
        features["email_suffix"] = email.apply(
            lambda x: x.split(".")[-1] if isinstance(x, str) and "." in x else "UNKNOWN"
        )

        # Network × product interaction
        features["network_product_combo"] = (
            df["card4"].astype(str) + "_" + df["ProductCD"].astype(str)
        )

        # ── Strictly-prior rolling aggregates ─────────────────────────────
        logger.info("Computing strictly-prior aggregations by card1 entity proxy...")
        hist = df[["TransactionID", "card1", "TransactionDT", "TransactionAmt"]].copy()
        hist.sort_values(["card1", "TransactionDT"], inplace=True)

        hist["time_since_last_txn"] = (
            hist.groupby("card1")["TransactionDT"].diff().fillna(86400 * 365)
        )

        base_date = pd.to_datetime("2017-12-01")
        hist["_dt"] = base_date + pd.to_timedelta(hist["TransactionDT"], unit="s")
        hist.set_index("_dt", inplace=True)

        for window, suffix in [
            (pd.Timedelta(hours=1), "1h"),
            (pd.Timedelta(days=1), "24h"),
            (pd.Timedelta(days=7), "7d"),
        ]:
            cnt = (
                hist.groupby("card1")["TransactionAmt"]
                .rolling(window)
                .count()
                .reset_index(level=0, drop=True)
            )
            hist[f"_cnt_{suffix}"] = cnt
            hist[f"entity_txn_count_{suffix}"] = (
                hist.groupby("card1")[f"_cnt_{suffix}"].shift(1).fillna(0)
            )

        avg_24h = (
            hist.groupby("card1")["TransactionAmt"]
            .rolling(pd.Timedelta(days=1))
            .mean()
            .reset_index(level=0, drop=True)
        )
        sum_24h = (
            hist.groupby("card1")["TransactionAmt"]
            .rolling(pd.Timedelta(days=1))
            .sum()
            .reset_index(level=0, drop=True)
        )
        hist["_avg_24h"] = avg_24h
        hist["_sum_24h"] = sum_24h
        hist["entity_avg_amount_24h"] = hist.groupby("card1")["_avg_24h"].shift(1).fillna(0.0)
        hist["entity_amount_sum_24h"] = hist.groupby("card1")["_sum_24h"].shift(1).fillna(0.0)

        hist.reset_index(drop=True, inplace=True)

        agg_cols = [
            "TransactionID", "time_since_last_txn",
            "entity_txn_count_1h", "entity_txn_count_24h", "entity_txn_count_7d",
            "entity_avg_amount_24h", "entity_amount_sum_24h",
        ]
        features = features.merge(hist[agg_cols], on="TransactionID", how="left")

        # Derived from aggregates (safe — uses only already-computed prior values)
        features["entity_is_new"] = (features["time_since_last_txn"] > 86400 * 180).astype(np.int8)
        features["entity_velocity_24h_7d"] = (
            features["entity_txn_count_24h"] / (features["entity_txn_count_7d"] + 1)
        )
        features["amount_deviation"] = df["TransactionAmt"].values - features["entity_avg_amount_24h"]
        features["amount_relative_24h"] = df["TransactionAmt"].values / (features["entity_avg_amount_24h"] + 1)

        # ═══════════════════════════════════════════════════════════════════
        # RAW_SAFE passthrough
        # ═══════════════════════════════════════════════════════════════════
        raw_safe_cols = [c for c in RAW_SAFE.keys() if c in df.columns]
        for col in raw_safe_cols:
            if col not in features.columns:
                features[col] = df[col]

        # ── Final sort ────────────────────────────────────────────────────
        features.sort_values("TransactionDT", inplace=True)
        features.reset_index(drop=True, inplace=True)

        return features

    def split_temporally(
        self, df: pd.DataFrame, train_frac: float = 0.7, val_frac: float = 0.15
    ) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        assert df["TransactionDT"].is_monotonic_increasing, (
            "Data must be chronologically sorted before splitting."
        )
        n = len(df)
        t = int(n * train_frac)
        v = int(n * (train_frac + val_frac))
        return df.iloc[:t].copy(), df.iloc[t:v].copy(), df.iloc[v:].copy()

    def validate_feature_contract(self, df: pd.DataFrame) -> bool:
        """Verify ENGINEERED_CORE features present and no rejected features leaked in."""
        for feat in ENGINEERED_CORE:
            if feat not in df.columns:
                logger.error(f"Missing ENGINEERED_CORE feature: {feat}")
                return False

        for feat in REJECTED_FEATURES:
            # isFraud is the label — it stays in the feature table for splitting but
            # must be excluded from X in the training script, not here.
            # TransactionID and TransactionDT are kept for join/ordering only.
            if feat in ("isFraud", "TransactionID", "TransactionDT"):
                continue
            if feat in df.columns:
                logger.error(f"Rejected feature found in table: {feat}")
                return False

        v_cols = [c for c in df.columns if c.startswith("V") and c[1:].isdigit()]
        # V138–V216 (84–86% null), V217–V278 (84% null), V322–V339 (86% null) must not appear
        bad_v = [c for c in v_cols if int(c[1:]) in range(138, 279) or int(c[1:]) in range(322, 340)]
        if bad_v:
            logger.error(f"Rejected high-null V-series found: {bad_v[:5]}...")
            return False

        return True
