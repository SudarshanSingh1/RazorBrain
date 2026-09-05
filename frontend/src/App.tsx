import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import Overview from './pages/Overview';
import RiskAnalytics from './pages/RiskAnalytics';
import DriftMonitoring from './pages/DriftMonitoring';
import Evaluation from './pages/Evaluation';
import Transactions from './pages/Transactions';
import ModelPolicyManagement from './pages/ModelPolicyManagement';
import SecuritySettings from './pages/SecuritySettings';
import ReviewQueue from './pages/ReviewQueue';
import AuditTrail from './pages/AuditTrail';
import TransactionDetail from './pages/TransactionDetail';
import ScoreTransaction from './pages/ScoreTransaction';
import Cases from './pages/Cases';
import CaseDetail from './pages/CaseDetail';
import { RazorpayTest } from './pages/RazorpayTest';
import Monitoring from './pages/Monitoring';
import { AppLayout } from './components/layout';

export default function App() {
  return (
    <Router>
      <AppLayout>
        <Routes>
          <Route path="/" element={<Overview />} />
          <Route path="/score-transaction" element={<ScoreTransaction />} />
          <Route path="/cases" element={<Cases />} />
          <Route path="/cases/:caseId" element={<CaseDetail />} />
          <Route path="/risk-analytics" element={<RiskAnalytics />} />
          <Route path="/drift-monitoring" element={<DriftMonitoring />} />
          <Route path="/evaluation" element={<Evaluation />} />
          <Route path="/transactions" element={<Transactions />} />
            <Route path="/registry" element={<ModelPolicyManagement />} />
            <Route path="/security" element={<SecuritySettings />} />
          <Route path="/transactions/:id" element={<TransactionDetail />} />
          <Route path="/review-queue" element={<ReviewQueue />} />
          <Route path="/monitoring" element={<Monitoring />} />
          <Route path="/audit" element={<AuditTrail />} />
          <Route path="/razorpay-test" element={<RazorpayTest />} />
        </Routes>
      </AppLayout>
    </Router>
  );
}
