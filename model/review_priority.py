from typing import Dict, Any, List

def calculate_review_priority(
    probability: float,
    confidence: str,
    rules: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Deterministic operational review prioritization.
    This component ONLY orders operational review queues.
    It DOES NOT alter the underlying ML fraud decision or probability.
    """
    reasons = []
    
    # Analyze rule severity
    has_critical_rule = any(r.get("severity") == "CRITICAL" for r in rules)
    has_high_rule = any(r.get("severity") == "HIGH" for r in rules)
    
    tier = "NORMAL"
    
    # We avoid magic numbers by relying on the existing decision boundaries.
    # REVIEW boundaries are typically >0.10 and <0.40. 
    # We partition the probability space into logical tiers, OR rely on independent severity.
    
    # Probability bounds
    if probability is not None:
        if probability >= 0.30:
            tier = "CRITICAL"
            reasons.append(f"Elevated primary risk probability ({probability:.3f}) approaching the BLOCK threshold.")
        elif probability >= 0.20:
            tier = "HIGH" if tier != "CRITICAL" else tier
            reasons.append(f"Moderate primary risk probability ({probability:.3f}).")
            
    # Independent evidence (Rules)
    # We ensure a single weak signal doesn't dominate by checking severity, which 
    # was already calibrated by the rule engine (Phase 16/17).
    if has_critical_rule:
        tier = "CRITICAL"
        reasons.append("Independent CRITICAL severity behavioral evidence present.")
    elif has_high_rule:
        tier = "HIGH" if tier != "CRITICAL" else tier
        reasons.append("Independent HIGH severity behavioral evidence present.")
        
    if confidence == "NONE":
        reasons.append("Confidence is NONE, requires manual contextualization.")
        
    if not reasons:
        reasons.append("Standard review priority based on baseline assessment.")
        
    components = {
        "probability_tier": "HIGH" if (probability and probability >= 0.30) else "NORMAL",
        "has_critical_rule": has_critical_rule,
        "has_high_rule": has_high_rule,
        "confidence": confidence
    }
    
    return {
        "tier": tier,
        "reasons": reasons,
        "components": components
    }
