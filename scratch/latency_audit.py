import time
import pandas as pd
from api.lifespan import app_state
from data.generator import generate_transactions
from model.feature_engineering import compute_historical_features, transform_features
from model.risk_fusion import fuse_risk_batch
from model.decision_engine import make_decision
import uuid
import asyncio

async def run_latency_audit():
    # Bootstrap
    from database.connection import get_session
    from database.migrations import run_migrations
    run_migrations(app_state.db_path)
    
    raw_df = generate_transactions(n=1000, seed=1337)
    from model.feature_engineering import fit_transform_features, get_feature_matrix, get_target
    from model.baseline import train_baseline
    from model.calibration import fit_calibration
    from model.explanation import create_explainer
    from model.rule_engine import extract_training_thresholds
    from model.decision_engine import DecisionPolicy
    from model.explanation_engine import ExplanationEngine
    
    df_hist = compute_historical_features(raw_df)
    train_feat, state = fit_transform_features(df_hist)
    X_train = get_feature_matrix(train_feat)
    y_train = get_target(train_feat)
    
    app_state.feature_encoder_state = state
    app_state.model_artifact = train_baseline(X_train, y_train)
    app_state.calibration_artifact = fit_calibration(app_state.model_artifact, X_train, y_train, method="isotonic")
    app_state.explainer_artifact = create_explainer(app_state.model_artifact, X_train)
    app_state.training_thresholds = extract_training_thresholds(X_train)
    app_state.decision_policy = DecisionPolicy(allow_threshold=0.10, block_threshold=0.40)
    app_state.explanation_engine = ExplanationEngine()
    
    txn_data = {
        "transaction_id": "L-001",
        "timestamp": "2023-01-01T12:00:00Z",
        "amount": 100.0,
        "currency": "USD",
        "customer_id": "C-001",
        "merchant_id": "M-001",
        "payment_method": "credit_card"
    }
    
    measurements = []
    
    t0 = time.perf_counter()
    raw_df_txn = pd.DataFrame([txn_data])
    measurements.append(("pandas_init", time.perf_counter() - t0))
    
    t0 = time.perf_counter()
    df_hist_txn = compute_historical_features(raw_df_txn)
    measurements.append(("feature_construction_hist", time.perf_counter() - t0))
    
    t0 = time.perf_counter()
    df_trans = transform_features(df_hist_txn, app_state.feature_encoder_state)
    X_val = get_feature_matrix(df_trans)
    measurements.append(("feature_construction_trans", time.perf_counter() - t0))
    
    # Let's break down fuse_risk_batch manually
    from model.baseline import predict_proba
    from model.calibration import predict_calibrated_proba
    from model.explanation import explain_batch
    from model.rule_engine import evaluate_rules
    
    t0 = time.perf_counter()
    raw_probs = predict_proba(app_state.model_artifact, X_val)
    measurements.append(("model_prediction", time.perf_counter() - t0))
    
    t0 = time.perf_counter()
    calib_probs = predict_calibrated_proba(app_state.calibration_artifact, X_val)
    measurements.append(("calibration", time.perf_counter() - t0))
    
    t0 = time.perf_counter()
    valid_shap = explain_batch(app_state.explainer_artifact, X_val, max_batch_size=len(X_val))
    measurements.append(("shap", time.perf_counter() - t0))
    
    t0 = time.perf_counter()
    rule_ev = evaluate_rules(X_val, app_state.training_thresholds)
    measurements.append(("rule_evaluation", time.perf_counter() - t0))
    
    # Re-run fusion
    t0 = time.perf_counter()
    fusion_results = fuse_risk_batch(
        X_val, 
        app_state.model_artifact, 
        app_state.calibration_artifact, 
        app_state.explainer_artifact, 
        app_state.training_thresholds,
        transaction_ids=pd.Series([txn_data["transaction_id"]])
    )
    result_payload = fusion_results[0]
    measurements.append(("risk_fusion_total", time.perf_counter() - t0))
    
    t0 = time.perf_counter()
    decision_result = make_decision(result_payload, app_state.decision_policy)
    measurements.append(("decision_engine", time.perf_counter() - t0))
    
    decision_result["assessment_id"] = str(uuid.uuid4())
    
    t0 = time.perf_counter()
    explanation_result = app_state.explanation_engine.explain(decision_result)
    measurements.append(("explanation", time.perf_counter() - t0))
    
    from database.repository import save_assessment
    t0 = time.perf_counter()
    for _ in range(10): # average over 10 inserts to get realistic SQLite time
        try:
            decision_result["assessment_id"] = str(uuid.uuid4())
            with get_session(app_state.db_path) as session:
                save_assessment(session, decision_result)
        except Exception as e:
            pass
    measurements.append(("database_persistence", (time.perf_counter() - t0) / 10))
    
    print("--- COMPONENT LATENCY MEASUREMENTS ---")
    for name, dur in measurements:
        print(f"{name}: {dur*1000:.3f} ms")

asyncio.run(run_latency_audit())
