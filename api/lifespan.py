from api.events import InMemoryEventBroker, EventProcessor
import asyncio
import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI

from database.migrations import run_migrations
from model.decision_engine import DecisionPolicy
from model.explanation_engine import ExplanationEngine

logger = logging.getLogger(__name__)


class AppState:
    """Holds global reusable application state."""
    def __init__(self):
        # ── Model C (research benchmark, unchanged) ────────────────────────
        self.model_artifact = None
        self.calibration_artifact = None
        self.explainer_artifact = None
        self.training_thresholds = None
        self.feature_encoder_state = None
        self.decision_policy = None
        self.explanation_engine = None
        self.reference_distribution = None

        # ── Razorpay Serving Model stack ──────────────────────────────────
        self.serving_loader = None              # ServingModelLoader
        self.serving_policy_loader = None       # ServingPolicyLoader
        self.serving_shap_explainer = None      # ServingSHAPExplainer
        self.serving_model_ready = False        # Serving stack ready flag

        # ── Infrastructure ────────────────────────────────────────────────
        db_env = os.environ.get("RAZORBRAIN_DB_PATH", "razorbrain_api.db")
        db_dir = os.path.dirname(db_env)
        if db_dir and not os.path.exists(db_dir):
            self.db_path = "razorbrain_api.db"
        else:
            self.db_path = db_env
        self.is_ready = False
        self.broker = None
        self.processor = None
        self.processor_task = None


app_state = AppState()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────────────────────────────────
    logger.info("Initializing Database Migrations...")
    run_migrations(db_path=app_state.db_path)

    logger.info("Reconciling stale PROCESSING events from previous crashes...")
    import sqlite3
    try:
        with sqlite3.connect(app_state.db_path) as conn:
            c = conn.cursor()
            c.execute(
                "UPDATE processed_events SET status = 'PROCESSING_FAILED', "
                "updated_at = CURRENT_TIMESTAMP WHERE status = 'PROCESSING'"
            )
            stale_count = c.rowcount
            if stale_count > 0:
                logger.warning(f"Reconciled {stale_count} stale PROCESSING events.")
    except Exception as e:
        logger.error(f"Failed to reconcile stale events: {e}")

    # ── Model C (frozen research benchmark) ──────────────────────────────────
    logger.info("Initializing ML Infrastructure (Model C)...")
    from model.model_artifact import load_model_artifact
    try:
        artifact = load_model_artifact()
        if artifact:
            app_state.model_artifact = artifact
            app_state.calibration_artifact = artifact
            app_state.explainer_artifact = artifact

            import json
            try:
                with open("data/validation_selected_policy.json") as pf:
                    pol = json.load(pf)
                    app_state.decision_policy = DecisionPolicy(
                        t_review=pol.get("T_review", 0.1258),
                        t_block=pol.get("T_block", 0.3125)
                    )
            except Exception:
                app_state.decision_policy = DecisionPolicy(t_review=0.1258, t_block=0.3125)

            app_state.feature_encoder_state = {}
            app_state.training_thresholds = {
                "amount_p99": 5000.0,
                "txns_last_24h_p99": 5.0,
                "txns_last_1h_p99": 2.0,
                "txns_last_5min_p99": 1.0,
                "amount_deviation_p99": 3.0,
                "merchant_fraud_rate_p95": 0.05
            }
            app_state.is_ready = True
            logger.info("Model C is ready for inference.")
    except Exception as e:
        logger.error(f"Model C unavailable: {e}")
        app_state.is_ready = False

    # Ensure policy and engine are always set (even if model is unavailable)
    if app_state.decision_policy is None:
        app_state.decision_policy = DecisionPolicy(t_review=0.1258, t_block=0.3125)
    app_state.explanation_engine = ExplanationEngine()

    # ── Razorpay Serving Model stack ──────────────────────────────────────────
    logger.info("Initializing Razorpay Serving Model stack...")
    try:
        from model.serving_model_loader import ServingModelLoader
        from model.serving_policy_loader import ServingPolicyLoader
        from model.serving_shap_explainer import ServingSHAPExplainer
        from model.serving_rule_engine import ServingRuleEngine
        from model.serving_risk_fusion import HybridRiskFusionEngine
        from model.decision_engine_v2 import DecisionPolicyV2, DecisionEngineV2

        serving_loader = ServingModelLoader()
        # Track validation: ServingModelLoader does not store model_track in metadata
        # by default, but ServingPolicyLoader enforces it explicitly.
        serving_policy = ServingPolicyLoader()
        # ServingPolicyLoader.__init__ raises ValueError if model_track != RAZORPAY_SERVING_MODEL

        shap_explainer = ServingSHAPExplainer()

        serving_rule_engine = ServingRuleEngine()
        hybrid_fusion_engine = HybridRiskFusionEngine()

        decision_policy_v2 = DecisionPolicyV2()
        decision_engine_v2 = DecisionEngineV2(
            policy=decision_policy_v2,
            rule_engine=serving_rule_engine,
            fusion_engine=hybrid_fusion_engine,
        )

        app_state.serving_loader = serving_loader
        app_state.serving_policy_loader = serving_policy
        app_state.serving_shap_explainer = shap_explainer
        app_state.serving_rule_engine = serving_rule_engine
        app_state.hybrid_fusion_engine = hybrid_fusion_engine
        app_state.decision_engine_v2 = decision_engine_v2
        app_state.serving_model_ready = True

        logger.info(
            f"Razorpay Serving Model ready: "
            f"T_review={serving_policy.t_review:.4f}  T_block={serving_policy.t_block:.4f} | "
            f"Rule Engine v1 & Hybrid Risk Fusion Loaded"
        )
    except Exception as e:
        logger.error(
            f"RAZORPAY SERVING MODEL UNAVAILABLE — "
            f"all serving transactions will receive REVIEW: {e}"
        )
        app_state.serving_model_ready = False

    # ── Real-Time Event Processing ────────────────────────────────────────────
    app_state.broker = InMemoryEventBroker(max_size=1000)
    app_state.processor = EventProcessor(
        consumer=app_state.broker,
        publisher=app_state.broker,
        app_state=app_state
    )
    app_state.processor_task = asyncio.create_task(app_state.processor.start())

    if app_state.is_ready:
        logger.info("RazorBrain API is fully ready with ML and Real-Time Processing enabled.")
    else:
        logger.warning("RazorBrain API is running, but Model C inference is UNAVAILABLE.")

    yield

    # ── Shutdown ──────────────────────────────────────────────────────────────
    logger.info("Shutting down RazorBrain API.")
    app_state.is_ready = False
    app_state.serving_model_ready = False

    if app_state.processor:
        app_state.processor.stop()
    if app_state.processor_task:
        app_state.processor_task.cancel()
        try:
            await app_state.processor_task
        except asyncio.CancelledError:
            pass
