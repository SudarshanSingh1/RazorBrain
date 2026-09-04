import uuid
import logging
import pandas as pd
from typing import Dict, Any

from database.connection import get_session
from database.repository import save_assessment, get_assessment

from model.feature_engineering import compute_historical_features
from model.risk_fusion import fuse_risk_batch
from model.decision_engine import make_decision

logger = logging.getLogger(__name__)

class AssessmentServiceError(Exception):
    pass

class DatabasePersistenceError(Exception):
    def __init__(self, message: str, decision_result: Dict[str, Any] = None):
        super().__init__(message)
        self.decision_result = decision_result

def assess_transaction(txn_data: Dict[str, Any], state) -> Dict[str, Any]:
    """
    Orchestrates the offline risk pipeline for a single transaction.
    """
    try:
        # 1. Prepare data
        raw_df = pd.DataFrame([txn_data])
        
        # 2. Historical features
        df_hist = compute_historical_features(raw_df)
        
        # If stateless API call (len=1), compute_historical_features invents 0. We must fix this!
        if len(raw_df) == 1:
            hist_cols = ["previous_transaction_count", "previous_fraud_count", "avg_customer_amount", 
                         "amount_deviation", "is_new_customer", "merchant_fraud_rate", 
                         "is_new_merchant", "txns_last_5min", "txns_last_1h", "txns_last_24h"]
            for c in hist_cols:
                if txn_data.get(c) is not None:
                    df_hist[c] = txn_data[c]
                else:
                    df_hist[c] = pd.NA
                    
        # 3 & 4. Risk Fusion (Pipeline handles transformation internally)
        fusion_results = fuse_risk_batch(
            df_hist, 
            state.model_artifact["base_model_artifact"] if "base_model_artifact" in state.model_artifact else state.model_artifact, 
            state.calibration_artifact, 
            state.explainer_artifact, 
            state.training_thresholds or {},
            transaction_ids=pd.Series([txn_data.get("transaction_id", "unknown")])
        )
        
        result_payload = fusion_results[0]
        
        # 5. Decision
        decision_result = make_decision(result_payload, state.decision_policy)
        assessment_id = txn_data.get("assessment_id") or str(uuid.uuid4())
        decision_result["assessment_id"] = assessment_id
        
        # 6. Explanation
        explanation_result = None
        try:
            explanation_result = state.explanation_engine.explain(decision_result)
        except Exception as e:
            logger.error(f"Explanation generation failed: {e}")
            # Explanation failure does not block decision return or persistence.
            
    except Exception as e:
        logger.error(f"Risk assessment computation failed: {e}")
        raise AssessmentServiceError("Risk pipeline computation failed.") from e
        
    # 7. Persistence
    from database.repository import DuplicateAssessmentError
    try:
        def _convert(obj):
            import numpy as np
            if isinstance(obj, dict):
                return {k: _convert(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [_convert(v) for v in obj]
            elif isinstance(obj, (np.integer, np.int64, np.int32)):
                return int(obj)
            elif isinstance(obj, (np.floating, np.float64, np.float32)):
                return float(obj)
            elif pd.api.types.is_datetime64_any_dtype(type(obj)):
                return str(obj)
            return obj

        with get_session(state.db_path) as conn:
            clean_txn = _convert(txn_data)
            clean_decision = _convert(decision_result)
            clean_expl = _convert(explanation_result) if explanation_result else None
            
            save_assessment(conn, clean_txn, clean_decision, clean_expl)
    except DuplicateAssessmentError:
        raise
    except Exception as e:
        logger.error(f"Database persistence failed: {e}")
        # Note: We do NOT mutate the decision, we just bubble up the persistence failure explicitly.
        raise DatabasePersistenceError("Failed to persist audit record.", decision_result) from e
        
    # 8. Retrieve authoritative format exactly as persisted
    try:
        with get_session(state.db_path) as conn:
            retrieved = get_assessment(conn, assessment_id)
            if not retrieved:
                raise DatabasePersistenceError("Persisted record not found upon read-back.")
            return retrieved
    except Exception as e:
        logger.error(f"Database retrieval failed: {e}")
        raise DatabasePersistenceError("Failed to retrieve audit record.") from e
