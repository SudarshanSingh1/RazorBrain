import React from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Shield, Activity, List, ClipboardCheck, History, BarChart2, TrendingUp, CreditCard, Zap, Briefcase } from 'lucide-react';

interface SidebarProps {
  apiStatus: string;
  dbStatus: string;
  isMobileOpen: boolean;
  setMobileOpen: (isOpen: boolean) => void;
}

const navItems = [
  { name: 'Overview', path: '/', icon: Shield },
  { name: 'Score Transaction', path: '/score-transaction', icon: Zap },
  { name: 'Investigations', path: '/cases', icon: Briefcase },
  { name: 'Transactions', path: '/transactions', icon: List },
  { name: 'Review Queue', path: '/review-queue', icon: ClipboardCheck },
  { name: 'Risk Analytics', path: '/risk-analytics', icon: Activity },
  { name: 'Drift Monitoring', path: '/drift-monitoring', icon: TrendingUp },
  { name: 'Evaluation', path: '/evaluation', icon: BarChart2 },
  { name: 'Audit Trail', path: '/audit', icon: History },
  { name: 'Razorpay Test', path: '/razorpay-test', icon: CreditCard },
];

export const Sidebar: React.FC<SidebarProps> = ({ apiStatus, dbStatus, isMobileOpen, setMobileOpen }) => {
  const location = useLocation();

  const sidebarClasses = `
    fixed md:sticky top-0 left-0 h-screen w-[260px] bg-bg-sidebar border-r border-[rgba(255,255,255,0.06)]
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
        <div className="px-5 pt-5 pb-3 flex flex-col gap-3.5 border-b border-[rgba(255,255,255,0.04)]">
          <div className="w-full">
            <img 
              src="/Razorpay-Logo-1.png" 
              alt="Razorpay Logo" 
              className="w-full h-auto max-h-[34px] object-contain object-left block" 
            />
          </div>

          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded bg-brand flex items-center justify-center shrink-0 shadow-sm">
              <Shield size={18} className="text-white" />
            </div>
            <div>
              <h1 className="text-[17px] font-bold text-text-primary leading-tight tracking-tight">
                RazorBrain
              </h1>
              <p className="text-[11px] text-text-secondary leading-tight">AI Risk Manager</p>
            </div>
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
                  <span className={`w-1.5 h-1.5 rounded-full ${apiStatus === 'Connected' ? 'bg-accent-green' : 'bg-accent-red'}`}></span>
                  API {apiStatus}
                </div>
                <div className="flex items-center gap-2 text-text-secondary">
                  <span className={`w-1.5 h-1.5 rounded-full ${dbStatus === 'Connected' ? 'bg-accent-green' : 'bg-text-muted'}`}></span>
                  Database {dbStatus}
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
