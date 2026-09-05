import React from 'react';
import { useLocation } from 'react-router-dom';
import { Bell, ChevronDown, Menu, RefreshCw } from 'lucide-react';
import { useConnectionStatus } from '../../services/ConnectionProvider';

interface HeaderProps {
  onMenuClick: () => void;
}

export const Header: React.FC<HeaderProps> = ({ onMenuClick }) => {
  const location = useLocation();
  const { status, retryConnection, isRetrying } = useConnectionStatus();
  
  let title = "Overview";
  let desc = "Real-time risk intelligence for your Razorpay payments";
  
  if (location.pathname.startsWith("/risk-analytics")) {
    title = "Risk Analytics";
    desc = "Deep dive into model probabilities and deterministic rule triggers.";
  } else if (location.pathname.startsWith("/evaluation")) {
    title = "Evaluation";
    desc = "Ground-truth performance feedback and operational metrics.";
  } else if (location.pathname.startsWith("/razorpay-test")) {
    title = "Razorpay TEST MODE";
    desc = "End-to-end testing integration for Razorpay orders and payments.";
  } else if (location.pathname.startsWith("/transactions/")) {
    title = "Transaction Investigation";
    desc = "Deep inspection of transaction context and model evidence.";
  } else if (location.pathname.startsWith("/transactions")) {
    title = "Transactions Explorer";
    desc = "Search and filter actual risk assessments.";
  } else if (location.pathname.startsWith("/review-queue")) {
    title = "Review Queue";
    desc = "Transactions requiring manual human review.";
  } else if (location.pathname.startsWith("/audit")) {
    title = "Audit Trail";
    desc = "Immutable-style log of all completed assessments.";
  } else if (location.pathname.startsWith("/drift-monitoring")) {
    title = "Drift Monitoring";
    desc = "Monitor data distribution shifts over time.";
  } else if (location.pathname.startsWith("/monitoring")) {
    title = "Monitoring & Alerts";
    desc = "Real-time operational health, alert management, and system metrics.";
  } else if (location.pathname.startsWith("/registry")) {
    title = "Model & Policy Registry";
    desc = "Manage model versions and decision policy configurations.";
  } else if (location.pathname.startsWith("/security")) {
    title = "Security Settings";
    desc = "Manage API access keys and security tokens.";
  } else if (location.pathname.startsWith("/score-transaction")) {
    title = "Score Transaction";
    desc = "Run real-time fraud risk scoring against the inference API.";
  } else if (location.pathname.startsWith("/cases")) {
    title = "Investigations";
    desc = "Manage and resolve flagged transaction investigation cases.";
  }

  // Connection status styling
  const statusConfig = {
    ONLINE: {
      dot: 'bg-accent-green',
      text: 'API Connected',
      textColor: 'text-text-secondary',
    },
    CONNECTING: {
      dot: 'bg-accent-yellow animate-pulse',
      text: 'Connecting...',
      textColor: 'text-accent-yellow',
    },
    OFFLINE: {
      dot: 'bg-accent-red',
      text: 'API Offline',
      textColor: 'text-accent-red',
    },
    DEGRADED: {
      dot: 'bg-accent-yellow',
      text: 'API Degraded',
      textColor: 'text-accent-yellow',
    },
  };

  const cfg = statusConfig[status];
  const isOfflineOrDegraded = status === 'OFFLINE' || status === 'DEGRADED';

  return (
    <header className="sticky top-0 z-20 bg-bg-main/80 backdrop-blur-xl border-b border-border-subtle px-4 md:px-8 py-5 flex items-center justify-between">
      <div className="flex items-center gap-4">
        <button 
          onClick={onMenuClick}
          className="p-2 -ml-2 text-text-muted hover:text-text-primary rounded-lg md:hidden hover:bg-bg-card-secondary"
        >
          <Menu size={20} />
        </button>
        <div>
          <h2 className="text-[24px] md:text-[28px] font-bold text-text-primary tracking-tight leading-none mb-1">
            {title}
          </h2>
          <p className="text-[13px] md:text-[14px] text-text-secondary">
            {desc}
          </p>
        </div>
      </div>

      <div className="flex items-center gap-4 md:gap-6">
        {/* Connection Status Pill — Dynamic */}
        <button
          onClick={isOfflineOrDegraded ? retryConnection : undefined}
          disabled={isRetrying}
          className={`hidden md:flex items-center gap-2 px-3 py-1.5 rounded-full border border-border-subtle bg-bg-card text-[12px] font-medium ${cfg.textColor} transition-all duration-200 ${
            isOfflineOrDegraded ? 'hover:bg-bg-card-secondary cursor-pointer' : 'cursor-default'
          } disabled:opacity-50`}
          title={isOfflineOrDegraded ? 'Click to retry connection' : 'API connection healthy'}
        >
          <span className={`w-2 h-2 rounded-full ${cfg.dot}`}></span>
          {isRetrying ? (
            <>
              <RefreshCw size={10} className="animate-spin" />
              Retrying...
            </>
          ) : (
            cfg.text
          )}
        </button>

        
        {/* Notifications */}
        <button 
          title="Coming soon"
          className="relative p-2 text-text-muted hover:text-text-primary rounded-[10px] border border-[rgba(255,255,255,0.08)] bg-bg-card hover:bg-bg-card-secondary transition-colors cursor-not-allowed"
        >
          <Bell size={16} />
          <span className="absolute top-1.5 right-1.5 w-[7px] h-[7px] bg-accent-red rounded-full"></span>
        </button>

        <div className="w-[1px] h-6 bg-[rgba(255,255,255,0.08)] hidden md:block mx-1"></div>

        {/* User Profile */}
        <div 
          title="Coming soon"
          className="flex items-center gap-2 cursor-not-allowed group opacity-90 hover:opacity-100 transition-opacity"
        >
          <div className="w-[34px] h-[34px] rounded-full bg-[#3b9cff] flex items-center justify-center text-white text-[15px] font-medium shadow-sm">
            R
          </div>
          <div className="hidden md:flex items-center gap-1.5 ml-1">
            <span className="text-[14px] font-medium text-text-primary">
              RazorBrain
            </span>
            <ChevronDown size={14} className="text-text-muted" />
          </div>
        </div>
      </div>

    </header>
  );
};
