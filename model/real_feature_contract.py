"""
IEEE-CIS Full Feature Contract
================================
Authoritative machine-readable definitions for all three feature pools:
  POOL A: ENGINEERED_CORE   (~20–25 engineered features)
  POOL B: RAW_SAFE          (broad set of safe raw IEEE-CIS columns)
  POOL C: RAW_RESEARCH      (useful but requiring further serving investigation)

Plus explicit REJECTED / LEAKAGE pools.

IMPORTANT:
- No feature derived from future rows.
- No feature that includes the current row in its own aggregate.
- No target (isFraud) in any pool except LEAKAGE.
- V-series: only groups with 0% missingness included in RAW_SAFE;
  all others remain LEAKAGE_RISK or UNKNOWN.
- C-series: all 0% missing. Included as RAW_CANDIDATE given they are
  numerical counts readable at transaction time, but flagged
  LEAKAGE_RISK because their exact rolling-window semantics are opaque
  (they could incorporate future rows in their construction).
  They are placed in RAW_RESEARCH, NOT RAW_SAFE.
"""

from enum import Enum


class FeatureStatus(str, Enum):
    PRODUCTION_CANDIDATE = "PRODUCTION_CANDIDATE"
    TRANSFERABLE_CONCEPT = "TRANSFERABLE_CONCEPT"
    OFFLINE_RESEARCH = "OFFLINE_RESEARCH"
    BENCHMARK_ONLY = "BENCHMARK_ONLY"
    UNAVAILABLE = "UNAVAILABLE"
    LEAKAGE_RISK = "LEAKAGE_RISK"
    POST_EVENT = "POST_EVENT"
    UNKNOWN = "UNKNOWN"
    REJECTED = "REJECTED"


class ServingAvailability(str, Enum):
    AVAILABLE = "AVAILABLE"
    AVAILABLE_WITH_MERCHANT_TELEMETRY = "AVAILABLE_WITH_MERCHANT_TELEMETRY"
    UNAVAILABLE = "UNAVAILABLE"
    OFFLINE_ONLY = "OFFLINE_ONLY"


class FeatureType(str, Enum):
    RAW = "RAW"
    ENGINEERED = "ENGINEERED"


