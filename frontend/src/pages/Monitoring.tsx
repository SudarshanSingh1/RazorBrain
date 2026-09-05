import { safeFormatDate } from '../utils/date';
import React, { useState, useEffect } from 'react';
import { Card, CardHeader, CardTitle } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { getAlerts, acknowledgeAlert, resolveAlert, getMonitoringSummary, runMonitoringEvaluation } from '../services/api';
import { 
  Shield, Bell, AlertTriangle, CheckCircle2, Clock, 
  Activity, RefreshCw, Filter, Eye, XCircle, Zap 
} from 'lucide-react';

interface FraudActivity {
  transactions_1h: number;
}

interface MonitoringSummary {
  system_health: 'HEALTHY' | 'DEGRADED' | 'CRITICAL' | string;
  open_alert_count: number;
  critical_alert_count: number;
  review_queue_size: number;
  recent_error_rate: number;
  recent_latency_ms: number;
  fraud_activity: FraudActivity;
}

interface Alert {
  id: string;
  severity: 'INFO' | 'WARNING' | 'CRITICAL' | string;
  title: string;
  category: string;
  message: string;
  status: 'OPEN' | 'ACKNOWLEDGED' | 'RESOLVED' | string;
  occurrence_count: number;
  first_detected: string;
  last_detected: string;
  metadata?: Record<string, any>;
  metric_name?: string;
  metric_value?: number;
  threshold?: number;
  entity_type?: string;
  entity_id?: string;
}

