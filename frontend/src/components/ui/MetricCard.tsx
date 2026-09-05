import React from 'react';

export interface MetricCardProps {
  title: string;
  value: string | number;
  icon?: React.ReactNode;
  trend?: string;
  trendDirection?: 'up' | 'down' | 'neutral';
  accentColor: 'blue' | 'green' | 'yellow' | 'red';
  className?: string;
}

const accentMap = {
  blue: {
    bg: 'bg-brand/10',
    text: 'text-brand',
    border: 'border-brand/30',
    glow: 'shadow-[0_0_15px_rgba(47,128,237,0.15)]'
  },
  green: {
    bg: 'bg-accent-green/10',
    text: 'text-accent-green',
    border: 'border-accent-green/30',
    glow: 'shadow-[0_0_15px_rgba(53,211,158,0.15)]'
  },
  yellow: {
    bg: 'bg-accent-yellow/10',
    text: 'text-accent-yellow',
    border: 'border-accent-yellow/30',
    glow: 'shadow-[0_0_15px_rgba(255,181,46,0.15)]'
  },
  red: {
    bg: 'bg-accent-red/10',
    text: 'text-accent-red',
    border: 'border-accent-red/30',
    glow: 'shadow-[0_0_15px_rgba(255,92,112,0.15)]'
  }
};

export const MetricCard: React.FC<MetricCardProps> = ({
  title,
  value,
  icon,
  trend,
  trendDirection = 'neutral',
  accentColor,
  className = ''
}) => {
  const accent = accentMap[accentColor];

  return (
    <div className={`rounded-[14px] p-5 border border-[rgba(100,150,220,0.18)] ${accent.glow} ${className}`}
         style={{ background: 'linear-gradient(135deg, rgba(17,38,65,0.95), rgba(11,26,47,0.95))' }}>
      <div className="flex justify-between items-start mb-4">
        <div className={`p-2.5 rounded-xl ${accent.bg} ${accent.text} ${accent.border} border`}>
          {icon}
        </div>
      </div>
      <div className="space-y-1">
        <h4 className="text-[13px] md:text-[14px] font-medium text-text-secondary">{title}</h4>
        <div className="flex items-baseline justify-between">
          <p className="text-[32px] md:text-[40px] font-bold text-text-primary tracking-tight leading-none">{value}</p>
        </div>
      </div>
      {trend && (
        <div className="mt-3 flex items-center gap-1.5 text-xs text-text-muted">
          {trendDirection === 'up' && <span className="text-accent-green font-medium">↗ {trend}</span>}
          {trendDirection === 'down' && <span className="text-accent-red font-medium">↘ {trend}</span>}
          {trendDirection === 'neutral' && <span className="text-text-muted font-medium">{trend}</span>}
          <span>vs previous period</span>
        </div>
      )}
    </div>
  );
};
