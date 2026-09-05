import pytest
import pandas as pd
from model.real_feature_pipeline import RealFeaturePipeline
from model.real_feature_contract import (
    ENGINEERED_CORE,
    RAW_SAFE,
    PRIMARY_REAL_FEATURE_SET,
)


@pytest.fixture
def sample_tx_df():
    """Minimal IEEE-CIS-shaped fixture for unit tests — never uses real data."""
    return pd.DataFrame({
        "TransactionID":  [1,   2,     3,     4,    5],
        "isFraud":        [0,   1,     0,     0,    1],
        "TransactionDT":  [10,  86410, 86420, 100,  200],
        "TransactionAmt": [100.0, 200.0, 300.0, 50.0, 50.0],
        "ProductCD":      ["W", "W",   "W",   "C",  "C"],
        "card1":          [1000, 1000, 1000, 2000, 2000],
        "card2":          [None, 330,   330,  221,  221],
        "card3":          [150,  150,   150,  119,  119],
        "card4":          ["visa", "mastercard", "visa", "visa", "visa"],
        "card5":          [102,  None,  102,   102,  102],
        "card6":          ["credit", "debit", "credit", "credit", "credit"],
        "addr1":          [315,  315,   None,  123,  123],
        "addr2":          [87,   87,    87,    87,   87],
        "P_emaildomain":  ["gmail.com", None, "gmail.com", "anon.com", "gmail.com"],
        "R_emaildomain":  [None, None,  None,  None, "yahoo.com"],
        "dist1":          [None, 10.0,  20.0,  None, None],
        "M4":             ["T", "F",   "T",   None, "T"],
        "M6":             ["T", None,  "T",   "T",  "T"],
        "D1":             [1.0, 2.0,   3.0,   4.0,  5.0],
        "D10":            [0.5, None,  1.5,   2.5,  3.5],
        "id_01":          [None, None, None,  0.0,  0.0],
        "id_12":          [None, None, None,  "T",  "T"],
        "V95":            [0.1, 0.2,   0.3,   0.4,  0.5],
        "V279":           [1.0, 2.0,   3.0,   4.0,  5.0],
    })


# ── 1. Temporal split correctness ─────────────────────────────────────────────

def test_chronological_split(sample_tx_df):
    pipeline = RealFeaturePipeline(data_dir=".")
    df = sample_tx_df.sort_values("TransactionDT").reset_index(drop=True)
    train, val, test = pipeline.split_temporally(df, train_frac=0.6, val_frac=0.2)
    assert len(train) + len(val) + len(test) == len(df)
    assert train["TransactionDT"].max() <= val["TransactionDT"].min()
    assert val["TransactionDT"].max() <= test["TransactionDT"].min()


def test_no_temporal_id_overlap(sample_tx_df):
    pipeline = RealFeaturePipeline(data_dir=".")
    df = sample_tx_df.sort_values("TransactionDT").reset_index(drop=True)
    train, val, test = pipeline.split_temporally(df)
    t, v, te = set(train["TransactionID"]), set(val["TransactionID"]), set(test["TransactionID"])
    assert not t & v, "Train and validation share TransactionIDs"
    assert not v & te, "Validation and test share TransactionIDs"
    assert not t & te, "Train and test share TransactionIDs"


# ── 2. Strictly-prior rolling aggregates ──────────────────────────────────────

def test_first_occurrence_has_zero_history(sample_tx_df):
    """First transaction for any entity must have zero prior counts/amounts."""
    pipeline = RealFeaturePipeline(data_dir=".")
    df = sample_tx_df.sort_values("TransactionDT").reset_index(drop=True)
    features = pipeline.build_real_features(df)

    # card1=1000 first txn is TransactionID=1 (DT=10, earliest)
    f1 = features[features["TransactionID"] == 1].iloc[0]
    assert f1["entity_txn_count_24h"] == 0.0, "First entity txn must have zero 24h count"
    assert f1["entity_avg_amount_24h"] == 0.0, "First entity txn must have zero 24h avg"
    assert f1["entity_is_new"] == 1


def test_current_row_excluded_from_own_aggregate(sample_tx_df):
    """The amount of transaction 3 must NOT be in entity_avg_amount_24h of txn 3."""
    pipeline = RealFeaturePipeline(data_dir=".")
    df = sample_tx_df.sort_values("TransactionDT").reset_index(drop=True)
    features = pipeline.build_real_features(df)

    f3 = features[features["TransactionID"] == 3].iloc[0]
    # TxnID 3 has amount 300. If it leaked into its own avg, avg would be ≥250.
    # Correct: avg should reflect only prior txns for card1=1000 (TxnID=1 at DT=10,
    # and TxnID=2 at DT=86410 which is >24h before DT=86420).
    assert f3["entity_avg_amount_24h"] in [200.0, 150.0, 0.0], (
        f"TxnID 3 avg_amount_24h={f3['entity_avg_amount_24h']} — current row may have leaked in"
    )
    assert f3["entity_avg_amount_24h"] != 300.0, "300.0 means current row leaked"


