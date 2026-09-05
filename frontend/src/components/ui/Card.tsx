import React from 'react';

export interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  children: React.ReactNode;
  className?: string;
  noPadding?: boolean;
}

export const Card: React.FC<CardProps> = ({ children, className = '', noPadding = false, ...props }) => {
  return (
    <div
      className={`bg-bg-card border border-border-subtle rounded-[14px] shadow-[0_10px_30px_rgba(0,0,0,0.12)] overflow-hidden transition-all duration-200 hover:border-border-active/30 ${noPadding ? '' : 'p-5 md:p-6'} ${className}`}
      {...props}
    >
      {children}
    </div>
  );
};

export const CardHeader: React.FC<{ children: React.ReactNode; className?: string; action?: React.ReactNode }> = ({ children, className = '', action }) => {
  return (
    <div className={`flex items-center justify-between mb-4 ${className}`}>
      <div className="flex items-center gap-2">
        {children}
      </div>
      {action && <div>{action}</div>}
    </div>
  );
};

export const CardTitle: React.FC<{ children: React.ReactNode; icon?: React.ReactNode; className?: string }> = ({ children, icon, className = '' }) => {
  return (
    <h3 className={`text-[16px] md:text-[18px] font-semibold text-text-primary flex items-center gap-2.5 m-0 tracking-tight ${className}`}>
      {icon && <span className="text-brand flex items-center justify-center p-1.5 bg-bg-card-secondary rounded-lg border border-border-subtle/30">{icon}</span>}
      {children}
    </h3>
  );
};
