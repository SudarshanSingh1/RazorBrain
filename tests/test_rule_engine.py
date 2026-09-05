"""
Comprehensive test suite for the Serving Rule Engine.
Tests all rule categories, deterministic prioritization, conflict resolution,
and defensive edge-case handling.
"""

import pytest
from model.serving_rule_engine import ServingRuleEngine


@pytest.fixture
def rule_engine():
    return ServingRuleEngine()


def test_rule_engine_no_rules_triggered(rule_engine):
    clean_features = {
        "amount": 1500.0,
        "is_new_customer": 0,
        "previous_transaction_count": 10,
        "avg_customer_amount": 1400.0,
        "amount_ratio": 1.07,
        "txns_last_1h": 1,
        "txns_last_24h": 2,
        "card_network": "visa",
    }
    triggered = rule_engine.evaluate(clean_features)
    assert len(triggered) == 0


def test_rule_engine_high_value_transaction(rule_engine):
    features = {
        "amount": 600000.0,
        "is_new_customer": 0,
        "previous_transaction_count": 5,
        "card_network": "visa",
    }
    triggered = rule_engine.evaluate(features)
    assert len(triggered) == 1
    assert triggered[0].rule_id == "HIGH_VALUE_TRANSACTION"
    assert triggered[0].severity == "REVIEW"
    assert triggered[0].reason_code == "HIGH_VALUE_TRANSACTION"
    assert "additional risk review" in triggered[0].description.lower() or "review" in triggered[0].description.lower()
    assert triggered[0].observed_values["amount"] == 600000.0


def test_rule_engine_extreme_high_value_transaction(rule_engine):
    features = {
        "amount": 3000000.0,
        "is_new_customer": 0,
        "previous_transaction_count": 5,
        "card_network": "visa",
    }
    triggered = rule_engine.evaluate(features)
    assert len(triggered) == 1
    assert triggered[0].rule_id == "EXTREME_HIGH_VALUE_TRANSACTION"
    assert triggered[0].severity == "STEP_UP"
    assert triggered[0].priority == 150


def test_rule_engine_cold_start_high_amount(rule_engine):
    features = {
        "amount": 75000.0,
        "is_new_customer": 1,
        "previous_transaction_count": 0,
        "card_network": "visa",
    }
    triggered = rule_engine.evaluate(features)
    rule_ids = [r.rule_id for r in triggered]
    assert "COLD_START_HIGH_AMOUNT" in rule_ids
    r = next(r for r in triggered if r.rule_id == "COLD_START_HIGH_AMOUNT")
    assert r.severity == "REVIEW"


def test_rule_engine_high_velocity_1h(rule_engine):
    features = {
        "amount": 1000.0,
        "txns_last_1h": 8,
        "txns_last_24h": 10,
        "card_network": "visa",
    }
    triggered = rule_engine.evaluate(features)
    assert any(r.rule_id == "HIGH_VELOCITY_1H" and r.severity == "STEP_UP" for r in triggered)


def test_rule_engine_elevated_velocity_24h(rule_engine):
    features = {
        "amount": 1000.0,
        "txns_last_1h": 1,
        "txns_last_24h": 25,
        "card_network": "visa",
    }
    triggered = rule_engine.evaluate(features)
    assert any(r.rule_id == "ELEVATED_VELOCITY_24H" and r.severity == "REVIEW" for r in triggered)


def test_rule_engine_significant_amount_deviation(rule_engine):
    features = {
        "amount": 50000.0,
        "is_new_customer": 0,
        "previous_transaction_count": 5,
        "avg_customer_amount": 2000.0,
        "amount_ratio": 25.0,
        "card_network": "visa",
    }
    triggered = rule_engine.evaluate(features)
    assert any(r.rule_id == "SIGNIFICANT_AMOUNT_DEVIATION" and r.severity == "STEP_UP" for r in triggered)


def test_rule_engine_deviation_skipped_for_new_customer(rule_engine):
    # Cold start customer has no baseline, so deviation rule MUST NOT trigger
    features = {
        "amount": 25000.0,
        "is_new_customer": 1,
        "previous_transaction_count": 0,
        "avg_customer_amount": 0.0,
        "amount_ratio": 1.0,
        "card_network": "visa",
    }
    triggered = rule_engine.evaluate(features)
    rule_ids = [r.rule_id for r in triggered]
    assert "SIGNIFICANT_AMOUNT_DEVIATION" not in rule_ids


def test_rule_engine_restricted_card_network(rule_engine):
    features = {
        "amount": 500.0,
        "card_network": "TEST",
    }
    triggered = rule_engine.evaluate(features)
    assert len(triggered) == 1
    assert triggered[0].rule_id == "RESTRICTED_CARD_NETWORK"
    assert triggered[0].severity == "DECLINE"


def test_rule_engine_unknown_card_network_handled_safely(rule_engine):
    features = {
        "amount": 500.0,
        "card_network": "totally_unknown_crypto_network",
    }
    triggered = rule_engine.evaluate(features)
    assert len(triggered) == 0


def test_rule_engine_priority_conflict_resolution(rule_engine):
    # Simultaneous triggers:
    # 1. COLD_START_HIGH_AMOUNT (severity REVIEW, priority 90)
    # 2. HIGH_VELOCITY_1H (severity STEP_UP, priority 120)
    # 3. RESTRICTED_CARD_NETWORK (severity DECLINE, priority 200)
    features = {
        "amount": 60000.0,
        "is_new_customer": 1,
        "previous_transaction_count": 0,
        "txns_last_1h": 7,
        "card_network": "test",
    }
    triggered = rule_engine.evaluate(features)
    assert len(triggered) == 3
    # First must be highest severity: DECLINE
    assert triggered[0].severity == "DECLINE"
    assert triggered[0].rule_id == "RESTRICTED_CARD_NETWORK"
    # Second must be STEP_UP
    assert triggered[1].severity == "STEP_UP"
    assert triggered[1].rule_id == "HIGH_VELOCITY_1H"
    # Third must be REVIEW
    assert triggered[2].severity == "REVIEW"
    assert triggered[2].rule_id == "COLD_START_HIGH_AMOUNT"


def test_rule_engine_numeric_edge_cases(rule_engine):
    # NaN and negative amounts
    features = {
        "amount": -100.0,
        "txns_last_1h": None,
        "card_network": None,
    }
    triggered = rule_engine.evaluate(features)
    assert len(triggered) == 0


def test_rule_engine_missing_policy_file():
    with pytest.raises(FileNotFoundError):
        ServingRuleEngine("data/non_existent_policy.json")