# ============================================================
# POOL A: ENGINEERED_CORE  (~20–25 features)
# ============================================================
# Every feature here is derived deterministically from source
# columns using strictly prior information.
ENGINEERED_CORE = {
    "log_amount": {
        "source": "TransactionAmt",
        "type": FeatureType.ENGINEERED,
        "semantic_meaning": "Log-scaled transaction amount; compresses long-tailed distribution",
        "temporal_requirement": "Current transaction value — no prior rows needed",
        "leakage_status": "NONE",
        "status": FeatureStatus.PRODUCTION_CANDIDATE,
        "serving_availability": ServingAvailability.AVAILABLE,
    },
    "time_of_day_proxy": {
        "source": "TransactionDT",
        "type": FeatureType.ENGINEERED,
        "semantic_meaning": "Pseudo hour-of-day (0–23) derived from elapsed-seconds delta",
        "temporal_requirement": "Current transaction value — no prior rows needed",
        "leakage_status": "NONE",
        "status": FeatureStatus.PRODUCTION_CANDIDATE,
        "serving_availability": ServingAvailability.AVAILABLE,
    },
    "day_of_week_proxy": {
        "source": "TransactionDT",
        "type": FeatureType.ENGINEERED,
        "semantic_meaning": "Pseudo day-of-week (0–6) — captures weekend fraud spikes",
        "temporal_requirement": "Current transaction value — no prior rows needed",
        "leakage_status": "NONE",
        "status": FeatureStatus.PRODUCTION_CANDIDATE,
        "serving_availability": ServingAvailability.AVAILABLE,
    },
    "time_since_last_txn": {
        "source": "card1, TransactionDT",
        "type": FeatureType.ENGINEERED,
        "semantic_meaning": "Seconds since entity's most recent prior transaction",
        "temporal_requirement": "Strictly prior rows only; shift(1) applied",
        "leakage_status": "NONE",
        "status": FeatureStatus.PRODUCTION_CANDIDATE,
        "serving_availability": ServingAvailability.AVAILABLE,
    },
    "entity_is_new": {
        "source": "time_since_last_txn",
        "type": FeatureType.ENGINEERED,
        "semantic_meaning": "1 if entity has no prior history (first-seen proxy)",
        "temporal_requirement": "Derived from time_since_last_txn",
        "leakage_status": "NONE",
        "status": FeatureStatus.PRODUCTION_CANDIDATE,
        "serving_availability": ServingAvailability.AVAILABLE,
    },
    "entity_txn_count_1h": {
        "source": "card1, TransactionDT",
        "type": FeatureType.ENGINEERED,
        "semantic_meaning": "Count of entity transactions in the prior 1 hour",
        "temporal_requirement": "Strictly prior rows; rolling window + shift(1)",
        "leakage_status": "NONE",
        "status": FeatureStatus.PRODUCTION_CANDIDATE,
        "serving_availability": ServingAvailability.AVAILABLE,
    },
    "entity_txn_count_24h": {
        "source": "card1, TransactionDT",
        "type": FeatureType.ENGINEERED,
        "semantic_meaning": "Count of entity transactions in the prior 24 hours",
        "temporal_requirement": "Strictly prior rows; rolling window + shift(1)",
        "leakage_status": "NONE",
        "status": FeatureStatus.PRODUCTION_CANDIDATE,
        "serving_availability": ServingAvailability.AVAILABLE,
    },
    "entity_txn_count_7d": {
        "source": "card1, TransactionDT",
        "type": FeatureType.ENGINEERED,
        "semantic_meaning": "Count of entity transactions in the prior 7 days",
        "temporal_requirement": "Strictly prior rows; rolling window + shift(1)",
        "leakage_status": "NONE",
        "status": FeatureStatus.PRODUCTION_CANDIDATE,
        "serving_availability": ServingAvailability.AVAILABLE,
    },
    "entity_avg_amount_24h": {
        "source": "card1, TransactionAmt, TransactionDT",
        "type": FeatureType.ENGINEERED,
        "semantic_meaning": "Rolling mean of entity transaction amounts over prior 24 hours",
        "temporal_requirement": "Strictly prior rows; rolling window + shift(1)",
        "leakage_status": "NONE",
        "status": FeatureStatus.PRODUCTION_CANDIDATE,
        "serving_availability": ServingAvailability.AVAILABLE,
    },
    "entity_amount_sum_24h": {
        "source": "card1, TransactionAmt, TransactionDT",
        "type": FeatureType.ENGINEERED,
        "semantic_meaning": "Rolling sum of entity transaction amounts over prior 24 hours",
        "temporal_requirement": "Strictly prior rows; rolling window + shift(1)",
        "leakage_status": "NONE",
        "status": FeatureStatus.PRODUCTION_CANDIDATE,
        "serving_availability": ServingAvailability.AVAILABLE,
    },
    "entity_velocity_24h_7d": {
        "source": "entity_txn_count_24h, entity_txn_count_7d",
        "type": FeatureType.ENGINEERED,
        "semantic_meaning": "Ratio of 24h count to 7d count — detects sudden frequency spikes",
        "temporal_requirement": "Derived from strictly-prior rolling features",
        "leakage_status": "NONE",
        "status": FeatureStatus.PRODUCTION_CANDIDATE,
        "serving_availability": ServingAvailability.AVAILABLE,
    },
    "amount_deviation": {
        "source": "TransactionAmt, entity_avg_amount_24h",
        "type": FeatureType.ENGINEERED,
        "semantic_meaning": "Current amount minus entity's 24h rolling mean",
        "temporal_requirement": "Derived from strictly-prior rolling features",
        "leakage_status": "NONE",
        "status": FeatureStatus.PRODUCTION_CANDIDATE,
        "serving_availability": ServingAvailability.AVAILABLE,
    },
    "amount_relative_24h": {
        "source": "TransactionAmt, entity_avg_amount_24h",
        "type": FeatureType.ENGINEERED,
        "semantic_meaning": "Current amount as a ratio of entity's 24h rolling mean",
        "temporal_requirement": "Derived from strictly-prior rolling features",
        "leakage_status": "NONE",
        "status": FeatureStatus.PRODUCTION_CANDIDATE,
        "serving_availability": ServingAvailability.AVAILABLE,
    },
    "email_suffix": {
        "source": "P_emaildomain",
        "type": FeatureType.ENGINEERED,
        "semantic_meaning": "Top-level domain extracted from purchaser email",
        "temporal_requirement": "Current transaction value",
        "leakage_status": "NONE",
        "status": FeatureStatus.PRODUCTION_CANDIDATE,
        "serving_availability": ServingAvailability.AVAILABLE,
    },
    "network_product_combo": {
        "source": "card4, ProductCD",
        "type": FeatureType.ENGINEERED,
        "semantic_meaning": "Interaction of card network × product type; captures risky segment combos",
        "temporal_requirement": "Current transaction value",
        "leakage_status": "NONE",
        "status": FeatureStatus.PRODUCTION_CANDIDATE,
        "serving_availability": ServingAvailability.AVAILABLE,
    },
    "email_domain_missing": {
        "source": "P_emaildomain",
        "type": FeatureType.ENGINEERED,
        "semantic_meaning": "Binary indicator: email domain absent (associated with anonymous orders)",
        "temporal_requirement": "Current transaction value",
        "leakage_status": "NONE",
        "status": FeatureStatus.PRODUCTION_CANDIDATE,
        "serving_availability": ServingAvailability.AVAILABLE,
    },
    "billing_region_missing": {
        "source": "addr1",
        "type": FeatureType.ENGINEERED,
        "semantic_meaning": "Binary indicator: billing region absent",
        "temporal_requirement": "Current transaction value",
        "leakage_status": "NONE",
        "status": FeatureStatus.PRODUCTION_CANDIDATE,
        "serving_availability": ServingAvailability.AVAILABLE,
    },
    "card_country_missing": {
        "source": "card5",
        "type": FeatureType.ENGINEERED,
        "semantic_meaning": "Binary indicator: card country absent",
        "temporal_requirement": "Current transaction value",
        "leakage_status": "NONE",
        "status": FeatureStatus.PRODUCTION_CANDIDATE,
        "serving_availability": ServingAvailability.AVAILABLE,
    },
    "recipient_email_missing": {
        "source": "R_emaildomain",
        "type": FeatureType.ENGINEERED,
        "semantic_meaning": "Binary indicator: recipient email domain absent (82% missing = informative)",
        "temporal_requirement": "Current transaction value",
        "leakage_status": "NONE",
        "status": FeatureStatus.PRODUCTION_CANDIDATE,
        "serving_availability": ServingAvailability.AVAILABLE,
    },
    "dist1_missing": {
        "source": "dist1",
        "type": FeatureType.ENGINEERED,
        "semantic_meaning": "Binary indicator: distance proxy 1 absent (66% missing = informative)",
        "temporal_requirement": "Current transaction value",
        "leakage_status": "NONE",
        "status": FeatureStatus.PRODUCTION_CANDIDATE,
        "serving_availability": ServingAvailability.AVAILABLE,
    },
    "identity_present": {
        "source": "id_01 (presence in identity join)",
        "type": FeatureType.ENGINEERED,
        "semantic_meaning": "Binary: transaction has identity data (only 24% of txns join to identity)",
        "temporal_requirement": "Available at join time",
        "leakage_status": "NONE",
        "status": FeatureStatus.PRODUCTION_CANDIDATE,
        "serving_availability": ServingAvailability.AVAILABLE_WITH_MERCHANT_TELEMETRY,
    },
    "m_match_count": {
        "source": "M1,M2,M3,M4,M5,M6,M7,M8,M9",
        "type": FeatureType.ENGINEERED,
        "semantic_meaning": "Count of non-null M-series match flags — proxy for identity verification richness",
        "temporal_requirement": "Current transaction value",
        "leakage_status": "NONE — counts only presence of flags, not their values",
        "status": FeatureStatus.PRODUCTION_CANDIDATE,
        "serving_availability": ServingAvailability.AVAILABLE,
    },
}

