import React, { useState, useEffect } from 'react';
import { getHealth } from '../../services/api';
import { Sidebar } from './Sidebar';
import { Header } from './Header';

export const AppLayout: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [apiStatus, setApiStatus] = useState<string>('Checking...');
  const [dbStatus, setDbStatus] = useState<string>('Checking...');
  const [isMobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    getHealth()
      .then((res) => {
        setApiStatus(res.data.status === 'ok' ? 'Connected' : 'Degraded');
        setDbStatus('Connected');
      })
      .catch(() => {
        setApiStatus('Disconnected');
        setDbStatus('Unknown');
      });
  }, []);

  return (
    <div className="flex bg-bg-main text-text-primary min-h-screen font-sans">
      {/* Background Decorators */}
            <div className="fixed top-0 right-0 w-full h-full pointer-events-none overflow-hidden z-0 flex justify-end">
        <div className="absolute -top-[30%] right-[5%] w-[40%] h-[160%] bg-gradient-to-r from-transparent via-[#0f2e60]/40 to-[#0f2e60]/10 transform -rotate-12 -skew-x-[35deg] blur-2xl"></div>
        <div className="absolute -top-[20%] right-[15%] w-[15%] h-[140%] bg-gradient-to-b from-[#1956e3]/30 to-transparent transform -skew-x-[35deg] blur-3xl"></div>
        <div className="absolute -top-[10%] right-[10%] w-[8%] h-[140%] bg-gradient-to-b from-[#3b9cff]/10 to-transparent transform -skew-x-[35deg] blur-md mix-blend-screen"></div>
        <div className="absolute top-[0%] right-[25%] w-[1px] h-[140%] bg-gradient-to-b from-[#4ea1ff]/30 to-transparent transform -skew-x-[35deg] blur-sm mix-blend-screen"></div>
      </div>
      
      <Sidebar 
        apiStatus={apiStatus} 
        dbStatus={dbStatus} 
        isMobileOpen={isMobileOpen}
        setMobileOpen={setMobileOpen}
      />
      
      <main className="flex-1 flex flex-col min-w-0 min-h-screen z-10 relative">
        <Header onMenuClick={() => setMobileOpen(true)} />
        
        <div className="flex-1 p-4 md:p-6 lg:p-8 overflow-x-hidden">
          <div className="max-w-[1600px] mx-auto w-full">
            {children}
          </div>
        </div>

        {/* Footer */}
        <footer className="mt-auto border-t border-border-subtle py-6 px-8 flex flex-col md:flex-row items-center justify-between text-[13px] text-text-muted gap-4">
          <div className="font-semibold text-text-secondary tracking-tight">
            RazorBrain Console
          </div>
          <div className="text-center">
            Building a safer payments ecosystem with AI
          </div>
          <div className="flex items-center gap-2">
            <div className="w-4 h-4 rounded-sm bg-brand flex items-center justify-center">
              <svg className="w-2.5 h-2.5 text-white" fill="currentColor" viewBox="0 0 24 24"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/></svg>
            </div>
            <span>RazorBrain AI Risk Manager</span>
          </div>
        </footer>
      </main>
    </div>
  );
};
