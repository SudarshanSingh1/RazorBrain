import React from 'react';
import { useConnectionStatus } from '../../services/ConnectionProvider';
import { WifiOff, RefreshCw, AlertTriangle } from 'lucide-react';

/**
 * Global connection status banner displayed when the API is offline or degraded.
 * Hidden when the API is online. Shows retry button and auto-recovery feedback.
 */
export const ConnectionStatusBanner: React.FC = () => {
  const { status, state, retryConnection, isRetrying } = useConnectionStatus();

  // Don't show anything when online or initially connecting
  if (status === 'ONLINE') return null;
  if (status === 'CONNECTING' && !state.lastChecked) return null;

  const isOffline = status === 'OFFLINE';
  const isDegraded = status === 'DEGRADED';
  const isConnecting = status === 'CONNECTING';

  const bgColor = isOffline
    ? 'bg-accent-red/10 border-accent-red/30'
    : isDegraded
      ? 'bg-accent-yellow/10 border-accent-yellow/30'
      : 'bg-brand/10 border-brand/30';

  const textColor = isOffline
    ? 'text-accent-red'
    : isDegraded
      ? 'text-accent-yellow'
      : 'text-brand-bright';

  const Icon = isOffline ? WifiOff : isDegraded ? AlertTriangle : RefreshCw;

  const message = isConnecting
    ? 'Attempting to reconnect to the backend API...'
    : isOffline
      ? 'Backend API is currently unavailable. Some RazorBrain features require an active API connection.'
      : 'Backend API is running in a degraded state. Some features may be limited.';

  const detail = state.errorMessage && !isConnecting ? state.errorMessage : null;

  return (
    <div className={`mx-4 md:mx-8 mt-2 px-4 py-3 rounded-[10px] border ${bgColor} flex items-center justify-between gap-4 animate-in fade-in`}>
      <div className="flex items-center gap-3 min-w-0">
        <Icon size={18} className={`${textColor} flex-shrink-0 ${isConnecting ? 'animate-spin' : ''}`} />
        <div className="min-w-0">
          <p className={`text-[13px] font-medium ${textColor}`}>
            {message}
          </p>
          {detail && (
            <p className="text-[11px] text-text-muted mt-0.5 truncate">
              {detail}
            </p>
          )}
        </div>
      </div>

      {!isConnecting && (
        <button
          onClick={retryConnection}
          disabled={isRetrying}
          className={`flex-shrink-0 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-[6px] text-[12px] font-medium
            border transition-all duration-200
            ${isOffline
              ? 'border-accent-red/40 text-accent-red hover:bg-accent-red/10'
              : 'border-accent-yellow/40 text-accent-yellow hover:bg-accent-yellow/10'
            }
            disabled:opacity-50 disabled:cursor-not-allowed`}
        >
          <RefreshCw size={12} className={isRetrying ? 'animate-spin' : ''} />
          {isRetrying ? 'Retrying...' : 'Retry Connection'}
        </button>
      )}
    </div>
  );
};
