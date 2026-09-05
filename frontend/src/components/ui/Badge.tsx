import React from 'react';

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: 'review' | 'highRisk' | 'lowRisk' | 'default' | 'success' | 'warning' | 'danger' | 'secondary';
  children: React.ReactNode;
}

export const Badge: React.FC<BadgeProps> = ({ variant = 'default', children, className = '', ...props }) => {
  const baseStyles = 'inline-flex items-center justify-center px-2 py-0.5 rounded-[4px] text-[10px] font-bold uppercase tracking-wider transition-colors';
  
  const variantStyles = {
    default: 'bg-[rgba(255,255,255,0.05)] text-text-secondary border border-[rgba(255,255,255,0.1)]',
    review: 'bg-accent-yellow/10 text-accent-yellow border border-accent-yellow/20',
    highRisk: 'bg-accent-red/10 text-accent-red border border-accent-red/20',
    lowRisk: 'bg-accent-green/10 text-accent-green border border-accent-green/20',
    success: 'bg-accent-green/10 text-accent-green border border-accent-green/20',
    warning: 'bg-accent-yellow/10 text-accent-yellow border border-accent-yellow/20',
    danger: 'bg-accent-red/10 text-accent-red border border-accent-red/20',
    secondary: 'bg-bg-card-secondary text-text-secondary border border-border-subtle'
  };

  return (
    <span className={`${baseStyles} ${variantStyles[variant]} ${className}`} {...props}>
      {children}
    </span>
  );
};
