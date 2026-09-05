
def format_feature_explanation(feature: str, value: any, direction: str, shap_value: float) -> str:
    """
    Format a feature and its raw value into a human-readable deterministic string.
    Does NOT assert causality. Only explains what the model observed.
    """
    impact = "increased" if direction == "INCREASES_MODEL_SCORE" else "decreased"
    
    formatted_value = str(value)
    if isinstance(value, float):
        formatted_value = f"{value:.2f}"
    
    if feature == "amount":
        return f"Transaction amount of {formatted_value} {impact} the risk score."
    elif feature == "log_amount":
        return f"Log-scaled transaction amount of {formatted_value} {impact} the risk score."
    elif feature == "hour_of_day":
        hour = int(value)
        return f"Transaction occurring at hour {hour:02d}:00 {impact} the risk score."
    elif feature == "day_of_week":
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        day_str = days[int(value)] if 0 <= int(value) <= 6 else str(value)
        return f"Transaction occurring on {day_str} {impact} the risk score."
    elif feature == "email_domain":
        return f"Email domain '{value}' {impact} the risk score."
    elif feature == "email_domain_missing":
        if int(value) == 1:
            return f"Missing email domain {impact} the risk score."
        else:
            return f"Presence of an email domain {impact} the risk score."
    elif feature == "card_network":
        return f"Card network '{value}' {impact} the risk score."
    elif feature == "card_type":
        return f"Card type '{value}' {impact} the risk score."
    elif feature == "previous_transaction_count":
        return f"Customer having {int(value)} previous transactions {impact} the risk score."
    elif feature == "is_new_customer":
        status = "new customer" if int(value) == 1 else "returning customer"
        return f"Transaction from a {status} {impact} the risk score."
    elif feature == "avg_customer_amount":
        return f"Customer's historical average amount of {formatted_value} {impact} the risk score."
    elif feature == "amount_deviation":
        return f"Amount deviation of {formatted_value} from historical average {impact} the risk score."
    elif feature == "amount_ratio":
        return f"Amount ratio of {formatted_value}x relative to historical average {impact} the risk score."
    elif feature == "txns_last_1h":
        return f"Velocity of {int(value)} transactions in the last hour {impact} the risk score."
    elif feature == "txns_last_24h":
        return f"Velocity of {int(value)} transactions in the last 24 hours {impact} the risk score."
    else:
        return f"Feature '{feature}' with value {formatted_value} {impact} the risk score."