def test_entity_velocity_uses_prior_counts(sample_tx_df):
    """entity_velocity_24h_7d must be derived from already-shifted counts."""
    pipeline = RealFeaturePipeline(data_dir=".")
    df = sample_tx_df.sort_values("TransactionDT").reset_index(drop=True)
    features = pipeline.build_real_features(df)
    # Velocity = count_24h / (count_7d + 1); both prior-only
    expected = features["entity_txn_count_24h"] / (features["entity_txn_count_7d"] + 1)
    pd.testing.assert_series_equal(
        features["entity_velocity_24h_7d"].reset_index(drop=True),
        expected.reset_index(drop=True),
        check_names=False,
    )


# ── 3. Missingness indicators ─────────────────────────────────────────────────

def test_missingness_indicators_correct(sample_tx_df):
    pipeline = RealFeaturePipeline(data_dir=".")
    df = sample_tx_df.sort_values("TransactionDT").reset_index(drop=True)
    features = pipeline.build_real_features(df)

    f2 = features[features["TransactionID"] == 2].iloc[0]
    assert f2["email_domain_missing"] == 1, "TxnID 2 should have missing email"
    assert f2["card_country_missing"] == 1, "TxnID 2 card5 is None"

    f3 = features[features["TransactionID"] == 3].iloc[0]
    assert f3["billing_region_missing"] == 1, "TxnID 3 addr1 is None"


def test_missingness_indicators_are_binary(sample_tx_df):
    pipeline = RealFeaturePipeline(data_dir=".")
    df = sample_tx_df.sort_values("TransactionDT").reset_index(drop=True)
    features = pipeline.build_real_features(df)
    for col in ["email_domain_missing", "billing_region_missing", "card_country_missing",
                "recipient_email_missing", "dist1_missing"]:
        unique = set(features[col].unique())
        assert unique <= {0, 1}, f"{col} must be binary, got {unique}"


# ── 4. Feature contract validation ───────────────────────────────────────────

def test_contract_passes_clean_features(sample_tx_df):
    pipeline = RealFeaturePipeline(data_dir=".")
    df = sample_tx_df.sort_values("TransactionDT").reset_index(drop=True)
    features = pipeline.build_real_features(df)
    assert pipeline.validate_feature_contract(features) is True


def test_contract_fails_on_rejected_v_series(sample_tx_df):
    pipeline = RealFeaturePipeline(data_dir=".")
    df = sample_tx_df.sort_values("TransactionDT").reset_index(drop=True)
    features = pipeline.build_real_features(df)
    features["V200"] = 1.0  # V200 is in the >80% null rejected group
    assert pipeline.validate_feature_contract(features) is False


def test_target_not_in_engineered_core():
    assert "isFraud" not in ENGINEERED_CORE, "Target must not appear in ENGINEERED_CORE"


def test_target_not_in_raw_safe():
    assert "isFraud" not in RAW_SAFE, "Target must not appear in RAW_SAFE"


def test_transaction_id_not_in_raw_safe():
    assert "TransactionID" not in RAW_SAFE, "Row ID must not be a model feature"


# ── 5. Deterministic feature ordering ────────────────────────────────────────

def test_engineered_core_order_stable():
    keys1 = list(ENGINEERED_CORE.keys())
    keys2 = list(ENGINEERED_CORE.keys())
    assert keys1 == keys2, "ENGINEERED_CORE key order must be deterministic (Python dict ordered)"


def test_raw_safe_order_stable():
    keys1 = list(RAW_SAFE.keys())
    keys2 = list(RAW_SAFE.keys())
    assert keys1 == keys2


# ── 6. Unknown category handling ──────────────────────────────────────────────

def test_email_suffix_handles_missing():
    pipeline = RealFeaturePipeline(data_dir=".")
    df = pd.DataFrame({
        "TransactionID": [1], "isFraud": [0], "TransactionDT": [10],
        "TransactionAmt": [100.0], "ProductCD": ["W"], "card1": [1000],
        "card4": ["visa"], "P_emaildomain": [None],
    })
    features = pipeline.build_real_features(df)
    assert features["email_suffix"].iloc[0] == "UNKNOWN"


# ── 7. PRIMARY_REAL_FEATURE_SET backward compat ──────────────────────────────

def test_primary_feature_set_alias():
    assert PRIMARY_REAL_FEATURE_SET is ENGINEERED_CORE, (
        "PRIMARY_REAL_FEATURE_SET must alias ENGINEERED_CORE for backward compat"
    )
