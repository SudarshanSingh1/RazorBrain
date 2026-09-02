"""
Tests for SHAP Explainability module.
"""

import pytest
import pandas as pd
import numpy as np

from data.generator import generate_transactions
from model.feature_engineering import compute_historical_features, fit_transform_features, transform_features, get_feature_matrix, get_target
from model.dataset_split import split_chronological
from model.baseline import train_baseline
from model.explanation import create_explainer, explain_batch, explain_transaction


@pytest.fixture(scope="module")
def explanation_fixtures():
    df = generate_transactions(n=1000, seed=42)
    df_hist = compute_historical_features(df)
    train, val, test = split_chronological(df_hist)
    
    train_feat, state = fit_transform_features(train)
    val_feat = transform_features(val, state)
    
    X_train = get_feature_matrix(train_feat)
    y_train = get_target(train_feat)
    X_val = get_feature_matrix(val_feat)
    
    model_art = train_baseline(X_train, y_train)
    explainer_art = create_explainer(model_art, X_train)
    return explainer_art, X_val


def test_explain_transaction(explanation_fixtures):
    explainer_art, X_val = explanation_fixtures
    single_txn = X_val.iloc[[0]]
    
    explanation = explain_transaction(explainer_art, single_txn)
    
    assert "base_value" in explanation
    assert "space" in explanation
    assert "all_contributions" in explanation
    
    contribs = explanation["all_contributions"]
    assert len(contribs) == len(X_val.columns)
    
    # Check feature mapping exactly matches
    mapped_features = [c["feature"] for c in contribs]
    assert set(mapped_features) == set(X_val.columns)
    
    # Check absolute value sorting
    abs_shaps = [abs(c["shap_contribution"]) for c in contribs]
    assert abs_shaps == sorted(abs_shaps, reverse=True)


def test_explain_batch(explanation_fixtures):
    explainer_art, X_val = explanation_fixtures
    batch = X_val.iloc[:10]
    
    explanations = explain_batch(explainer_art, batch)
    assert len(explanations) == 10
    

def test_explain_batch_limit(explanation_fixtures):
    explainer_art, X_val = explanation_fixtures
    # Limit max size to 2
    with pytest.raises(ValueError, match="exceeds maximum limit"):
        explain_batch(explainer_art, X_val.iloc[:5], max_batch_size=2)


def test_edge_cases_shap(explanation_fixtures):
    explainer_art, X_val = explanation_fixtures
    
    edge_cases = pd.DataFrame(columns=X_val.columns)
    base_row = {col: 0.0 for col in X_val.columns}
    
    # Missing / Cold start
    row_new = base_row.copy()
    row_new.update({
        "ip_is_missing": 1.0, "location_is_missing": 1.0,
        "is_new_customer": 1.0, "is_new_merchant": 1.0,
    })
    
    # Extreme Outlier
    row_extreme = base_row.copy()
    row_extreme.update({
        "amount": 9999999.0, "txns_last_5min": 500, "previous_fraud_count": 100
    })
    
    edge_cases.loc[0] = row_new
    edge_cases.loc[1] = row_extreme
    
    explanations = explain_batch(explainer_art, edge_cases)
    assert len(explanations) == 2
    
    for exp in explanations:
        for c in exp["all_contributions"]:
            assert not np.isnan(c["shap_contribution"])
            assert not np.isinf(c["shap_contribution"])
