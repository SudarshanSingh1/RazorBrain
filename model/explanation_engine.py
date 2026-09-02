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
    Safe against hallucination and provider outages. Actual prompt injection
    resistance for future LLMs must be validated when integrated.
    """
    def explain(self, decision_result: Dict[str, Any]) -> Dict[str, Any]:
        decision = decision_result.get("decision", "UNKNOWN")
        prob = decision_result.get("primary_risk_probability")
        conf = decision_result.get("confidence_in_probability")
        tid = decision_result.get("transaction_id", "UNKNOWN")
        
        explanation_parts = [f"Decision: {decision}."]
        
        # Missing probability handling
        if prob is None or not isinstance(prob, (float, int)):
            explanation_parts.append("The calibrated model probability is unavailable.")
        else:
            explanation_parts.append(f"The calibrated model probability is {prob:.4f}.")
            
        if conf:
            explanation_parts.append(f"Confidence is {conf}.")
        else:
            explanation_parts.append("Confidence is unavailable.")
            
        reason = decision_result.get("decision_reason")
        if reason:
            explanation_parts.append(f"Policy reasoning: {reason}")
            
        summary = decision_result.get("evidence_summary")
        evidence_references = []
        key_factors = []
        
        if summary is None or "rule_evidence" not in summary:
            explanation_parts.append("Rule evidence is unavailable.")
        else:
            rule_ev = summary.get("rule_evidence", {})
            triggered = rule_ev.get("triggered_rules")
            
            if triggered is None:
                explanation_parts.append("Rule evidence is unavailable.")
            elif len(triggered) == 0:
                explanation_parts.append("No contextual rules were triggered.")
            else:
                rules_str = ", ".join([f"{r.get('rule_id')} ({r.get('severity')})" for r in triggered])
                explanation_parts.append(f"Triggered contextual rules: {rules_str}.")
                for r in triggered:
                    evidence_references.append(r.get('rule_id'))
                    key_factors.append(f"Rule: {r.get('rule_id')} triggered.")
            
        model_ev = summary.get("model_evidence", {}) if summary else decision_result.get("model_evidence", {})
        if model_ev:
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
            "limitations": ["Generated deterministically without natural language reasoning. Not an LLM."],
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
        if not self.endpoint_url:
            raise ProviderUnavailableError("Local LLM endpoint is not configured or unavailable.")
        raise ProviderUnavailableError("Local LLM inference not implemented in this demo phase.")


class ExplanationEngine:
    """
    Orchestrates explanation generation. Enforces read-only isolation,
    validates output grounding, and handles provider failures natively.
    """
    def __init__(self, primary_provider: ExplanationProvider = None, max_output_length: int = 5000):
        self.primary_provider = primary_provider
        self.max_output_length = max_output_length
        self.fallback_provider = DeterministicFallbackProvider()
        
    def _validate_output(self, decision_result: Dict[str, Any], explanation: Dict[str, Any]) -> None:
        """
        Ensures the explanation provider has not hallucinated, mutated authoritative data,
        or injected unsupported claims.
        """
        # 1. Output length protection
        if len(str(explanation)) > self.max_output_length:
            raise ExplanationValidationError("Provider output exceeded maximum allowed length.")

        # 2. Schema check
        required_keys = {"transaction_id", "decision", "explanation", "provider", "grounded"}
        if not required_keys.issubset(explanation.keys()):
            raise ExplanationValidationError("Provider output missing required structured fields.")

        # 3. Decision Preservation
        if explanation.get("decision") != decision_result.get("decision"):
            raise ExplanationValidationError("Provider altered the authoritative decision.")
            
        # 4. Numeric & Confidence Protection
        if "primary_risk_probability" in explanation:
            if explanation["primary_risk_probability"] != decision_result.get("primary_risk_probability"):
                raise ExplanationValidationError("Provider altered authoritative primary_risk_probability.")
                
        if "confidence_in_probability" in explanation:
            if explanation["confidence_in_probability"] != decision_result.get("confidence_in_probability"):
                raise ExplanationValidationError("Provider altered authoritative confidence_in_probability.")
                
        # Reject completely fabricated numeric scores 
        forbidden_keys = ["risk_score", "fraud_probability_percentage", "fraud_score", "anomaly_score"]
        for fk in forbidden_keys:
            if fk in explanation:
                raise ExplanationValidationError(f"Provider introduced unsupported risk score field: {fk}")

        # 5. Rule Grounding
        summary = decision_result.get("evidence_summary", {})
        rule_ev = summary.get("rule_evidence", {}) if summary else {}
        triggered_rules = {r.get("rule_id") for r in rule_ev.get("triggered_rules", [])} if rule_ev else set()
        
        for ref in explanation.get("evidence_references", []):
            if ref not in triggered_rules and ref not in ["model_probability", "missing_data"]:
                raise ExplanationValidationError(f"Provider hallucinated unsupported evidence reference: {ref}")

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