# ============================================================
# POOL B: RAW_SAFE
# ============================================================
# Original IEEE-CIS columns that pass temporal / semantic / leakage screening.
# V-series with 0% missing (V95–V137, V279–V321) are included as RAW_SAFE
# with UNKNOWN semantic confidence. They are numerical features with no missing
# values, observed at transaction time. Their inclusion is defensible as
# black-box numerical inputs that the model can learn from.
# C-series (all 0% missing) moved to RAW_RESEARCH due to opaque rolling semantics.

RAW_SAFE = {
    # --- Transaction metadata ---
    "TransactionAmt":   {"source": "TransactionAmt",   "semantic": "Payment amount", "leakage": "NONE", "null_pct": 0},
    "ProductCD":        {"source": "ProductCD",         "semantic": "Product type proxy", "leakage": "NONE", "null_pct": 0},
    # --- Card attributes ---
    "card1":            {"source": "card1",             "semantic": "IEEE-CIS entity proxy (anonymous)", "leakage": "NONE", "null_pct": 0},
    "card2":            {"source": "card2",             "semantic": "IEEE-CIS card attribute proxy", "leakage": "NONE", "null_pct": 1.2},
    "card3":            {"source": "card3",             "semantic": "Card attribute proxy", "leakage": "NONE", "null_pct": 0},
    "card4":            {"source": "card4",             "semantic": "Card network (Visa/MC/etc)", "leakage": "NONE", "null_pct": 0},
    "card5":            {"source": "card5",             "semantic": "Card country proxy", "leakage": "NONE", "null_pct": 0.4},
    "card6":            {"source": "card6",             "semantic": "Card type (credit/debit)", "leakage": "NONE", "null_pct": 0},
    # --- Address ---
    "addr1":            {"source": "addr1",             "semantic": "Billing region proxy", "leakage": "NONE", "null_pct": 8.4},
    "addr2":            {"source": "addr2",             "semantic": "Billing country proxy", "leakage": "NONE", "null_pct": 8.4},
    # --- Email ---
    "P_emaildomain":    {"source": "P_emaildomain",     "semantic": "Purchaser email domain", "leakage": "NONE", "null_pct": 20.9},
    "R_emaildomain":    {"source": "R_emaildomain",     "semantic": "Recipient email domain", "leakage": "NONE", "null_pct": 82.5},
    # --- Distance ---
    "dist1":            {"source": "dist1",             "semantic": "Distance proxy 1 (anonymous)", "leakage": "NONE", "null_pct": 65.8},
    # --- M-series match flags (categorical T/F, safe at transaction time) ---
    "M4":               {"source": "M4",                "semantic": "Anonymous match flag", "leakage": "NONE", "null_pct": 52.5},
    "M6":               {"source": "M6",                "semantic": "Anonymous match flag (lowest missing 29%)", "leakage": "NONE", "null_pct": 29.4},
    # --- D-series (lower missing, numerical timedelta proxies) ---
    "D1":               {"source": "D1",                "semantic": "Anonymous timedelta proxy 1 (0% null)", "leakage": "UNKNOWN", "null_pct": 0},
    "D10":              {"source": "D10",               "semantic": "Anonymous timedelta proxy 10 (16% null)", "leakage": "UNKNOWN", "null_pct": 15.9},
    "D15":              {"source": "D15",               "semantic": "Anonymous timedelta proxy 15 (42% null)", "leakage": "UNKNOWN", "null_pct": 42.4},
    # --- Identity features (low missing, in identity table) ---
    "id_01":            {"source": "id_01",             "semantic": "Anonymous identity attribute (0% null)", "leakage": "NONE", "null_pct": 0},
    "id_02":            {"source": "id_02",             "semantic": "Anonymous identity proxy (2% null)", "leakage": "NONE", "null_pct": 2.3},
    "id_05":            {"source": "id_05",             "semantic": "Anonymous identity attribute (5% null)", "leakage": "NONE", "null_pct": 5.1},
    "id_06":            {"source": "id_06",             "semantic": "Anonymous identity attribute (5% null)", "leakage": "NONE", "null_pct": 5.1},
    "id_11":            {"source": "id_11",             "semantic": "Anonymous identity attribute (2% null)", "leakage": "NONE", "null_pct": 2.3},
    "id_12":            {"source": "id_12",             "semantic": "Binary identity string flag", "leakage": "NONE", "null_pct": 0},
    "id_13":            {"source": "id_13",             "semantic": "Anonymous identity count (22% null)", "leakage": "NONE", "null_pct": 21.8},
    "id_14":            {"source": "id_14",             "semantic": "Anonymous identity count (27% null)", "leakage": "NONE", "null_pct": 27.4},
    "id_15":            {"source": "id_15",             "semantic": "Identity string flag (3 values)", "leakage": "NONE", "null_pct": 2.3},
    "id_16":            {"source": "id_16",             "semantic": "Binary identity string flag", "leakage": "NONE", "null_pct": 7.8},
    "id_17":            {"source": "id_17",             "semantic": "Anonymous identity proxy (3% null)", "leakage": "NONE", "null_pct": 3.2},
    "id_19":            {"source": "id_19",             "semantic": "Anonymous identity proxy (3% null)", "leakage": "NONE", "null_pct": 3.2},
    "id_20":            {"source": "id_20",             "semantic": "Anonymous identity proxy (3% null)", "leakage": "NONE", "null_pct": 3.3},
    "id_28":            {"source": "id_28",             "semantic": "Binary identity string flag (2% null)", "leakage": "NONE", "null_pct": 2.3},
    "id_29":            {"source": "id_29",             "semantic": "Binary identity string flag (2% null)", "leakage": "NONE", "null_pct": 2.3},
    "id_31":            {"source": "id_31",             "semantic": "Browser/OS string proxy", "leakage": "NONE", "null_pct": 2.5},
    "id_35":            {"source": "id_35",             "semantic": "Binary device flag (2% null)", "leakage": "NONE", "null_pct": 2.3},
    "id_36":            {"source": "id_36",             "semantic": "Binary device flag (2% null)", "leakage": "NONE", "null_pct": 2.3},
    "id_37":            {"source": "id_37",             "semantic": "Binary device flag (2% null)", "leakage": "NONE", "null_pct": 2.3},
    "id_38":            {"source": "id_38",             "semantic": "Binary device flag (2% null)", "leakage": "NONE", "null_pct": 2.3},
    "DeviceType":       {"source": "DeviceType",        "semantic": "Device category (mobile/desktop) — 2% null", "leakage": "NONE", "null_pct": 2.3},
    # --- V-series: 0% missing groups ---
    # Group 1: V95–V137 (43 cols, 0% null) — include as numerical black-box inputs
    **{f"V{i}": {"source": f"V{i}", "semantic": "Anonymous Vesta feature (0% null group)", "leakage": "UNKNOWN", "null_pct": 0}
       for i in range(95, 138)},
    # Group 2: V279–V321 (43 cols, 0% null)
    **{f"V{i}": {"source": f"V{i}", "semantic": "Anonymous Vesta feature (0% null group)", "leakage": "UNKNOWN", "null_pct": 0}
       for i in range(279, 322)},
}

