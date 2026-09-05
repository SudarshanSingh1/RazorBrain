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

export type RiskLevel = 'LOW' | 'MEDIUM' | 'HIGH';

export interface PredictionDetails {
  transaction_id: string;
  fraud_probability: number;
  risk_level: RiskLevel;
  thresholds: {
    low_risk_cutoff: number;
    high_risk_cutoff: number;
  };
  model_version: string;
  model_track: string;
  calibrator: string;
  scored_at: string;
  features_used: Record<string, any>;
}

export interface PredictionResponse {
  success: boolean;
  prediction: PredictionDetails;
}

export type FinalDecisionType = 'APPROVE' | 'REVIEW' | 'STEP_UP' | 'DECLINE';

export interface DecisionTraceItem {
  stage: string;
  decision?: string;
  rule?: string;
  proposed_decision?: string;
  reason?: string;
  applied?: string;
  probability?: string;
  triggered_rules_count?: number;
  [key: string]: any;
}

export interface TriggeredRuleItem {
  rule_id: string;
  triggered: boolean;
  severity: 'INFO' | 'REVIEW' | 'STEP_UP' | 'DECLINE';
  priority: number;
  reason_code: string;
  description: string;
  observed_values: Record<string, any>;
  policy_version: string;
}

export interface HybridRiskAssessmentData {
  fusion_version: string;
  fraud_probability: number;
  model_risk_level: RiskLevel;
  base_decision: FinalDecisionType;
  highest_rule_severity: string;
  recommended_minimum_decision: FinalDecisionType;
  conflict_status: {
    has_conflict: boolean;
    reason?: string | null;
  };
  triggered_rules_count: number;
  triggered_rules: TriggeredRuleItem[];
}

export interface DecisionDetails {
  assessment_id?: string;
  transaction_id: string;
  fraud_probability: number;
  risk_level: RiskLevel;
  base_decision?: FinalDecisionType;
  triggered_rules?: TriggeredRuleItem[];
  hybrid_assessment?: HybridRiskAssessmentData;
  final_decision: FinalDecisionType;
  decision_reason: string;
  decision_trace: DecisionTraceItem[];
  thresholds: {
    approve_max: number;
    review_max: number;
    step_up_max: number;
  };
  model_version: string;
  model_track?: string;
  calibrator?: string;
  rule_policy_version?: string;
  fusion_version?: string;
  case?: {
    case_created: boolean;
    case_id?: string;
    status?: string;
    priority?: string;
    reason?: string;
    warning?: string;
  };
  explanation?: Record<string, any>;
  scored_at: string;
  features_used: Record<string, any>;
}

export interface DecideResponse {
  success: boolean;
  decision: DecisionDetails;
}

export type CaseStatus = 'OPEN' | 'INVESTIGATING' | 'ESCALATED' | 'RESOLVED';
export type CasePriority = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
export type ResolutionType = 'CONFIRMED_FRAUD' | 'CONFIRMED_LEGITIMATE' | 'INCONCLUSIVE' | 'DUPLICATE' | 'OTHER';

export interface CaseEvent {
  event_id: string;
  case_id: string;
  event_type: string;
  previous_state?: string | null;
  new_state?: string | null;
  actor: string;
  metadata?: Record<string, any>;
  created_at: string;
}

export interface InvestigationCase {
  case_id: string;
  transaction_id: string;
  assessment_id: string;
  status: CaseStatus;
  priority: CasePriority;
  assigned_to?: string | null;
  resolution_type?: ResolutionType | null;
  resolution_notes?: string | null;
  escalation_reason?: string | null;
  case_policy_version: string;
  created_from_decision: string;
  created_from_reason: string;
  decision_snapshot: Record<string, any>;
  risk_snapshot: Record<string, any>;
  rule_snapshot: Record<string, any>;
  explanation_snapshot?: Record<string, any>;
  audit_metadata?: Record<string, any>;
  version: number;
  created_at: string;
  updated_at: string;
  resolved_at?: string | null;
}

export interface CaseListStats {
  open_cases: number;
  investigating_cases: number;
  escalated_cases: number;
  resolved_cases: number;
  high_critical_open: number;
  resolved_today: number;
}

export interface CaseListResponse {
  success: boolean;
  items: InvestigationCase[];
  pagination: {
    page: number;
    page_size: number;
    total_items: number;
    total_pages: number;
  };
  stats: CaseListStats;
}

export interface CaseDetailResponse {
  success: boolean;
  case: InvestigationCase;
  events: CaseEvent[];
}

