import React from 'react';

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'danger' | 'ghost';
  size?: 'sm' | 'md' | 'lg';
  fullWidth?: boolean;
  children: React.ReactNode;
  icon?: React.ReactNode;
}

export const Button: React.FC<ButtonProps> = ({
  variant = 'primary',
  size = 'md',
  fullWidth = false,
  children,
  icon,
  className = '',
  ...props
}) => {
  const baseStyles = 'inline-flex items-center justify-center gap-2 font-medium transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-brand/50 disabled:opacity-50 disabled:cursor-not-allowed';
  
  const sizeStyles = {
    sm: 'text-[12px] px-3 py-1.5 rounded-[6px]',
    md: 'text-[14px] px-4 py-2 rounded-[8px]',
    lg: 'text-[15px] px-6 py-3 rounded-[10px]',
  };

  const variantStyles = {
    primary: 'text-white border border-brand/20 shadow-sm hover:shadow-[0_4px_12px_rgba(47,128,237,0.25)] hover:brightness-110',
    secondary: 'bg-[rgba(20,40,70,0.7)] text-text-primary border border-brand/60 hover:brightness-110 hover:-translate-y-[1px] hover:shadow-md',
    danger: 'bg-accent-red/20 text-accent-red border border-accent-red/50 hover:bg-accent-red/30',
    ghost: 'bg-transparent text-text-secondary hover:bg-bg-card-secondary hover:text-text-primary border border-transparent',
  };

  const primaryBg = variant === 'primary' ? { background: 'linear-gradient(135deg, #2f80ed, #1f67d1)' } : {};

  return (
    <button
      className={`${baseStyles} ${sizeStyles[size]} ${variantStyles[variant]} ${fullWidth ? 'w-full' : ''} ${className}`}
      style={primaryBg}
      {...props}
    >
      {icon && <span className="flex-shrink-0">{icon}</span>}
      {children}
    </button>
  );
};
