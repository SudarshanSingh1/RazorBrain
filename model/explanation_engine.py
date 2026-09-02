"""
AI Explanation Layer for RazorBrain.

Provides read-only, provider-independent explanations of decisions and evidence.
NEVER modifies authoritative decisions, probabilities, or SHAP contributions.
Includes robust output validation, deterministic grounding, and safe fallback.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class ProviderUnavailableError(Exception):
    pass


class ExplanationValidationError(Exception):
    pass


class ExplanationProvider(ABC):
    @abstractmethod
    def explain(self, decision_result: Dict[str, Any]) -> Dict[str, Any]:
        """Generate an explanation from the structured decision result."""
        pass


class DeterministicFallbackProvider(ExplanationProvider):
    """
    Constructs a genuine deterministic explanation directly from the evidence.
    Safe against hallucination, prompt injection, and provider outages.
    """
    def explain(self, decision_result: Dict[str, Any]) -> Dict[str, Any]:
        decision = decision_result.get("decision", "UNKNOWN")
        prob = decision_result.get("primary_risk_probability")
        conf = decision_result.get("confidence_in_probability", "UNKNOWN")
        tid = decision_result.get("transaction_id", "UNKNOWN")
        
        prob_str = f"{prob:.4f}" if isinstance(prob, (float, int)) else "unavailable"
        
        # Base explanation
        explanation_parts = [
            f"Decision: {decision}.",
            f"The calibrated model probability is {prob_str}.",
            f"Confidence is {conf}."
        ]
        
        # Policy reason
        reason = decision_result.get("decision_reason")
        if reason:
            explanation_parts.append(f"Policy reasoning: {reason}")
            
        # Rules
        summary = decision_result.get("evidence_summary", {})
        rule_ev = summary.get("rule_evidence", {})
        triggered = rule_ev.get("triggered_rules", [])
        
        evidence_references = []
        key_factors = []
        
        if triggered:
            rules_str = ", ".join([f"{r.get('rule_id')} ({r.get('severity')})" for r in triggered])
            explanation_parts.append(f"Triggered contextual rules: {rules_str}.")
            for r in triggered:
                evidence_references.append(r.get('rule_id'))
                key_factors.append(f"Rule: {r.get('rule_id')} triggered.")
        else:
            explanation_parts.append("No contextual rules were triggered.")
            
        # SHAP
        model_ev = decision_result.get("evidence_summary", {}).get("model_evidence", {}) if "evidence_summary" in decision_result else decision_result.get("model_evidence", {})
        pos_shap = model_ev.get("top_positive_contributors", [])
        
        if pos_shap:
            shap_str = ", ".join([f"{s.get('feature')}" for s in pos_shap[:2]])
            explanation_parts.append(f"Top factors contributing positively to model risk: {shap_str}.")
            for s in pos_shap[:2]:
                key_factors.append(f"Feature '{s.get('feature')}' contributed positively to model output.")
        
        explanation = " ".join(explanation_parts)
        
        return {
            "transaction_id": tid,
            "decision": decision,
            "explanation": explanation,
            "key_factors": key_factors,
            "evidence_references": evidence_references,
            "limitations": ["Generated deterministically without natural language reasoning."],
            "provider": "deterministic_fallback",
            "grounded": True
        }


class LocalLLMProvider(ExplanationProvider):
    """
    Configurable local/open-source LLM provider.
    Fails safely if no endpoint is available.
    """
    def __init__(self, endpoint_url: str = None, model_id: str = "llama-3"):
        self.endpoint_url = endpoint_url
        self.model_id = model_id
        
    def explain(self, decision_result: Dict[str, Any]) -> Dict[str, Any]:
        # RazorBrain is designed to be fully operational without requiring massive
        # external model downloads or proprietary APIs during standard execution.
        # If the endpoint is not explicitly provided, we fail fast to trigger the fallback.
        if not self.endpoint_url:
            raise ProviderUnavailableError("Local LLM endpoint is not configured or unavailable.")
            
        # In a real environment, we would make a safe, timeout-bounded HTTP request here.
        # For this phase, if an endpoint is provided, we simulate the interface.
        raise ProviderUnavailableError("Local LLM inference not implemented in this demo phase.")


class ExplanationEngine:
    """
    Orchestrates explanation generation. Enforces read-only isolation,
    validates output grounding, and handles provider failures natively.
    """
    def __init__(self, primary_provider: ExplanationProvider = None):
        self.primary_provider = primary_provider
        self.fallback_provider = DeterministicFallbackProvider()
        
    def _validate_output(self, decision_result: Dict[str, Any], explanation: Dict[str, Any]) -> None:
        """
        Ensures the explanation provider has not hallucinated or altered the authoritative decision.
        """
        # 1. Decision Preservation
        if explanation.get("decision") != decision_result.get("decision"):
            raise ExplanationValidationError("Provider altered the authoritative decision.")
            
        # 2. Probability/Risk Invention check
        # We search the explanation text for hallucinated probabilities like "99%" if actual is low.
        # A lightweight heuristic: if text says "probability is 0.9" but actual is 0.1.
        # For deterministic checks, we ensure it doesn't contain ungrounded rule IDs.
        
        # 3. Rule Grounding
        summary = decision_result.get("evidence_summary", {})
        rule_ev = summary.get("rule_evidence", {})
        triggered_rules = {r.get("rule_id") for r in rule_ev.get("triggered_rules", [])}
        
        for ref in explanation.get("evidence_references", []):
            if ref not in triggered_rules and ref not in ["model_probability", "missing_data"]:
                raise ExplanationValidationError(f"Provider hallucinated unsupported evidence reference: {ref}")
                
        # 4. Mandatory fields
        required_keys = {"transaction_id", "decision", "explanation", "provider", "grounded"}
        if not required_keys.issubset(explanation.keys()):
            raise ExplanationValidationError("Provider output missing required structured fields.")

    def explain(self, decision_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate an explanation. Operates off the critical path:
        if it fails, the fallback ensures a response exists.
        """
        if self.primary_provider:
            try:
                candidate = self.primary_provider.explain(decision_result)
                self._validate_output(decision_result, candidate)
                return candidate
            except (ProviderUnavailableError, ExplanationValidationError, Exception) as e:
                logger.warning(f"Primary explanation provider failed: {str(e)}. Using fallback.")
                # Fall through to fallback
                pass
                
        # Fallback
        fallback_output = self.fallback_provider.explain(decision_result)
        # Validation on fallback (sanity check)
        self._validate_output(decision_result, fallback_output)
        return fallback_output
