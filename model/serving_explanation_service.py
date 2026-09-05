from typing import Any, Dict
import pandas as pd
from model.serving_shap_explainer import ServingSHAPExplainer
from model.explanation_formatter import format_feature_explanation

class ServingExplanationService:
    def __init__(self, explainer: ServingSHAPExplainer):
        self.explainer = explainer

    def explain_transaction(
        self,
        X: pd.DataFrame,
        fraud_probability: float,
        top_positive_k: int = 5,
        top_negative_k: int = 3
    ) -> Dict[str, Any]:
        """
        Generates a human-readable, deterministic explanation of the ML model's decision.
        """
        raw_explanation = self.explainer.explain(
            X, 
            top_positive_k=top_positive_k, 
            top_negative_k=top_negative_k
        )

        if raw_explanation.get("status") != "AVAILABLE":
            return {
                "status": "UNAVAILABLE",
                "reason": raw_explanation.get("reason", "Unknown error during explanation extraction.")
            }

        metadata = {
            "explains": "MODEL_SCORE",
            "fraud_probability": round(fraud_probability, 6),
            "calibrator": "isotonic",
            "explanation_method": "TreeSHAP"
        }

        top_positive_formatted = []
        for item in raw_explanation.get("top_positive", []):
            formatted_text = format_feature_explanation(
                feature=item["feature"],
                value=item["value"],
                direction=item["direction"],
                shap_value=item["shap_value"]
            )
            top_positive_formatted.append({
                "feature": item["feature"],
                "value": item["value"],
                "shap_value": item["shap_value"],
                "direction": item["direction"],
                "description": formatted_text
            })
            
        top_negative_formatted = []
        for item in raw_explanation.get("top_negative", []):
            formatted_text = format_feature_explanation(
                feature=item["feature"],
                value=item["value"],
                direction=item["direction"],
                shap_value=item["shap_value"]
            )
            top_negative_formatted.append({
                "feature": item["feature"],
                "value": item["value"],
                "shap_value": item["shap_value"],
                "direction": item["direction"],
                "description": formatted_text
            })

        return {
            "status": "AVAILABLE",
            "metadata": metadata,
            "top_positive": top_positive_formatted,
            "top_negative": top_negative_formatted,
        }
