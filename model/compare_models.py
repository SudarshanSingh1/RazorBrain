"""
Three-way controlled feature-ablation comparison.

MODEL A: 13-feature baseline (original contract)
MODEL B: 22-feature ENGINEERED_CORE
MODEL C: 22-feature ENGINEERED_CORE + 125 RAW_SAFE

Identical XGBoost config / random seed / splits across all three.
HELD-OUT TEST IS NOT EVALUATED.
"""
import logging
import joblib
import os
import time
from datetime import datetime

import pandas as pd

from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.metrics import (
    roc_auc_score, average_precision_score,
    precision_score, recall_score, f1_score, confusion_matrix,
)
from xgboost import XGBClassifier

from model.real_feature_pipeline import RealFeaturePipeline
from model.real_feature_contract import ENGINEERED_CORE, RAW_SAFE

logging.basicConfig(level=logging.INFO, format="%(name)s:%(levelname)s:%(message)s")
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# Original 13-feature baseline contract (preserved exactly)
# ─────────────────────────────────────────────────────────────
MODEL_A_FEATURES = [
    "amount", "log_amount", "product_type", "card_network", "card_type",
    "card_issuer_proxy", "email_domain", "time_of_day_proxy",
    "entity_txn_count_1h", "entity_txn_count_24h", "entity_avg_amount_24h",
    "amount_deviation", "time_since_last_txn",
]

# ─────────────────────────────────────────────────────────────
# XGBoost config (identical for all three models)
# ─────────────────────────────────────────────────────────────
XGBOOST_PARAMS = dict(
    n_estimators=100,
    max_depth=6,
    learning_rate=0.1,
    eval_metric="logloss",
    random_state=42,
    use_label_encoder=False,
)

ARTIFACT_DIR = "data"
TARGET_COL = "isFraud"
THRESHOLD = 0.5


def _metrics(y_true, y_prob, threshold=THRESHOLD):
    y_pred = (y_prob >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred).ravel()
    return dict(
        roc_auc=round(roc_auc_score(y_true, y_prob), 4),
        pr_auc=round(average_precision_score(y_true, y_prob), 4),
        precision=round(precision_score(y_true, y_pred, zero_division=0), 4),
        recall=round(recall_score(y_true, y_pred, zero_division=0), 4),
        f1=round(f1_score(y_true, y_pred, zero_division=0), 4),
        fpr=round(fp / (fp + tn + 1e-9), 4),
        fnr=round(fn / (fn + tp + 1e-9), 4),
        tp=int(tp), fp=int(fp), fn=int(fn), tn=int(tn),
    )


