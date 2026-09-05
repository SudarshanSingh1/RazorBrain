import React, { createContext, useContext, useEffect, useRef, useState, useCallback } from 'react';
import { ConnectionManager, type ConnectionState, type ConnectionStatus } from './connectionManager';

interface ConnectionContextValue {
  /** Current connection status */
  status: ConnectionStatus;
  /** Full connection state with error details */
  state: ConnectionState;
  /** Trigger a manual connection retry */
  retryConnection: () => Promise<void>;
  /** Whether a retry is currently in progress */
  isRetrying: boolean;
}

const ConnectionContext = createContext<ConnectionContextValue | null>(null);

const API_BASE_URL = import.meta.env.VITE_API_URL || 'https://razorbrain.onrender.com';

export const ConnectionProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [state, setState] = useState<ConnectionState>({
    status: 'CONNECTING',
    errorType: null,
    errorMessage: null,
    lastChecked: null,
    checks: null,
  });
  const [isRetrying, setIsRetrying] = useState(false);
  const managerRef = useRef<ConnectionManager | null>(null);

  useEffect(() => {
    const manager = new ConnectionManager(API_BASE_URL, {
      onStatusChange: (newState) => {
        setState(newState);
      },
    });
    managerRef.current = manager;
    manager.start();

    return () => {
      manager.destroy();
      managerRef.current = null;
    };
  }, []);

  const retryConnection = useCallback(async () => {
    if (!managerRef.current || isRetrying) return;
    setIsRetrying(true);
    try {
      await managerRef.current.retryConnection();
    } finally {
      setIsRetrying(false);
    }
  }, [isRetrying]);

  const value: ConnectionContextValue = {
    status: state.status,
    state,
    retryConnection,
    isRetrying,
  };

  return (
    <ConnectionContext.Provider value={value}>
      {children}
    </ConnectionContext.Provider>
  );
};

/**
 * Hook to access the API connection status from any component.
 * Must be used within a ConnectionProvider.
 */
export function useConnectionStatus(): ConnectionContextValue {
  const context = useContext(ConnectionContext);
  if (!context) {
    throw new Error('useConnectionStatus must be used within a ConnectionProvider');
  }
  return context;
}

/**
 * Get the ConnectionManager instance for use outside React (e.g., axios interceptors).
 * Returns null if not yet initialized.
 */
let _globalManagerRef: ConnectionManager | null = null;

export function getConnectionManager(): ConnectionManager | null {
  return _globalManagerRef;
}

export function setConnectionManager(manager: ConnectionManager | null): void {
  _globalManagerRef = manager;
}
