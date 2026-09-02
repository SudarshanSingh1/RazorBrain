from api.events import InMemoryEventBroker, EventProcessor
import asyncio
import os
import logging
import pandas as pd
from contextlib import asynccontextmanager
from fastapi import FastAPI

from database.migrations import run_migrations
from data.generator import generate_transactions
from model.feature_engineering import compute_historical_features, fit_transform_features, get_feature_matrix, get_target
from model.baseline import train_baseline
from model.calibration import fit_calibration
from model.explanation import create_explainer
from model.rule_engine import extract_training_thresholds
from model.decision_engine import DecisionPolicy
from model.explanation_engine import ExplanationEngine

logger = logging.getLogger(__name__)

class AppState:
    """Holds global reusable application state."""
    def __init__(self):
        self.model_artifact = None
        self.calibration_artifact = None
        self.explainer_artifact = None
        self.training_thresholds = None
        self.feature_encoder_state = None
        self.decision_policy = None
        self.explanation_engine = None
        self.db_path = os.environ.get("RAZORBRAIN_DB_PATH", "razorbrain_api.db")
        self.is_ready = False
        self.broker = None
        self.processor = None
        self.processor_task = None

app_state = AppState()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Initializing Database Migrations...")
    run_migrations(db_path=app_state.db_path)
    
    
    logger.info("Reconciling stale PROCESSING events from previous crashes...")
    from database.connection import get_session
    
    import sqlite3
    
    try:
        with sqlite3.connect(app_state.db_path) as conn:
            c = conn.cursor()
            c.execute("UPDATE processed_events SET status = 'PROCESSING_FAILED', updated_at = CURRENT_TIMESTAMP WHERE status = 'PROCESSING'")
            stale_count = c.rowcount
            if stale_count > 0:
                logger.warning(f"Reconciled {stale_count} stale events from PROCESSING to PROCESSING_FAILED.")
    except Exception as e:
        logger.error(f"Failed to reconcile stale events: {e}")

    logger.info("Initializing ML Infrastructure (Bootstrapping prototype state)...")
    # In a production environment, artifacts would be loaded from disk/S3.
    # For this prototype, we quickly bootstrap a small subset to ensure the engine is fully operational.
    raw_df = generate_transactions(n=1000, seed=1337)
    df_hist = compute_historical_features(raw_df)
    train_feat, state = fit_transform_features(df_hist)
    X_train = get_feature_matrix(train_feat)
    y_train = get_target(train_feat)
    
    app_state.feature_encoder_state = state
    app_state.model_artifact = train_baseline(X_train, y_train)
    app_state.calibration_artifact = fit_calibration(app_state.model_artifact, X_train, y_train, method="isotonic")
    
    # SHAP Explainer
    # Background dataset for SHAP
    app_state.explainer_artifact = create_explainer(app_state.model_artifact, X_train)
    
    app_state.training_thresholds = extract_training_thresholds(X_train)
    app_state.decision_policy = DecisionPolicy(allow_threshold=0.10, block_threshold=0.40)
    app_state.explanation_engine = ExplanationEngine()
    
    
    # Initialize Real-Time Event Processing
    app_state.broker = InMemoryEventBroker(max_size=1000)
    app_state.processor = EventProcessor(
        consumer=app_state.broker, 
        publisher=app_state.broker, 
        app_state=app_state
    )
    # Run the event processor in background
    app_state.processor_task = asyncio.create_task(app_state.processor.start())

    app_state.is_ready = True
    logger.info("RazorBrain API is ready with Real-Time Processing enabled.")
    
    yield
    
    # Shutdown
    logger.info("Shutting down RazorBrain API.")
    app_state.is_ready = False
    
    if app_state.processor:
        app_state.processor.stop()
    if app_state.processor_task:
        app_state.processor_task.cancel()
        try:
            await app_state.processor_task
        except asyncio.CancelledError:
            pass