def _build_preprocessor(X_train: pd.DataFrame, cat_cols: list, num_cols: list):
    """Build ColumnTransformer fitted on TRAIN only."""
    cat_pipeline = Pipeline([
        ("imputer", SimpleImputer(strategy="constant", fill_value="UNKNOWN")),
        ("ohe", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
    ])
    num_pipeline = Pipeline([
        ("imputer", SimpleImputer(strategy="constant", fill_value=0.0)),
    ])
    actual_cat = [c for c in cat_cols if c in X_train.columns]
    actual_num = [c for c in num_cols if c in X_train.columns]
    transformer = ColumnTransformer([
        ("cat", cat_pipeline, actual_cat),
        ("num", num_pipeline, actual_num),
    ], remainder="drop")
    # Cast categoricals to str before fit
    X_fit = X_train.copy()
    for c in actual_cat:
        X_fit[c] = X_fit[c].astype(str).replace("nan", "UNKNOWN")
    transformer.fit(X_fit)
    return transformer, actual_cat, actual_num


def _get_cat_cols(feature_names: list, df: pd.DataFrame) -> list:
    """Identify categorical columns using dtype check (object/StringDtype) or known name."""
    KNOWN_CAT = {
        # Raw IEEE-CIS names
        "ProductCD", "card4", "card6", "P_emaildomain", "R_emaildomain",
        "id_12", "id_15", "id_16", "id_23", "id_27", "id_28", "id_29",
        "id_35", "id_36", "id_37", "id_38", "DeviceType", "DeviceInfo",
        "M1", "M2", "M3", "M4", "M5", "M6", "M7", "M8", "M9",
        # Engineered categorical
        "email_suffix", "network_product_combo",
        # Model A renamed aliases
        "product_type", "card_network", "card_type", "card_issuer_proxy",
        "email_domain",
    }
    cat = []
    for c in feature_names:
        if c not in df.columns:
            continue
        if pd.api.types.is_string_dtype(df[c]) or df[c].dtype == object or c in KNOWN_CAT:
            cat.append(c)
    return cat


def _train_model(name: str, X_train: pd.DataFrame, y_train: pd.Series,
                 X_val: pd.DataFrame, y_val: pd.Series,
                 cat_cols: list, artifact_path: str):
    """Train one model, evaluate on train+val, save artifact."""
    logger.info(f"{'='*60}")
    logger.info(f"Training {name} | features={len(X_train.columns)}")

    # Auto-detect cat columns from actual data types to be safe
    auto_cat = [c for c in X_train.columns
                if not pd.api.types.is_numeric_dtype(X_train[c])]
    # Also include any explicitly-named cat cols that may be numeric-looking
    auto_cat = list(dict.fromkeys(auto_cat + [c for c in cat_cols if c in X_train.columns]))
    auto_num = [c for c in X_train.columns if c not in auto_cat]
    logger.info(f"  auto_cat={len(auto_cat)} auto_num={len(auto_num)}")

    t0 = time.time()
    preprocessor, actual_cat, actual_num = _build_preprocessor(X_train, auto_cat, auto_num)
    preprocess_time = time.time() - t0
    logger.info(f"Preprocessing fitted in {preprocess_time:.1f}s  cat={len(actual_cat)} num={len(actual_num)}")

    # Cast categoricals to str before transform (already done in _build_preprocessor.fit,
    # must repeat for transform calls)
    def _cast_cats(df, cats):
        df = df.copy()
        for c in cats:
            if c in df.columns:
                df[c] = df[c].astype(str).replace("nan", "UNKNOWN")
        return df

    X_tr_enc = preprocessor.transform(_cast_cats(X_train, actual_cat))
    X_vl_enc = preprocessor.transform(_cast_cats(X_val,   actual_cat))
    transformed_dim = X_tr_enc.shape[1]
    logger.info(f"Transformed dimension: {transformed_dim}")

    # Scale class imbalance from training data ONLY
    neg = int((y_train == 0).sum())
    pos = int((y_train == 1).sum())
    spw = neg / pos
    logger.info(f"scale_pos_weight={spw:.2f}  (neg={neg}, pos={pos})")

    model = XGBClassifier(scale_pos_weight=spw, **XGBOOST_PARAMS)

    t1 = time.time()
    model.fit(X_tr_enc, y_train)
    train_time = time.time() - t1
    logger.info(f"Training done in {train_time:.1f}s")

    # Metrics
    prob_train = model.predict_proba(X_tr_enc)[:, 1]
    prob_val   = model.predict_proba(X_vl_enc)[:, 1]

    train_metrics = _metrics(y_train, prob_train)
    val_metrics   = _metrics(y_val,   prob_val)

    logger.info(f"TRAIN ROC-AUC={train_metrics['roc_auc']}  PR-AUC={train_metrics['pr_auc']}")
    logger.info(f"VAL   ROC-AUC={val_metrics['roc_auc']}  PR-AUC={val_metrics['pr_auc']}")

    # Feature importance (raw XGBoost)
    importance = dict(zip(
        preprocessor.get_feature_names_out(),
        model.feature_importances_,
    ))
    top10 = sorted(importance.items(), key=lambda x: -x[1])[:10]
    logger.info("Top-10 feature importances:")
    for feat, imp in top10:
        logger.info(f"  {feat}: {imp:.6f}")

    # Save artifact
    artifact = dict(
        model_id=name,
        model_artifact=model,
        preprocessor=preprocessor,
        cat_cols=cat_cols,
        feature_order=list(X_train.columns),
        transformed_dim=transformed_dim,
        train_metrics=train_metrics,
        val_metrics=val_metrics,
        feature_importances=importance,
        xgboost_params=XGBOOST_PARAMS,
        scale_pos_weight=spw,
        trained_at=datetime.utcnow().isoformat(),
        train_rows=len(X_train),
        val_rows=len(X_val),
        held_out_evaluated=False,
    )
    joblib.dump(artifact, artifact_path)
    logger.info(f"Artifact saved → {artifact_path}")

    return train_metrics, val_metrics, importance, transformed_dim, train_time


def _get_cat_cols(feature_names: list, df: pd.DataFrame) -> list:
    """Identify which of the feature columns are categorical (object dtype)."""
    return [c for c in feature_names if c in df.columns and df[c].dtype == object]


def main():
    logger.info("Loading and joining IEEE-CIS dataset...")
    pipe = RealFeaturePipeline()
    raw = pipe.load_and_join()
    logger.info(f"Raw rows: {len(raw)}")

    logger.info("Building full feature table (ENGINEERED_CORE + RAW_SAFE)...")
    t0 = time.time()
    features_df = pipe.build_real_features(raw)
    feat_time = time.time() - t0
    logger.info(f"Feature engineering done in {feat_time:.1f}s")

    # Validate contract
    assert pipe.validate_feature_contract(features_df), "Feature contract FAILED"
    logger.info("Feature contract: PASS")

    # Chronological split (identical for all models)
    train_df, val_df, test_df = pipe.split_temporally(features_df, train_frac=0.7, val_frac=0.15)
    logger.info(f"Train={len(train_df)}  Val={len(val_df)}  Test={len(test_df)}")
    logger.info(f"Train fraud prevalence: {train_df[TARGET_COL].mean():.4f}")
    logger.info(f"Val   fraud prevalence: {val_df[TARGET_COL].mean():.4f}")

    y_train = train_df[TARGET_COL]
    y_val   = val_df[TARGET_COL]

    # ─────────────────────────────────────────────────────────
    # Build MODEL A feature table
    # We need the original 13 features. Some were named differently in the
    # old contract vs the new pipeline output. Map them:
    # ─────────────────────────────────────────────────────────
    A_MAP = {
        "amount":           "TransactionAmt",   # raw passthrough
        "log_amount":       "log_amount",
        "product_type":     "ProductCD",
        "card_network":     "card4",
        "card_type":        "card6",
        "card_issuer_proxy":"card3",
        "email_domain":     "P_emaildomain",
        "time_of_day_proxy":"time_of_day_proxy",
        "entity_txn_count_1h":"entity_txn_count_1h",
        "entity_txn_count_24h":"entity_txn_count_24h",
        "entity_avg_amount_24h":"entity_avg_amount_24h",
        "amount_deviation": "amount_deviation",
        "time_since_last_txn":"time_since_last_txn",
    }
    missing_a = [v for v in A_MAP.values() if v not in features_df.columns]
    if missing_a:
        raise KeyError(f"Model A columns missing from feature table: {missing_a}")

    X_train_a = train_df[[v for v in A_MAP.values()]].copy()
    X_val_a   = val_df[[v for v in A_MAP.values()]].copy()
    # Rename to friendly names for the artifact
    X_train_a.columns = list(A_MAP.keys())
    X_val_a.columns   = list(A_MAP.keys())
    cat_a = _get_cat_cols(list(A_MAP.keys()), X_train_a)

    # ─────────────────────────────────────────────────────────
    # MODEL B: ENGINEERED_CORE features
    # ─────────────────────────────────────────────────────────
    B_COLS = list(ENGINEERED_CORE.keys())
    missing_b = [c for c in B_COLS if c not in features_df.columns]
    if missing_b:
        logger.warning(f"Model B missing columns (will skip): {missing_b}")
        B_COLS = [c for c in B_COLS if c in features_df.columns]

    X_train_b = train_df[B_COLS].copy()
    X_val_b   = val_df[B_COLS].copy()
    cat_b = _get_cat_cols(B_COLS, X_train_b)

    # ─────────────────────────────────────────────────────────
    # MODEL C: ENGINEERED_CORE + RAW_SAFE
    # ─────────────────────────────────────────────────────────
    C_COLS_ENG = list(ENGINEERED_CORE.keys())
    C_COLS_RAW = [c for c in RAW_SAFE.keys() if c in features_df.columns and c not in C_COLS_ENG]
    C_COLS = C_COLS_ENG + C_COLS_RAW
    logger.info(f"Model C columns: {len(C_COLS)} ({len(C_COLS_ENG)} engineered + {len(C_COLS_RAW)} raw_safe)")

    excluded_raw = [c for c in RAW_SAFE.keys() if c not in features_df.columns]
    if excluded_raw:
        logger.warning(f"Model C RAW_SAFE columns absent from feature table (skipped): {excluded_raw}")

    X_train_c = train_df[C_COLS].copy()
    X_val_c   = val_df[C_COLS].copy()
    cat_c = _get_cat_cols(C_COLS, X_train_c)

    logger.info(f"Model C categorical cols: {len(cat_c)}")
    logger.info(f"Model C numeric cols: {len(C_COLS) - len(cat_c)}")

    # ─────────────────────────────────────────────────────────
    # TRAIN
    # ─────────────────────────────────────────────────────────
    results = {}

    ma_tr, ma_vl, ma_imp, ma_dim, ma_t = _train_model(
        "MODEL_A_BASELINE_13",
        X_train_a.copy(), y_train, X_val_a.copy(), y_val, cat_a,
        os.path.join(ARTIFACT_DIR, "model_a_baseline_13.joblib"),
    )
    results["A"] = dict(name="A (13-feat)", src=13, dim=ma_dim,
                        train=ma_tr, val=ma_vl, time=ma_t)

    mb_tr, mb_vl, mb_imp, mb_dim, mb_t = _train_model(
        "MODEL_B_ENGINEERED_22",
        X_train_b.copy(), y_train, X_val_b.copy(), y_val, cat_b,
        os.path.join(ARTIFACT_DIR, "model_b_engineered_22.joblib"),
    )
    results["B"] = dict(name="B (22-eng)", src=len(B_COLS), dim=mb_dim,
                        train=mb_tr, val=mb_vl, time=mb_t)

    mc_tr, mc_vl, mc_imp, mc_dim, mc_t = _train_model(
        "MODEL_C_ENGINEERED_PLUS_RAW",
        X_train_c.copy(), y_train, X_val_c.copy(), y_val, cat_c,
        os.path.join(ARTIFACT_DIR, "model_c_engineered_raw_safe.joblib"),
    )
    results["C"] = dict(name="C (eng+raw)", src=len(C_COLS), dim=mc_dim,
                        train=mc_tr, val=mc_vl, time=mc_t)

    # ─────────────────────────────────────────────────────────
    # COMPARISON TABLE
    # ─────────────────────────────────────────────────────────
    print("\n" + "="*80)
    print("THREE-WAY REAL MODEL COMPARISON")
    print("="*80)

    header = f"{'Model':<20} {'SrcFeat':>8} {'TrDim':>7} {'TrROC':>7} {'VaROC':>7} {'TrPR':>7} {'VaPR':>7} {'VaPrec':>7} {'VaRec':>7} {'VaF1':>7} {'VaFPR':>7}"
    print(header)
    print("-"*len(header))
    for k, r in results.items():
        print(
            f"{r['name']:<20} {r['src']:>8} {r['dim']:>7} "
            f"{r['train']['roc_auc']:>7.4f} {r['val']['roc_auc']:>7.4f} "
            f"{r['train']['pr_auc']:>7.4f} {r['val']['pr_auc']:>7.4f} "
            f"{r['val']['precision']:>7.4f} {r['val']['recall']:>7.4f} "
            f"{r['val']['f1']:>7.4f} {r['val']['fpr']:>7.4f}"
        )

    def delta(a, b, key):
        return round(b[key] - a[key], 4)

    print("\n── Deltas ─────────────────────────────────────────────────────")
    for pair, (ka, kb) in [("B-A", ("A", "B")), ("C-B", ("B", "C")), ("C-A", ("A", "C"))]:
        ra, rb = results[ka], results[kb]
        print(f"\n  {pair}:")
        for metric in ("roc_auc", "pr_auc", "precision", "recall", "f1", "fpr", "fnr"):
            da = delta(ra["val"], rb["val"], metric)
            arrow = "▲" if da > 0.0005 else ("▼" if da < -0.0005 else "~")
            print(f"    val_{metric:12s}: {arrow} {da:+.4f}")

    # ── Generalization gaps ──────────────────────────────────
    print("\n── Generalization gaps (Train − Val) ──────────────────────────")
    for k, r in results.items():
        gap_roc = round(r["train"]["roc_auc"] - r["val"]["roc_auc"], 4)
        gap_pr  = round(r["train"]["pr_auc"]  - r["val"]["pr_auc"],  4)
        print(f"  {r['name']}: ROC gap={gap_roc:+.4f}  PR gap={gap_pr:+.4f}")

    # ── Model C Feature Importance (top 30) ─────────────────
    print("\n── Model C: Top-30 Transformed Feature Importances ───────────")
    top30_c = sorted(mc_imp.items(), key=lambda x: -x[1])[:30]
    for feat, imp in top30_c:
        print(f"  {feat[:60]:<60} {imp:.6f}")

    # ── Model C: Aggregated source-feature importance ────────
    print("\n── Model C: Aggregated by SOURCE feature ───────────────────────")
    agg: dict[str, float] = {}
    for feat, imp in mc_imp.items():
        # OHE produces names like "cat__ProductCD_W" or "num__TransactionAmt"
        # Strip transformer prefix then split on first _ to get base name
        stripped = feat.split("__", 1)[-1]  # remove "cat__" / "num__"
        best_match = stripped
        for col in C_COLS:
            if stripped == col or stripped.startswith(col + "_") or stripped.startswith(col):
                best_match = col
                break
        agg[best_match] = agg.get(best_match, 0.0) + imp

    agg_sorted = sorted(agg.items(), key=lambda x: -x[1])[:30]
    for src, imp in agg_sorted:
        print(f"  {src:<50} {imp:.6f}")

    # ── Feature-family importance ────────────────────────────
    FAMILIES = {
        "V-series":    [c for c in C_COLS if c.startswith("V") and c[1:].isdigit()],
        "C-series":    [c for c in C_COLS if c.startswith("C") and c[1:].isdigit()],
        "D-series":    [c for c in C_COLS if c.startswith("D") and c[1:].isdigit()],
        "M-series":    [c for c in C_COLS if c.startswith("M") and c[1:].isdigit()],
        "id-series":   [c for c in C_COLS if c.startswith("id_")],
        "card":        [c for c in C_COLS if c.startswith("card")],
        "address":     [c for c in C_COLS if c.startswith("addr") or c.startswith("dist")],
        "email":       [c for c in C_COLS if "email" in c or "email" in c.lower()],
        "device":      [c for c in C_COLS if c in ("DeviceType", "DeviceInfo") or c.startswith("id_3")],
        "transaction": ["TransactionAmt", "ProductCD"],
        "entity-eng":  [c for c in C_COLS if c.startswith("entity_") or c in ("amount_deviation","amount_relative_24h","entity_velocity_24h_7d")],
        "temporal-eng":[c for c in C_COLS if c in ("log_amount","time_of_day_proxy","day_of_week_proxy","time_since_last_txn","entity_is_new")],
        "missing-ind": [c for c in C_COLS if c.endswith("_missing") or c in ("identity_present","m_match_count")],
        "combo-eng":   [c for c in C_COLS if c in ("email_suffix","network_product_combo")],
    }

    print("\n── Model C: Feature-Family Importance ──────────────────────────")
    fam_imp: dict[str, float] = {}
    for fam, cols in FAMILIES.items():
        total = 0.0
        for col in cols:
            total += agg.get(col, 0.0)
        fam_imp[fam] = total

    for fam, imp in sorted(fam_imp.items(), key=lambda x: -x[1]):
        print(f"  {fam:<20} {imp:.6f}")

    # ── V-series inspection ──────────────────────────────────
    v_cols_c = [c for c in C_COLS if c.startswith("V") and c[1:].isdigit()]
    if v_cols_c:
        v_importance = {c: agg.get(c, 0.0) for c in v_cols_c}
        v_top10 = sorted(v_importance.items(), key=lambda x: -x[1])[:10]
        total_v = sum(v_importance.values())
        total_all = sum(mc_imp.values())
        print("\n── V-series Analysis ───────────────────────────────────────────")
        print(f"  V-series total importance: {total_v:.4f} / {total_all:.4f} ({100*total_v/total_all:.1f}%)")
        print("  Top-10 V features:")
        for col, imp in v_top10:
            print(f"    {col}: {imp:.6f}")
        if total_v / total_all > 0.5:
            print("  ⚠️  WARNING: V-series dominate (>50% total importance). Flag for leakage review.")
        else:
            print("  ✓ V-series contribution is within reasonable range.")

    print("\n── Artifact paths ──────────────────────────────────────────────")
    for path in [
        "data/model_a_baseline_13.joblib",
        "data/model_b_engineered_22.joblib",
        "data/model_c_engineered_raw_safe.joblib",
    ]:
        size = os.path.getsize(path) // 1024 if os.path.exists(path) else -1
        print(f"  {path}  ({size} KB)")

    print("\nHELD-OUT TEST EVALUATED: NO")
    print("SYNTHETIC TRAINING: NO")
    print("CROSS-DATASET MERGE: NO")
    print("PRODUCTION MODEL REPLACED: NO")
    print("PRODUCTION THRESHOLDS CHANGED: NO")

    return results


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    main()
