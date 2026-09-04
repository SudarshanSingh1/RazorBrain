from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List

class TransactionRequest(BaseModel):
    transaction_id: str = Field(..., max_length=100, description="Unique identifier for the transaction")
    timestamp: str = Field(..., max_length=50, description="ISO-8601 timestamp")
    amount: float = Field(..., ge=0.0, le=1e15, description="Transaction amount")
    currency: str = Field("USD", max_length=10, description="Currency code")
    customer_id: str = Field(..., max_length=100, description="Unique customer identifier")
    merchant_id: str = Field(..., max_length=100, description="Unique merchant identifier")
    payment_method: str = Field(..., max_length=50, description="Payment method used")
    device_id: Optional[str] = Field(None, max_length=100)
    ip_address: Optional[str] = Field(None, max_length=50)
    assessment_id: Optional[str] = Field(None, max_length=100, description="Client-supplied idempotency key")
    
    # Historical Context (Optional, explicitly defined)
    previous_transaction_count: Optional[int] = Field(None, description="Count of prior transactions for this customer")
    previous_fraud_count: Optional[int] = Field(None)
    avg_customer_amount: Optional[float] = Field(None)
    amount_deviation: Optional[float] = Field(None)
    is_new_customer: Optional[int] = Field(None)
    merchant_fraud_rate: Optional[float] = Field(None)
    is_new_merchant: Optional[int] = Field(None)
    txns_last_5min: Optional[int] = Field(None)
    txns_last_1h: Optional[int] = Field(None)
    txns_last_24h: Optional[int] = Field(None)
    customer_account_age_days: Optional[float] = Field(None)

    model_config = ConfigDict(extra="forbid")

class RuleEvidence(BaseModel):
    rule_id: str
    severity: str

class ModelEvidence(BaseModel):
    feature_name: str
    shap_contribution: float

class DecisionRecord(BaseModel):
    decision: str
    decision_reason: Optional[str]
    blocking_guardrail_status: Optional[str]

class ExplanationRecord(BaseModel):
    provider: str
    grounded: bool
    explanation_text: Optional[str]

class RiskAssessmentResponse(BaseModel):
    assessment_id: str
    transaction_id: str
    primary_risk_probability: Optional[float]
    confidence_in_probability: Optional[str]
    
    decision_record: DecisionRecord
    rule_evidence: List[RuleEvidence] = []
    model_evidence: List[ModelEvidence] = []
    explanation_record: Optional[ExplanationRecord] = None
    
class ErrorDetail(BaseModel):
    code: str
    message: str
    request_id: str

class ErrorResponse(BaseModel):
    error: ErrorDetail

class RecordFeedbackRequest(BaseModel):
    ground_truth: str = Field(..., pattern="^(FRAUD|LEGITIMATE)$", description="Ground truth outcome")
    label_source: str = Field(..., max_length=50, description="Source of the label e.g., MANUAL_REVIEW, CHARGEBACK")
    notes: Optional[str] = Field(None, max_length=1000)

    model_config = ConfigDict(extra="forbid")

class EvaluationFeedbackResponse(BaseModel):
    assessment_id: str
    transaction_id: str
    ground_truth: str
    label_source: str
    evaluation_outcome: str
    labeled_at: str

    model_config = ConfigDict(extra="forbid")

class AnalyticsMetricsResponse(BaseModel):
    labeled_volume: int
    fraud_labels: int
    legitimate_labels: int
    tp: int
    fp: int
    tn: int
    fn: int
    unresolved: int
    precision: str
    recall: str
    f1: str
    specificity: str
    fpr: str
    fnr: str

class SimulationRequest(BaseModel):
    horizon_hours: int = Field(24, ge=1, le=720, description="Simulation horizon in hours")
    capacity_per_hour: float = Field(..., ge=0.0, description="Assumed review capacity per hour")
    arrival_rate_per_hour: Optional[float] = Field(None, ge=0.0, description="Assumed arrival rate per hour")
    use_observed_arrival: bool = Field(False, description="Use actual observed arrival rate")
    initial_backlog: int = Field(0, ge=0, description="Starting backlog")

    model_config = ConfigDict(extra="forbid")
