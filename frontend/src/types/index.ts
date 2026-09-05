export type DecisionType = 'ALLOW' | 'REVIEW' | 'BLOCK';
export type ConfidenceType = 'NONE' | 'MEDIUM' | 'HIGH';
export type GroundTruthType = 'FRAUD' | 'LEGITIMATE';

export interface DecisionRecord {
  decision: DecisionType;
  decision_reason?: string;
  blocking_guardrail_status?: string;
}

export interface RuleEvidence {
  rule_id: string;
  severity: string;
}

export interface ModelEvidence {
  feature_name: string;
  shap_contribution: number;
}

export interface TransactionSummary {
  assessment_id: string;
  transaction_id: string;
  timestamp: string;
  amount: number;
  currency?: string;
  customer_id: string;
  merchant_id: string;
  decision: DecisionType;
  primary_risk_probability: number | null;
  confidence_in_probability: ConfidenceType | string;
  context_data?: any;
}

export interface DashboardSummaryData {
  total_assessments: number;
  decisions: {
    ALLOW: number;
    REVIEW: number;
    BLOCK: number;
  };
  confidence: Record<string, number>;
}

export interface EvaluationMetrics {
  labeled_volume: number;
  fraud_labels: number;
  legitimate_labels: number;
  tp: number;
  fp: number;
  tn: number;
  fn: number;
  unresolved: number;
  precision: string | number;
  recall: string | number;
  f1: string | number;
  specificity?: string | number;
  fpr?: string | number;
  fnr?: string | number;
}