export default function Monitoring() {
  const [summary, setSummary] = useState<MonitoringSummary | null>(null);
  const [alertsData, setAlertsData] = useState<{ alerts: Alert[], total: number }>({ alerts: [], total: 0 });
  const [loadingSummary, setLoadingSummary] = useState(true);
  const [loadingAlerts, setLoadingAlerts] = useState(true);
  const [evaluating, setEvaluating] = useState(false);
  const [filters, setFilters] = useState({ status: 'ALL', severity: 'ALL', category: 'ALL' });
  const [selectedAlert, setSelectedAlert] = useState<Alert | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [page, setPage] = useState(1);
  const limit = 10;

  const fetchData = async () => {
    try {
      setLoadingSummary(true);
      const summaryRes = await getMonitoringSummary();
      setSummary(summaryRes.data);
    } catch (err) {
      console.error('Failed to fetch summary', err);
    } finally {
      setLoadingSummary(false);
    }
  };

  const fetchAlerts = async () => {
    try {
      setLoadingAlerts(true);
      const params: any = { page, limit };
      if (filters.status !== 'ALL') params.status = filters.status;
      if (filters.severity !== 'ALL') params.severity = filters.severity;
      if (filters.category !== 'ALL') params.category = filters.category;
      
      const alertsRes = await getAlerts(params);
      setAlertsData(alertsRes.data || { alerts: [], total: 0 });
    } catch (err) {
      console.error('Failed to fetch alerts', err);
      setAlertsData({ alerts: [], total: 0 });
    } finally {
      setLoadingAlerts(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  useEffect(() => {
    fetchAlerts();
  }, [filters, page]);

  useEffect(() => {
    let interval: ReturnType<typeof setInterval>;
    if (autoRefresh) {
      interval = setInterval(() => {
        fetchData();
        fetchAlerts();
      }, 30000);
    }
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [autoRefresh, filters, page]);

  const handleRunEvaluation = async () => {
    setEvaluating(true);
    try {
      await runMonitoringEvaluation();
      await fetchData();
      await fetchAlerts();
    } catch (err) {
      console.error('Failed to run evaluation', err);
    } finally {
      setEvaluating(false);
    }
  };

  const handleAcknowledge = async (id: string, e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    try {
      await acknowledgeAlert(id);
      fetchAlerts();
      if (selectedAlert && selectedAlert.id === id) {
        setSelectedAlert({ ...selectedAlert, status: 'ACKNOWLEDGED' });
      }
    } catch (err) {
      console.error('Failed to acknowledge alert', err);
    }
  };

  const handleResolve = async (id: string, e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    try {
      await resolveAlert(id);
      fetchAlerts();
      if (selectedAlert && selectedAlert.id === id) {
        setSelectedAlert({ ...selectedAlert, status: 'RESOLVED' });
      }
    } catch (err) {
      console.error('Failed to resolve alert', err);
    }
  };

  const formatDate = (dateString: string) => {
    try {
      return safeFormatDate(dateString);
    } catch (e) {
      return dateString;
    }
  };

  const getHealthColor = (health: string) => {
    switch (health) {
      case 'HEALTHY': return 'text-accent-green bg-accent-green/10 border-accent-green/20';
      case 'DEGRADED': return 'text-accent-yellow bg-accent-yellow/10 border-accent-yellow/20';
      case 'CRITICAL': return 'text-accent-red bg-accent-red/10 border-accent-red/20';
      default: return 'text-text-secondary bg-bg-card-secondary border-border-subtle';
    }
  };

  const getSeverityBadge = (severity: string) => {
    switch (severity) {
      case 'CRITICAL': return <Badge className="bg-accent-red/20 text-accent-red border-accent-red/30"><AlertTriangle className="w-3 h-3 mr-1" /> CRITICAL</Badge>;
      case 'WARNING': return <Badge className="bg-accent-yellow/20 text-accent-yellow border-accent-yellow/30"><AlertTriangle className="w-3 h-3 mr-1" /> WARNING</Badge>;
      case 'INFO': return <Badge className="bg-brand/20 text-brand-bright border-brand/30"><Activity className="w-3 h-3 mr-1" /> INFO</Badge>;
      default: return <Badge className="bg-bg-card-secondary text-text-secondary">{severity}</Badge>;
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'OPEN': return <Badge className="bg-accent-red/10 text-accent-red border-accent-red/20">OPEN</Badge>;
      case 'ACKNOWLEDGED': return <Badge className="bg-accent-yellow/10 text-accent-yellow border-accent-yellow/20">ACKNOWLEDGED</Badge>;
      case 'RESOLVED': return <Badge className="bg-accent-green/10 text-accent-green border-accent-green/20">RESOLVED</Badge>;
      default: return <Badge className="bg-bg-card-secondary text-text-secondary">{status}</Badge>;
    }
  };

  return (
    <div className="min-h-screen bg-bg-main text-text-primary p-6 font-sans">
      {/* HEADER SECTION */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center mb-8 gap-4">
        <div>
          <h1 className="text-2xl font-bold text-text-primary flex items-center">
            <Activity className="w-6 h-6 mr-2 text-brand-bright" />
            System Monitoring
          </h1>
          <p className="text-text-muted mt-1 text-sm">Real-time operational health, alerts, and system metrics</p>
        </div>
        <div className="flex items-center space-x-4">
          <label className="flex items-center space-x-2 text-sm text-text-secondary cursor-pointer">
            <input 
              type="checkbox" 
              checked={autoRefresh} 
              onChange={(e) => setAutoRefresh(e.target.checked)}
              className="rounded border-border-subtle bg-bg-card text-brand-bright focus:ring-brand focus:ring-offset-bg-main"
            />
            <span className="flex items-center">
              <RefreshCw className={`w-4 h-4 mr-1 ${autoRefresh ? 'animate-spin-slow text-brand-bright' : ''}`} />
              Auto-refresh (30s)
            </span>
          </label>
          <Button 
            onClick={handleRunEvaluation} 
            disabled={evaluating}
            className="bg-brand hover:bg-brand-bright text-white"
          >
            {evaluating ? (
              <><RefreshCw className="w-4 h-4 mr-2 animate-spin" /> Evaluating...</>
            ) : (
              <><Zap className="w-4 h-4 mr-2" /> Run Evaluation</>
            )}
          </Button>
        </div>
      </div>

      {/* SYSTEM HEALTH OVERVIEW */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <Card className="bg-bg-card border-border-subtle rounded-[14px]">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-text-secondary">System Health</CardTitle>
          </CardHeader>
          <div className="p-6 pt-0">
            {loadingSummary ? (
              <div className="h-8 w-24 bg-bg-card-secondary animate-pulse rounded" />
            ) : (
              <div className={`inline-flex items-center px-3 py-1 rounded-full border ${getHealthColor(summary?.system_health || 'UNKNOWN')} font-bold text-lg`}>
                {summary?.system_health === 'HEALTHY' && <CheckCircle2 className="w-5 h-5 mr-2" />}
                {summary?.system_health === 'DEGRADED' && <AlertTriangle className="w-5 h-5 mr-2" />}
                {summary?.system_health === 'CRITICAL' && <XCircle className="w-5 h-5 mr-2" />}
                {summary?.system_health || 'UNKNOWN'}
              </div>
            )}
          </div>
        </Card>
        
        <Card className="bg-bg-card border-border-subtle rounded-[14px]">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-text-secondary flex justify-between">
              Open Alerts
              <Bell className="w-4 h-4 text-accent-red" />
            </CardTitle>
          </CardHeader>
          <div className="p-6 pt-0">
            {loadingSummary ? (
              <div className="h-8 w-16 bg-bg-card-secondary animate-pulse rounded" />
            ) : (
              <div className="text-3xl font-mono font-bold text-text-primary">
                {summary?.open_alert_count || 0}
              </div>
            )}
          </div>
        </Card>
        
        <Card className="bg-bg-card border-border-subtle rounded-[14px]">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-text-secondary flex justify-between">
              Critical Alerts
              <AlertTriangle className="w-4 h-4 text-accent-red" />
            </CardTitle>
          </CardHeader>
          <div className="p-6 pt-0">
            {loadingSummary ? (
              <div className="h-8 w-16 bg-bg-card-secondary animate-pulse rounded" />
            ) : (
              <div className="text-3xl font-mono font-bold text-accent-red">
                {summary?.critical_alert_count || 0}
              </div>
            )}
          </div>
        </Card>

        <Card className="bg-bg-card border-border-subtle rounded-[14px]">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-text-secondary flex justify-between">
              Review Queue Size
              <Shield className="w-4 h-4 text-brand-bright" />
            </CardTitle>
          </CardHeader>
          <div className="p-6 pt-0">
            {loadingSummary ? (
              <div className="h-8 w-16 bg-bg-card-secondary animate-pulse rounded" />
            ) : (
              <div className="text-3xl font-mono font-bold text-text-primary">
                {summary?.review_queue_size || 0}
              </div>
            )}
          </div>
        </Card>
      </div>

      {/* QUICK METRICS ROW */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
        <Card className="bg-bg-card-secondary border-none rounded-[14px]">
          <div className="p-4 flex items-center justify-between">
            <div className="text-sm text-text-secondary">Error Rate (1h)</div>
            <div className="text-xl font-mono font-bold text-text-primary">
              {loadingSummary ? '--' : `${((summary?.recent_error_rate || 0) * 100).toFixed(2)}%`}
            </div>
          </div>
        </Card>
        <Card className="bg-bg-card-secondary border-none rounded-[14px]">
          <div className="p-4 flex items-center justify-between">
            <div className="text-sm text-text-secondary">Avg Latency</div>
            <div className="text-xl font-mono font-bold text-text-primary flex items-center">
              <Clock className="w-4 h-4 mr-2 text-text-muted" />
              {loadingSummary ? '--' : `${summary?.recent_latency_ms?.toFixed(0) || 0} ms`}
            </div>
          </div>
        </Card>
        <Card className="bg-bg-card-secondary border-none rounded-[14px]">
          <div className="p-4 flex items-center justify-between">
            <div className="text-sm text-text-secondary">Fraud Activity (1h)</div>
            <div className="text-xl font-mono font-bold text-accent-yellow">
              {loadingSummary ? '--' : summary?.fraud_activity?.transactions_1h || 0} txns
            </div>
          </div>
        </Card>
      </div>

      {/* ALERTS LIST SECTION */}
      <div className="mb-4 flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
        <h2 className="text-xl font-bold text-text-primary">Active Alerts</h2>
        
        {/* Filters */}
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center text-sm text-text-muted bg-bg-card-secondary px-3 py-2 rounded-md border border-border-subtle">
            <Filter className="w-4 h-4 mr-2" />
            <select 
              className="bg-transparent text-text-primary focus:outline-none"
              value={filters.status}
              onChange={(e) => setFilters({...filters, status: e.target.value})}
            >
              <option value="ALL">All Status</option>
              <option value="OPEN">Open</option>
              <option value="ACKNOWLEDGED">Acknowledged</option>
              <option value="RESOLVED">Resolved</option>
            </select>
          </div>
          
          <div className="flex items-center text-sm text-text-muted bg-bg-card-secondary px-3 py-2 rounded-md border border-border-subtle">
            <select 
              className="bg-transparent text-text-primary focus:outline-none"
              value={filters.severity}
              onChange={(e) => setFilters({...filters, severity: e.target.value})}
            >
              <option value="ALL">All Severities</option>
              <option value="INFO">Info</option>
              <option value="WARNING">Warning</option>
              <option value="CRITICAL">Critical</option>
            </select>
          </div>
        </div>
      </div>

      {/* Alert Cards */}
      <div className="space-y-4 mb-6">
        {loadingAlerts ? (
          Array.from({ length: 3 }).map((_, i) => (
            <Card key={i} className="bg-bg-card border-border-subtle rounded-[14px] p-6 animate-pulse">
              <div className="h-6 w-1/3 bg-bg-card-secondary rounded mb-4" />
              <div className="h-4 w-2/3 bg-bg-card-secondary rounded" />
            </Card>
          ))
        ) : alertsData.alerts.length === 0 ? (
          <div className="text-center py-12 bg-bg-card border-border-subtle rounded-[14px]">
            <CheckCircle2 className="w-12 h-12 text-accent-green mx-auto mb-4 opacity-50" />
            <h3 className="text-lg font-medium text-text-primary">No alerts found</h3>
            <p className="text-text-muted mt-1">Everything looks good based on your current filters.</p>
          </div>
        ) : (
          alertsData.alerts.map((alert) => (
            <Card 
              key={alert.id} 
              className={`bg-bg-card border-border-subtle rounded-[14px] hover:border-brand/50 transition-colors cursor-pointer ${selectedAlert?.id === alert.id ? 'border-brand' : ''}`}
              onClick={() => setSelectedAlert(selectedAlert?.id === alert.id ? null : alert)}
            >
              <div className="p-5 flex flex-col lg:flex-row gap-4">
                {/* Left Side */}
                <div className="flex-1">
                  <div className="flex items-center gap-3 mb-2">
                    {getSeverityBadge(alert.severity)}
                    <Badge className="bg-bg-card-secondary text-text-secondary font-mono border-border-subtle">{alert.category}</Badge>
                    <span className="text-text-muted font-mono text-xs">#{alert.id.substring(0, 8)}</span>
                  </div>
                  <h3 className="text-lg font-medium text-text-primary mb-1">{alert.title}</h3>
                  <p className="text-text-muted text-sm line-clamp-2">{alert.message}</p>
                </div>
                
                {/* Right Side */}
                <div className="flex flex-col lg:items-end justify-between gap-3 min-w-[200px]">
                  <div className="flex items-center gap-3">
                    <div className="text-right">
                      <div className="text-xs text-text-muted mb-1">Status</div>
                      {getStatusBadge(alert.status)}
                    </div>
                    <div className="text-right">
                      <div className="text-xs text-text-muted mb-1">Occurrences</div>
                      <Badge className="bg-bg-card-secondary text-text-primary font-mono">{alert.occurrence_count}</Badge>
                    </div>
                  </div>
                  
                  <div className="text-xs text-text-muted font-mono flex flex-col lg:items-end gap-1">
                    <div>First: {formatDate(alert.first_detected)}</div>
                    <div>Last: {formatDate(alert.last_detected)}</div>
                  </div>
                  
                  <div className="flex gap-2 mt-2 w-full lg:w-auto">
                    {alert.status === 'OPEN' && (
                      <Button 
                        onClick={(e) => handleAcknowledge(alert.id, e)}
                        className="bg-accent-yellow/20 hover:bg-accent-yellow/30 text-accent-yellow text-xs py-1 px-3 h-8 flex-1 lg:flex-none"
                      >
                        Acknowledge
                      </Button>
                    )}
                    {alert.status !== 'RESOLVED' && (
                      <Button 
                        onClick={(e) => handleResolve(alert.id, e)}
                        className="bg-accent-green/20 hover:bg-accent-green/30 text-accent-green text-xs py-1 px-3 h-8 flex-1 lg:flex-none"
                      >
                        Resolve
                      </Button>
                    )}
                  </div>
                </div>
              </div>
              
              {/* Alert Detail Modal/Dropdown */}
              {selectedAlert?.id === alert.id && (
                <div className="border-t border-border-subtle p-5 bg-bg-card-secondary/50 rounded-b-[14px]">
                  <h4 className="text-sm font-bold text-text-primary mb-4 flex items-center">
                    <Eye className="w-4 h-4 mr-2" />
                    Alert Details
                  </h4>
                  
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                    <div>
                      <div className="text-xs text-text-muted mb-1">Metric Details</div>
                      {alert.metric_name ? (
                        <div className="font-mono text-sm">
                          <div className="text-brand-bright">{alert.metric_name}</div>
                          <div className="mt-1">Value: <span className="text-text-primary">{alert.metric_value}</span></div>
                          <div className="mt-1">Threshold: <span className="text-text-secondary">{alert.threshold}</span></div>
                        </div>
                      ) : (
                        <span className="text-text-secondary text-sm italic">N/A</span>
                      )}
                    </div>
                    
                    <div>
                      <div className="text-xs text-text-muted mb-1">Entity Reference</div>
                      {alert.entity_type ? (
                        <div className="font-mono text-sm">
                          <div>Type: <span className="text-text-primary">{alert.entity_type}</span></div>
                          <div>ID: <span className="text-text-primary">{alert.entity_id}</span></div>
                        </div>
                      ) : (
                        <span className="text-text-secondary text-sm italic">N/A</span>
                      )}
                    </div>
                    
                    <div className="md:col-span-2 lg:col-span-1">
                      <div className="text-xs text-text-muted mb-1">Metadata</div>
                      {alert.metadata && Object.keys(alert.metadata).length > 0 ? (
                        <pre className="bg-bg-main p-2 rounded border border-border-subtle text-xs font-mono text-text-secondary overflow-x-auto">
                          {JSON.stringify(alert.metadata, null, 2)}
                        </pre>
                      ) : (
                        <span className="text-text-secondary text-sm italic">No additional metadata</span>
                      )}
                    </div>
                  </div>
                </div>
              )}
            </Card>
          ))
        )}
      </div>

      {/* Pagination */}
      {!loadingAlerts && alertsData.total > limit && (
        <div className="flex items-center justify-between bg-bg-card p-4 rounded-[14px] border border-border-subtle">
          <div className="text-sm text-text-muted">
            Showing {((page - 1) * limit) + 1} to {Math.min(page * limit, alertsData.total)} of {alertsData.total} alerts
          </div>
          <div className="flex gap-2">
            <Button 
              onClick={() => setPage(p => Math.max(1, p - 1))}
              disabled={page === 1}
              className="bg-bg-card-secondary text-text-primary hover:bg-bg-card border border-border-subtle"
            >
              Previous
            </Button>
            <Button 
              onClick={() => setPage(p => p + 1)}
              disabled={page * limit >= alertsData.total}
              className="bg-bg-card-secondary text-text-primary hover:bg-bg-card border border-border-subtle"
            >
              Next
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
