import axios from 'axios';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000',
});

const defaultApiKey = '9362a0101d51b5e4c4f8ca0d252f740dcb8112651cd90c149c3747d0929761f3';
const apiKey = import.meta.env.VITE_API_KEY || defaultApiKey;
api.defaults.headers.common['X-API-Key'] = apiKey;

// Health & Status
export const getHealth = () => api.get('/health');

// Razorpay Test Mode
export const createTestOrder = (data: { amount: number; currency: string; receipt: string; notes: Record<string, string> }) =>
  api.post('/razorpay/test/orders', data);

export const assessTestPayment = (payment_id: string) =>
  api.post('/razorpay/test/assess', { payment_id });

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

export default api;
