import axios from 'axios';

// ── API Base URL Configuration ──────────────────────────────────────────────
// Development: Set VITE_API_URL=http://localhost:8000 in .env
// Production:  Set VITE_API_URL=https://your-backend.onrender.com in Render env vars
// The fallback to localhost:8000 is for development convenience only.
export const API_BASE_URL = import.meta.env.VITE_API_URL || 'https://razorbrain.onrender.com';

if (!import.meta.env.VITE_API_URL) {
  console.warn(
    '[RazorBrain] VITE_API_URL is not set. Using default: https://razorbrain.onrender.com\n' +
    'For production, set VITE_API_URL to your backend deployment URL.'
  );
}

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000, // 30 second timeout for all requests
});

const defaultApiKey = '9362a0101d51b5e4c4f8ca0d252f740dcb8112651cd90c149c3747d0929761f3';
const apiKey = import.meta.env.VITE_API_KEY || defaultApiKey;
api.defaults.headers.common['X-API-Key'] = apiKey;

// ── Response Interceptor for Connection Status and Logging ─────────────

api.interceptors.response.use(
  (response) => {
    // If request succeeds, connection is good
    if (typeof window !== 'undefined' && (window as any).__RAZORBRAIN_CONNECTION_MANAGER__) {
      (window as any).__RAZORBRAIN_CONNECTION_MANAGER__.notifyRequestSucceeded();
    }
    return response;
  },
  (error) => {
    // Log clear error details in development
    if (import.meta.env.DEV) {
      if (error.response) {
        console.error(
          `[API Error] ${error.config?.method?.toUpperCase()} ${error.config?.url} | Status: ${error.response.status} | Message:`, 
          error.response.data?.error?.message || error.message
        );
      } else if (error.request) {
        console.error(`[API Error] ${error.config?.method?.toUpperCase()} ${error.config?.url} | Network Error or Timeout`);
      }
    } else {
      // Minimal production logging
      console.error('[API Error] Request failed');
    }

    // Notify connection manager of failure (will trigger health check)
    if (typeof window !== 'undefined' && (window as any).__RAZORBRAIN_CONNECTION_MANAGER__) {
      (window as any).__RAZORBRAIN_CONNECTION_MANAGER__.notifyRequestFailed(error);
    }
    
    return Promise.reject(error);
  }
);

// ── Exported API Base URL (for ConnectionManager and other consumers) ───────
export const getApiBaseUrl = () => API_BASE_URL;

// Health & Status
export const getHealth = () => api.get('/health');

// Razorpay Test Mode
export const createTestOrder = (data: { amount: number; currency: string; receipt: string; notes: Record<string, string> }) =>
  api.post('/razorpay/test/orders', data);

export const assessTestPayment = (payment_id: string) =>
  api.post('/razorpay/test/assess', { payment_id });

// Manual Transaction Scoring
export const scoreTransaction = (payload: any, options?: { signal?: AbortSignal }) =>
  api.post('/predict', payload, options);

export const decideTransaction = (payload: any, options?: { signal?: AbortSignal }) =>
  api.post('/transactions/decide', payload, options);

// Dashboard Overview & Analytics
export const getSummary = () => api.get('/dashboard/summary');
export const getRiskDistribution = () => api.get('/dashboard/risk-distribution');
export const getRuleIntelligence = () => api.get('/dashboard/rule-intelligence');
export const getTrends = () => api.get('/dashboard/trends');
export const getProbabilityAmount = () => api.get('/dashboard/probability-amount');
export const getShapIntelligence = () => api.get('/dashboard/shap-intelligence');
export const getOperationalAnalytics = () => api.get('/dashboard/operational-analytics');
export const getEvaluationMetrics = () => api.get('/analytics/evaluation');
export const getDriftMetrics = (window_hours?: number) => 
  api.get('/dashboard/drift', { params: window_hours ? { window_hours } : {} });
