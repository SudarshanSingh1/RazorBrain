import React from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Shield, Activity, List, ClipboardCheck, History, BarChart2, TrendingUp, CreditCard, Zap, Briefcase, Bell, Settings, Key } from 'lucide-react';
import { useConnectionStatus } from '../../services/ConnectionProvider';

interface SidebarProps {
  isMobileOpen: boolean;
  setMobileOpen: (isOpen: boolean) => void;
}

const navItems = [
  { name: 'Overview', path: '/', icon: Shield },
  { name: 'Score Transaction', path: '/score-transaction', icon: Zap },
  { name: 'Investigations', path: '/cases', icon: Briefcase },
  { name: 'Transactions', path: '/transactions', icon: List },
  { name: 'Review Queue', path: '/review-queue', icon: ClipboardCheck },
  { name: 'Monitoring', path: '/monitoring', icon: Bell },
  { name: 'Risk Analytics', path: '/risk-analytics', icon: Activity },
  { name: 'Drift Monitoring', path: '/drift-monitoring', icon: TrendingUp },
  { name: 'Evaluation', path: '/evaluation', icon: BarChart2 },
  { name: 'Audit Trail', path: '/audit', icon: History },
  { name: 'Registry', path: '/registry', icon: Settings },
  { name: 'Security', path: '/security', icon: Key },
  { name: 'Razorpay Test', path: '/razorpay-test', icon: CreditCard },
];

export const Sidebar: React.FC<SidebarProps> = ({ isMobileOpen, setMobileOpen }) => {
  const location = useLocation();
  const { status } = useConnectionStatus();

  const statusConfig = {
    ONLINE: { dot: 'bg-accent-green', label: 'Connected' },
    CONNECTING: { dot: 'bg-accent-yellow animate-pulse', label: 'Connecting...' },
    OFFLINE: { dot: 'bg-accent-red', label: 'Disconnected' },
    DEGRADED: { dot: 'bg-accent-yellow', label: 'Degraded' },
  };

  const cfg = statusConfig[status];

  const sidebarClasses = `
    fixed md:sticky top-0 left-0 h-screen w-[260px] shrink-0 bg-bg-sidebar border-r border-[rgba(255,255,255,0.06)]
    flex flex-col z-40 transition-transform duration-300 ease-in-out
    ${isMobileOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'}
  `;

  return (
    <>
      {isMobileOpen && (
        <div 
          className="fixed inset-0 bg-black/60 z-30 md:hidden"
          onClick={() => setMobileOpen(false)}
        />
      )}
      <aside className={sidebarClasses}>
        <div className="px-5 py-5 border-b border-[rgba(255,255,255,0.04)] flex items-center justify-between">
          <img 
            src="/Razorpay-Logo-1.png" 
            alt="Razorpay Logo" 
            className="h-5 w-auto object-contain shrink-0" 
            style={{ filter: "brightness(0) invert(1)" }} 
          />
          <div className="w-[1px] h-6 bg-border-subtle shrink-0 mx-3"></div>
          <div className="flex items-center gap-2 shrink-0">
            <Shield size={16} className="text-brand shrink-0" />
            <h1 className="text-[14px] font-bold text-text-primary tracking-tight leading-none whitespace-nowrap">
              RazorBrain
            </h1>
          </div>
        </div>

        <nav className="flex-1 px-3.5 py-2.5 space-y-1 overflow-y-auto">
          {navItems.map((item) => {
            const Icon = item.icon;
            const active = location.pathname === item.path || (item.path !== '/' && location.pathname.startsWith(item.path));
            
            return (
              <Link
                key={item.name}
                to={item.path}
                onClick={() => setMobileOpen(false)}
                className={`flex items-center gap-3 px-3 py-2 rounded-[10px] transition-all duration-200 text-[13.5px] font-medium group
                  ${active 
                    ? 'bg-gradient-to-r from-[rgba(37,112,230,0.9)] to-[rgba(32,101,210,0.9)] text-white shadow-[0_4px_12px_rgba(37,112,230,0.25)]' 
                    : 'text-text-secondary hover:bg-[rgba(47,128,237,0.08)] hover:text-text-primary'
                  }`}
              >
                <Icon size={17} className={`${active ? 'text-white' : 'text-text-muted group-hover:text-brand-bright'} transition-colors duration-200`} />
                {item.name}
              </Link>
            );
          })}
        </nav>

        <div className="p-3.5 mt-auto">
          <div className="relative border border-border-subtle rounded-[12px] p-4 overflow-hidden bg-bg-card">
            {/* Background graphic from public/squareRP.png */}
            <img 
              src="/squareRP.png" 
              alt="Razorpay Pattern" 
              className="absolute inset-0 w-full h-full object-cover opacity-20 pointer-events-none mix-blend-screen"
            />
            
            <div className="relative z-10">
              <h4 className="text-[13px] font-semibold text-text-primary mb-0.5">RazorBrain</h4>
              <p className="text-[11px] text-text-muted mb-3.5">PaymentsAI</p>
              
              <div className="space-y-2 text-[11px]">
                <div className="flex items-center gap-2 text-text-secondary">
                  <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${cfg.dot}`}></span>
                  API {cfg.label}
                </div>
                <div className="flex items-center gap-2 text-text-secondary">
                  <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${status === 'ONLINE' || status === 'DEGRADED' ? 'bg-accent-green' : 'bg-text-muted'}`}></span>
                  Database {status === 'ONLINE' || status === 'DEGRADED' ? 'Connected' : status === 'CONNECTING' ? 'Checking...' : 'Unknown'}
                </div>
              </div>
              
              <div className="mt-3 pt-2.5 border-t border-border-subtle/50 text-[10px] text-text-muted">
                v1.0.0
              </div>
            </div>
          </div>
        </div>
      </aside>
    </>
  );
};