# ============================================================
# POOL C: RAW_RESEARCH
# ============================================================
# Columns that have potential value but require further investigation
# for leakage safety, serving availability, or semantic clarity.

RAW_RESEARCH = {
    # C-series: all 0% missing, numerical. Potentially useful but
    # opaque rolling-window semantics — could aggregate future transactions.
    **{f"C{i}": {
        "source": f"C{i}",
        "semantic": "Anonymous count feature (0% null) — leakage semantics unclear",
        "leakage": "SUSPECTED — may be rolling aggregates including future rows",
        "null_pct": 0,
    } for i in range(1, 15)},
    # D-series: moderate missing (42–68%), anonymous timedeltas
    "D2":  {"source": "D2",  "semantic": "Anonymous timedelta (47% null)", "leakage": "UNKNOWN", "null_pct": 47.2},
    "D3":  {"source": "D3",  "semantic": "Anonymous timedelta (44% null)", "leakage": "UNKNOWN", "null_pct": 44.3},
    "D4":  {"source": "D4",  "semantic": "Anonymous timedelta (56% null)", "leakage": "UNKNOWN", "null_pct": 55.6},
    "D5":  {"source": "D5",  "semantic": "Anonymous timedelta (68% null)", "leakage": "UNKNOWN", "null_pct": 68.4},
    # M-series with higher missingness but potentially still useful
    "M1":  {"source": "M1",  "semantic": "Anonymous match flag (60% null)", "leakage": "NONE", "null_pct": 60.4},
    "M2":  {"source": "M2",  "semantic": "Anonymous match flag (60% null)", "leakage": "NONE", "null_pct": 60.4},
    "M3":  {"source": "M3",  "semantic": "Anonymous match flag (60% null)", "leakage": "NONE", "null_pct": 60.4},
    "M5":  {"source": "M5",  "semantic": "Anonymous match flag (61% null)", "leakage": "NONE", "null_pct": 61.2},
    "M7":  {"source": "M7",  "semantic": "Anonymous match flag (79% null)", "leakage": "NONE", "null_pct": 79.2},
    "M8":  {"source": "M8",  "semantic": "Anonymous match flag (79% null)", "leakage": "NONE", "null_pct": 79.2},
    "M9":  {"source": "M9",  "semantic": "Anonymous match flag (79% null)", "leakage": "NONE", "null_pct": 79.2},
    # Distance proxy 2
    "dist2": {"source": "dist2", "semantic": "Distance proxy 2 (95% null — high sparsity)", "leakage": "UNKNOWN", "null_pct": 95.2},
    # Identity: moderate missing
    "id_03": {"source": "id_03", "semantic": "Anonymous identity proxy (54% null)", "leakage": "NONE", "null_pct": 54.3},
    "id_04": {"source": "id_04", "semantic": "Anonymous identity proxy (54% null)", "leakage": "NONE", "null_pct": 54.3},
    "id_09": {"source": "id_09", "semantic": "Anonymous identity proxy (47% null)", "leakage": "NONE", "null_pct": 46.6},
    "id_10": {"source": "id_10", "semantic": "Anonymous identity proxy (47% null)", "leakage": "NONE", "null_pct": 46.6},
    "id_18": {"source": "id_18", "semantic": "Anonymous identity proxy (70% null)", "leakage": "NONE", "null_pct": 69.9},
    "id_30": {"source": "id_30", "semantic": "OS string proxy (29% null)", "leakage": "NONE", "null_pct": 28.6},
    "id_32": {"source": "id_32", "semantic": "Screen resolution proxy (29% null)", "leakage": "NONE", "null_pct": 28.6},
    "id_33": {"source": "id_33", "semantic": "Screen resolution string (34% null)", "leakage": "NONE", "null_pct": 33.9},
    "id_34": {"source": "id_34", "semantic": "Connection type proxy (29% null)", "leakage": "NONE", "null_pct": 28.8},
    "DeviceInfo": {"source": "DeviceInfo", "semantic": "Device model string (12% null — high cardinality)", "leakage": "NONE", "null_pct": 12.2},
    # V-series: 49–86% missing groups — high sparsity, research only
    **{f"V{i}": {"source": f"V{i}", "semantic": "Anonymous Vesta feature (49% null group)", "leakage": "UNKNOWN", "null_pct": 49.3}
       for i in range(53, 95)},
}

