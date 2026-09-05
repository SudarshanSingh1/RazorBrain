/**
 * RazorBrain API Connection Manager
 * 
 * Centralized state machine for tracking backend API connectivity.
 * States: ONLINE | CONNECTING | OFFLINE | DEGRADED
 * 
 * Features:
 * - Exponential backoff polling when offline (5s → 10s → 20s → 30s cap)
 * - Lightweight heartbeat when online (60s interval)
 * - Manual retry always available
 * - Classifies error types (network, timeout, auth, server, readiness)
 */

export type ConnectionStatus = 'ONLINE' | 'CONNECTING' | 'OFFLINE' | 'DEGRADED';

export type ConnectionErrorType = 
  | 'NETWORK_FAILURE'
  | 'TIMEOUT'
  | 'AUTH_ERROR'
  | 'SERVER_ERROR'
  | 'READINESS_FAILURE'
  | 'UNKNOWN'
  | null;

export interface ConnectionState {
  status: ConnectionStatus;
  errorType: ConnectionErrorType;
  errorMessage: string | null;
  lastChecked: Date | null;
  checks: Record<string, string> | null;
}

export interface ConnectionManagerCallbacks {
  onStatusChange: (state: ConnectionState) => void;
}

const BACKOFF_INITIAL_MS = 5000;
const BACKOFF_MAX_MS = 30000;
const HEARTBEAT_INTERVAL_MS = 60000;

export class ConnectionManager {
  private state: ConnectionState;
  private callbacks: ConnectionManagerCallbacks;
  private baseUrl: string;
  private offlineRetryTimer: ReturnType<typeof setTimeout> | null = null;
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null;
  private currentBackoff: number = BACKOFF_INITIAL_MS;
  private destroyed = false;

  constructor(baseUrl: string, callbacks: ConnectionManagerCallbacks) {
    this.baseUrl = baseUrl;
    this.callbacks = callbacks;
    this.state = {
      status: 'CONNECTING',
      errorType: null,
      errorMessage: null,
      lastChecked: null,
      checks: null,
    };
  }

  /** Start initial connection check */
  start(): void {
    this.checkConnection();
  }

  /** Clean up all timers */
  destroy(): void {
    this.destroyed = true;
    this.clearTimers();
  }

  /** Get current state */
  getState(): ConnectionState {
    return { ...this.state };
  }

  /** Manual retry — always available */
  async retryConnection(): Promise<ConnectionState> {
    this.clearTimers();
    this.currentBackoff = BACKOFF_INITIAL_MS;
    return this.checkConnection();
  }

  /** Notify the connection manager that an API request failed */
  notifyRequestFailed(error: unknown): void {
    const errorType = this.classifyError(error);
    if (errorType === 'NETWORK_FAILURE' || errorType === 'TIMEOUT') {
      // Trigger a connection check if we think we're online
      if (this.state.status === 'ONLINE') {
        this.checkConnection();
      }
    }
  }

  /** Core connection check */
  private async checkConnection(): Promise<ConnectionState> {
    if (this.destroyed) return this.state;

    this.updateState({ status: 'CONNECTING', errorType: null, errorMessage: null });

    try {
      // Step 1: Health check (lightweight liveness)
      const healthResponse = await this.fetchWithTimeout(`${this.baseUrl}/health`, 5000);
      
      if (!healthResponse.ok) {
        if (healthResponse.status === 401 || healthResponse.status === 403) {
          return this.goState('OFFLINE', 'AUTH_ERROR', 'Authentication failed. Check API key configuration.');
        }
        return this.goState('OFFLINE', 'SERVER_ERROR', `Health check failed with status ${healthResponse.status}`);
      }

      // Step 2: Readiness check (can serve traffic?)
      const readyResponse = await this.fetchWithTimeout(`${this.baseUrl}/ready`, 5000);
      
      if (readyResponse.ok) {
        const readyData = await readyResponse.json();
        const checks = readyData.checks || null;
        
        if (readyData.status === 'DEGRADED') {
          return this.goState('DEGRADED', 'READINESS_FAILURE', 'Backend is running but some subsystems are degraded.', checks);
        }
        
        return this.goState('ONLINE', null, null, checks);
      } else {
        // Health OK but readiness failed — DEGRADED
        let detail = 'Backend is running but not fully ready to serve traffic.';
        try {
          const errData = await readyResponse.json();
          if (errData.detail && typeof errData.detail === 'object') {
            detail = errData.detail.status || detail;
            return this.goState('DEGRADED', 'READINESS_FAILURE', detail, errData.detail.checks || null);
          } else if (typeof errData.detail === 'string') {
            detail = errData.detail;
          }
        } catch {
          // ignore parse errors
        }
        return this.goState('DEGRADED', 'READINESS_FAILURE', detail);
      }

    } catch (error) {
      const errorType = this.classifyError(error);
      const message = errorType === 'TIMEOUT'
        ? 'Backend API request timed out.'
        : 'Backend API is unreachable.';
      return this.goState('OFFLINE', errorType, message);
    }
  }

  private goState(
    status: ConnectionStatus,
    errorType: ConnectionErrorType,
    errorMessage: string | null,
    checks: Record<string, string> | null = null
  ): ConnectionState {
    this.updateState({
      status,
      errorType,
      errorMessage,
      lastChecked: new Date(),
      checks,
    });

    this.clearTimers();

    if (status === 'ONLINE' || status === 'DEGRADED') {
      // Start heartbeat polling
      this.currentBackoff = BACKOFF_INITIAL_MS;
      this.heartbeatTimer = setInterval(() => {
        this.checkConnection();
      }, HEARTBEAT_INTERVAL_MS);
    } else if (status === 'OFFLINE') {
      // Start exponential backoff retry
      this.scheduleOfflineRetry();
    }

    return this.state;
  }

  private scheduleOfflineRetry(): void {
    if (this.destroyed) return;
    
    this.offlineRetryTimer = setTimeout(() => {
      this.checkConnection();
      // Increase backoff for next retry
      this.currentBackoff = Math.min(this.currentBackoff * 2, BACKOFF_MAX_MS);
    }, this.currentBackoff);
  }

  private clearTimers(): void {
    if (this.offlineRetryTimer) {
      clearTimeout(this.offlineRetryTimer);
      this.offlineRetryTimer = null;
    }
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
  }

  private updateState(partial: Partial<ConnectionState>): void {
    this.state = { ...this.state, ...partial };
    if (!this.destroyed) {
      this.callbacks.onStatusChange(this.getState());
    }
  }

  private classifyError(error: unknown): ConnectionErrorType {
    if (error instanceof TypeError && (error as TypeError).message?.includes('fetch')) {
      return 'NETWORK_FAILURE';
    }
    if (error instanceof DOMException && error.name === 'AbortError') {
      return 'TIMEOUT';
    }
    if (error && typeof error === 'object' && 'name' in error) {
      const e = error as { name: string };
      if (e.name === 'AbortError' || e.name === 'TimeoutError') {
        return 'TIMEOUT';
      }
    }
    return 'NETWORK_FAILURE';
  }

  private async fetchWithTimeout(url: string, timeoutMs: number): Promise<Response> {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
    
    try {
      const response = await fetch(url, {
        signal: controller.signal,
        headers: {
          'Accept': 'application/json',
        },
      });
      return response;
    } finally {
      clearTimeout(timeoutId);
    }
  }
}
