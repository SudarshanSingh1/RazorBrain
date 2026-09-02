import axios from 'axios';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000',
});


const apiKey = import.meta.env.VITE_API_KEY;
if (apiKey) {
  api.defaults.headers.common['X-API-Key'] = apiKey;
}

export const getSummary = () => api.get('/dashboard/summary');
export const getRiskDistribution = () => api.get('/dashboard/risk-distribution');
export const getRuleIntelligence = () => api.get('/dashboard/rule-intelligence');
export const getTransactions = (params = {}) => api.get('/dashboard/transactions', { params });
export const getTransactionDetail = (id: string) => api.get(`/dashboard/transactions/${id}`);

export default api;

export const getTrends = () => api.get('/dashboard/trends');
export const getProbabilityAmount = () => api.get('/dashboard/probability-amount');
export const getShapIntelligence = () => api.get('/dashboard/shap-intelligence');
