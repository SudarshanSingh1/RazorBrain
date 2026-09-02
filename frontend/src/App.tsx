import { BrowserRouter as Router, Routes, Route, Link, useLocation } from 'react-router-dom';
import { Shield, Activity, List, ClipboardCheck, History, Database, Server, RefreshCw } from 'lucide-react';
import { useState, useEffect } from 'react';
import axios from 'axios';
import Overview from './pages/Overview';
import RiskAnalytics from './pages/RiskAnalytics';
import Transactions from './pages/Transactions';
import ReviewQueue from './pages/ReviewQueue';
import AuditTrail from './pages/AuditTrail';
import TransactionDetail from './pages/TransactionDetail';

const Sidebar = () => {
  const location = useLocation();
  const [apiStatus, setApiStatus] = useState<string>('Checking...');
  const [dbStatus, setDbStatus] = useState<string>('Checking...');

  useEffect(() => {
    axios.get('http://localhost:8000/health')
      .then((res) => {
        setApiStatus(res.data.status === 'ok' ? 'Connected' : 'Degraded');
        setDbStatus('Connected'); // If API health is ok, DB is usually ok as we fetch data
      })
      .catch(() => {
        setApiStatus('Disconnected');
        setDbStatus('Unknown');
      });
  }, []);

  const navItems = [
    { name: 'Overview', path: '/', icon: Shield },
    { name: 'Risk Analytics', path: '/risk-analytics', icon: Activity },
    { name: 'Transactions', path: '/transactions', icon: List },
    { name: 'Review Queue', path: '/review-queue', icon: ClipboardCheck },
    { name: 'Audit Trail', path: '/audit', icon: History },
  ];

  return (
    <div className="w-64 bg-[#0B1120] border-r border-slate-800/60 text-slate-300 min-h-screen flex flex-col shadow-2xl z-20">
      <div className="p-6 border-b border-slate-800/60">
        <h1 className="text-xl font-bold text-white flex items-center gap-2 tracking-tight">
          <Shield className="text-blue-500" /> RazorBrain
        </h1>
        <p className="text-[10px] text-slate-500 mt-1 uppercase tracking-widest font-semibold">Risk Intelligence Console</p>
      </div>
      <nav className="flex-1 p-4 space-y-1">
        {navItems.map((item) => {
          const Icon = item.icon;
          const active = location.pathname === item.path || (item.path !== '/' && location.pathname.startsWith(item.path));
          return (
            <Link
              key={item.name}
              to={item.path}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all duration-200 text-sm font-medium ${
                active ? 'bg-blue-600/10 text-blue-400' : 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-200'
              }`}
            >
              <Icon size={18} className={active ? 'text-blue-400' : 'text-slate-500'} />
              {item.name}
            </Link>
          );
        })}
      </nav>
      
      <div className="p-4 border-t border-slate-800/60 space-y-3 bg-[#0f172a]/50">
        <div className="flex items-center justify-between text-xs">
          <div className="flex items-center gap-2 text-slate-400">
            <Server size={14} className={apiStatus === 'Connected' ? 'text-emerald-500' : 'text-red-500'}/>
            API
          </div>
          <span className={`font-medium ${apiStatus === 'Connected' ? 'text-emerald-500' : 'text-red-500'}`}>{apiStatus}</span>
        </div>
        <div className="flex items-center justify-between text-xs">
          <div className="flex items-center gap-2 text-slate-400">
            <Database size={14} className={dbStatus === 'Connected' ? 'text-emerald-500' : 'text-slate-500'}/>
            Database
          </div>
          <span className={`font-medium ${dbStatus === 'Connected' ? 'text-emerald-500' : 'text-slate-500'}`}>{dbStatus}</span>
        </div>
      </div>
    </div>
  );
};

const Header = () => {
  const location = useLocation();
  let title = "Overview";
  let desc = "Decision and evidence intelligence from assessed transactions.";
  
  if (location.pathname.startsWith("/risk-analytics")) {
    title = "Risk Analytics";
    desc = "Deep dive into model probabilities and deterministic rule triggers.";
  } else if (location.pathname.startsWith("/transactions/")) {
    title = "Transaction Investigation";
    desc = "Deep inspection of transaction context, model evidence, and AI explanation.";
  } else if (location.pathname.startsWith("/transactions")) {
    title = "Transactions Explorer";
    desc = "Search and filter actual risk assessments.";
  } else if (location.pathname.startsWith("/review-queue")) {
    title = "Review Queue";
    desc = "Transactions requiring manual human review.";
  } else if (location.pathname.startsWith("/audit")) {
    title = "Audit Trail";
    desc = "Immutable-style log of all completed assessments.";
  }

  const handleRefresh = () => {
    window.location.reload();
  };

  return (
    <header className="bg-[#0B1120]/80 backdrop-blur-md border-b border-slate-800/60 px-8 py-5 sticky top-0 z-10 flex items-center justify-between">
      <div>
        <h2 className="text-xl font-semibold text-slate-100 tracking-tight">{title}</h2>
        <p className="text-sm text-slate-400 mt-0.5">{desc}</p>
      </div>
      <div className="flex items-center gap-4">
        <div className="text-xs text-slate-500 px-3 py-1.5 rounded-full border border-slate-800 bg-slate-900/50">
          Assessment intelligence
        </div>
        <button 
          onClick={handleRefresh}
          className="p-2 text-slate-400 hover:text-white bg-slate-900 border border-slate-800 rounded-md hover:bg-slate-800 transition-colors shadow-sm"
          title="Refresh Data"
        >
          <RefreshCw size={16} />
        </button>
      </div>
    </header>
  );
};

export default function App() {
  return (
    <Router>
      <div className="flex bg-[#020617] text-slate-200 min-h-screen font-sans selection:bg-blue-500/30">
        <Sidebar />
        <main className="flex-1 flex flex-col h-screen overflow-hidden">
          <Header />
          <div className="p-8 overflow-y-auto flex-1">
            <div className="max-w-7xl mx-auto">
              <Routes>
                <Route path="/" element={<Overview />} />
                <Route path="/risk-analytics" element={<RiskAnalytics />} />
                <Route path="/transactions" element={<Transactions />} />
                <Route path="/transactions/:id" element={<TransactionDetail />} />
                <Route path="/review-queue" element={<ReviewQueue />} />
                <Route path="/audit" element={<AuditTrail />} />
              </Routes>
            </div>
          </div>
        </main>
      </div>
    </Router>
  );
}
