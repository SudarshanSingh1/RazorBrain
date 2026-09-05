import React from 'react';
import { useLocation } from 'react-router-dom';
import { Bell, ChevronDown, Menu } from 'lucide-react';

interface HeaderProps {
  onMenuClick: () => void;
}

export const Header: React.FC<HeaderProps> = ({ onMenuClick }) => {
  const location = useLocation();
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
  }

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
        {/* Connection Status Pill */}
        <div className="hidden md:flex items-center gap-2 px-3 py-1.5 rounded-full border border-border-subtle bg-bg-card text-[12px] font-medium text-text-secondary">
          <span className="w-2 h-2 rounded-full bg-accent-green"></span>
          Live · Connected
        </div>

        
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
