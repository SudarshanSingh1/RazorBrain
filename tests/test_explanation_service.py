import pandas as pd
from model.serving_shap_explainer import ServingSHAPExplainer
from model.serving_explanation_service import ServingExplanationService
from model.explanation_formatter import format_feature_explanation

def test_formatter():
    assert format_feature_explanation("amount", 2500, "INCREASES_MODEL_SCORE", 0.5) == "Transaction amount of 2500 increased the risk score."
    assert format_feature_explanation("is_new_customer", 1, "INCREASES_MODEL_SCORE", 0.5) == "Transaction from a new customer increased the risk score."
    assert format_feature_explanation("is_new_customer", 0, "DECREASES_MODEL_SCORE", -0.5) == "Transaction from a returning customer decreased the risk score."

def test_serving_explanation_service():
    explainer = ServingSHAPExplainer()
    service = ServingExplanationService(explainer)

    # Use the fixture from the explainer module
    from model.serving_shap_explainer import make_fixture
    X = make_fixture()
    
    result = service.explain_transaction(X, fraud_probability=0.15)
    
    assert result["status"] == "AVAILABLE"
    assert "metadata" in result
    assert result["metadata"]["explains"] == "MODEL_SCORE"
    assert result["metadata"]["fraud_probability"] == 0.15
    assert len(result["top_positive"]) > 0
    assert len(result["top_negative"]) > 0
    
    # Check that it's formatted
    assert "description" in result["top_positive"][0]

def test_serving_explanation_service_invalid_input():
    explainer = ServingSHAPExplainer()
    service = ServingExplanationService(explainer)
    
    # Missing columns
    X = pd.DataFrame([{"amount": 100}])
    result = service.explain_transaction(X, fraud_probability=0.15)
    
    assert result["status"] == "UNAVAILABLE"
    assert "reason" in result