# ============================================================
# LEAKAGE / REJECTED
# ============================================================
REJECTED_FEATURES = {
    "isFraud": {
        "reason": "Target label — pure data leakage if used as feature",
        "status": FeatureStatus.POST_EVENT,
    },
    "TransactionID": {
        "reason": "Row identifier — must never enter feature matrix",
        "status": FeatureStatus.REJECTED,
    },
    "TransactionDT": {
        "reason": "Raw time delta — used only for ordering/derived features, not directly",
        "status": FeatureStatus.REJECTED,
    },
    # V-series: groups with >80% missing — not useful
    "V_series_80pct_null_groups": {
        "reason": "V138–V216, V217–V278, V322–V339 groups — 84–86% missing. "
                  "Near-empty: model would see zeros for >84% of examples. Excluded.",
        "status": FeatureStatus.REJECTED,
    },
    # D-series: extremely sparse
    "D6_D7_D8_D9_D12_D13_D14": {
        "reason": "D6(94%), D7(97%), D8(87%), D9(87%), D12(95%), D13(96%), D14(95%) null. "
                  "Excluded due to near-complete sparsity.",
        "status": FeatureStatus.REJECTED,
    },
    # id-series: 96%+ null
    "id_07_08_21_22_23_24_25_26_27": {
        "reason": "96%+ null — effectively absent for the vast majority of transactions.",
        "status": FeatureStatus.REJECTED,
    },
}

# ============================================================
# OFFLINE RESEARCH FEATURES
# ============================================================
OFFLINE_RESEARCH_FEATURE_SET = {
    "entity_fraud_rate_30d_delay": {
        "source": "isFraud + card1 + TransactionDT",
        "semantic_meaning": "Historical fraud rate with explicit 30-day chargeback delay",
        "status": FeatureStatus.OFFLINE_RESEARCH,
        "serving_availability": ServingAvailability.OFFLINE_ONLY,
    },
}

# ============================================================
# ALIASES for backward compatibility with training script
# ============================================================
# The training script reads PRIMARY_REAL_FEATURE_SET for feature ordering.
# We expose ENGINEERED_CORE as the authoritative pool.
PRIMARY_REAL_FEATURE_SET = ENGINEERED_CORE