export const getDriftMonitoring = (window_hours?: number) => getDriftMetrics(window_hours);

// Transactions & Manual Review
export const getTransactions = (params = {}) => api.get('/dashboard/transactions', { params });
export const getTransactionDetail = (id: string) => api.get(`/dashboard/transactions/${id}`);
export const recordFeedback = (
  assessmentId: string, 
  groundTruth: 'FRAUD' | 'LEGITIMATE', 
  notes?: string
) => {
  return api.post(`/transactions/${assessmentId}/feedback`, {
    ground_truth: groundTruth,
    label_source: 'MANUAL_REVIEW',
    notes
  });
};

// Simulations
export const simulateReviewCapacity = (params: any) => 
  api.post('/dashboard/review-capacity/simulate', params);

// Investigation Case Management
export const getCases = (params = {}, options?: { signal?: AbortSignal }) =>
  api.get('/cases', { params, ...options });

export const getCaseDetail = (caseId: string, options?: { signal?: AbortSignal }) =>
  api.get(`/cases/${caseId}`, options);

export const createCase = (data: any) =>
  api.post('/cases', data);

export const assignCase = (caseId: string, data: { assigned_to: string; expected_version: number; actor?: string }) =>
  api.post(`/cases/${caseId}/assign`, data);

export const investigateCase = (caseId: string, data: { expected_version: number; notes?: string; actor?: string }) =>
  api.post(`/cases/${caseId}/investigate`, data);

export const escalateCase = (caseId: string, data: { escalation_reason: string; expected_version: number; actor?: string }) =>
  api.post(`/cases/${caseId}/escalate`, data);

export const resolveCase = (caseId: string, data: { resolution_type: string; resolution_notes?: string; expected_version: number; actor?: string }) =>
  api.post(`/cases/${caseId}/resolve`, data);

// Monitoring & Alerts
export const getAlerts = (params = {}) => api.get('/alerts', { params });
export const getAlertDetail = (alertId: string) => api.get(`/alerts/${alertId}`);
export const acknowledgeAlert = (alertId: string, data?: { acknowledged_by?: string }) =>
  api.post(`/alerts/${alertId}/acknowledge`, data || {});
export const resolveAlert = (alertId: string) =>
  api.post(`/alerts/${alertId}/resolve`);
export const getMonitoringSummary = () => api.get('/monitoring/summary');
export const runMonitoringEvaluation = () => api.post('/monitoring/evaluate');

export default api;

// ── Model & Policy Management ────────────────────────────────────────────────
export const getModels = () => api.get('/management/models');
export const getActiveModel = () => api.get('/management/models/active');
export const getModel = (id: string) => api.get(`/management/models/${id}`);
export const registerModel = (data: any) => api.post('/management/models/register', data);
export const activateModel = (id: string) => api.post(`/management/models/${id}/activate`);
export const rollbackModel = (id: string) => api.post(`/management/models/${id}/rollback`);

export const getPolicies = () => api.get('/management/policies');
export const getActivePolicy = () => api.get('/management/policies/active');
export const getPolicy = (id: string) => api.get(`/management/policies/${id}`);
export const createPolicy = (data: any) => api.post('/management/policies', data);
export const activatePolicy = (id: string) => api.post(`/management/policies/${id}/activate`);
export const rollbackPolicy = (id: string) => api.post(`/management/policies/${id}/rollback`);

// ── Security Key Management ─────────────────────────────────────────────────
// Uses the shared axios instance (no hardcoded localhost)
export const getSecurityKeys = () => api.get('/security/keys');
export const createSecurityKey = (data: { name: string; role: string }) => 
  api.post('/security/keys', data);
export const revokeSecurityKey = (keyId: string) => 
  api.post(`/security/keys/${keyId}/revoke`);
export const rotateSecurityKey = (keyId: string, data: { new_name: string; role: string }) => 
  api.post(`/security/keys/${keyId}/rotate`, data);
