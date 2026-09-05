import { useEffect, useState, useCallback, useMemo } from 'react';
import { useParams, Link } from 'react-router-dom';
import {
  ArrowLeft,
  Briefcase,
  Clock,
  User,
  CheckCircle2,
  AlertTriangle,
  History,
  FileText,
  Flame,
  ShieldAlert,
  ArrowRight,
  RefreshCw,
  ExternalLink,
  ShieldCheck,
  X,
  AlertCircle
} from 'lucide-react';
import {
  getCaseDetail,
  assignCase,
  investigateCase,
  escalateCase,
  resolveCase,
} from '../services/api';
import { Card, CardHeader, CardTitle } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import type {
  InvestigationCase,
  CaseEvent,
  CaseStatus,
  CasePriority,
  ResolutionType,
} from '../types';

export default function CaseDetail() {
  const { caseId } = useParams<{ caseId: string }>();
  const [caseData, setCaseData] = useState<InvestigationCase | null>(null);
  const [events, setEvents] = useState<CaseEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState(false);

  // Modals / Action states
  const [isAssignOpen, setIsAssignOpen] = useState(false);
  const [assigneeInput, setAssigneeInput] = useState('');

  const [isEscalateOpen, setIsEscalateOpen] = useState(false);
  const [escalationReason, setEscalationReason] = useState('');

  const [isResolveOpen, setIsResolveOpen] = useState(false);
  const [resolutionType, setResolutionType] = useState<ResolutionType>('CONFIRMED_FRAUD');
  const [resolutionNotes, setResolutionNotes] = useState('');

  // Fetch case detail
  const fetchDetail = useCallback(async () => {
    if (!caseId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await getCaseDetail(caseId);
      if (res.data && res.data.success) {
        setCaseData(res.data.case);
        setEvents(res.data.events || []);
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Failed to load case details');
    } finally {
      setLoading(false);
    }
  }, [caseId]);

  useEffect(() => {
    fetchDetail();
  }, [fetchDetail]);

  // SLA calculation
  const sla = useMemo(() => {
    if (!caseData) {
      return {
        targetHours: 24,
        deadline: new Date().toISOString(),
        isBreached: false,
        diffHours: '0.0',
        isResolved: false,
      };
    }
    const slaHoursMap: Record<CasePriority, number> = {
      CRITICAL: 4,
      HIGH: 12,
      MEDIUM: 24,
      LOW: 48,
    };
    const hours = slaHoursMap[caseData.priority] || 24;
    const createdAtTime = new Date(caseData.created_at).getTime();
    const slaDeadlineTime = createdAtTime + hours * 3600 * 1000;
    const nowTime = caseData.resolved_at ? new Date(caseData.resolved_at).getTime() : new Date().getTime();
    const diffMs = slaDeadlineTime - nowTime;
    const diffHours = diffMs / (3600 * 1000);

    return {
      targetHours: hours,
      deadline: new Date(slaDeadlineTime).toISOString(),
      isBreached: diffMs < 0,
      diffHours: Math.abs(diffHours).toFixed(1),
      isResolved: caseData.status === 'RESOLVED',
    };
  }, [caseData]);

  // State Machine Action Handlers
  const handleStartInvestigation = async () => {
    if (!caseData) return;
    setActionLoading(true);
    setActionError(null);
    setActionSuccess(null);
    try {
      await investigateCase(caseData.case_id, {
        expected_version: caseData.version,
        notes: 'Investigation initiated by analyst',
        actor: 'analyst_ui',
      });
      setActionSuccess('Investigation status updated to INVESTIGATING');
      await fetchDetail();
    } catch (err: any) {
      handleActionError(err);
    } finally {
      setActionLoading(false);
    }
  };

  const handleAssign = async () => {
    if (!caseData || !assigneeInput.trim()) return;
    setActionLoading(true);
    setActionError(null);
    setActionSuccess(null);
    try {
      await assignCase(caseData.case_id, {
        assigned_to: assigneeInput.trim(),
        expected_version: caseData.version,
        actor: 'analyst_ui',
      });
      setActionSuccess(`Case successfully assigned to ${assigneeInput.trim()}`);
      setIsAssignOpen(false);
      setAssigneeInput('');
      await fetchDetail();
    } catch (err: any) {
      handleActionError(err);
    } finally {
      setActionLoading(false);
    }
  };

  const handleEscalate = async () => {
    if (!caseData || !escalationReason.trim()) return;
    setActionLoading(true);
    setActionError(null);
    setActionSuccess(null);
    try {
      await escalateCase(caseData.case_id, {
        escalation_reason: escalationReason.trim(),
        expected_version: caseData.version,
        actor: 'analyst_ui',
      });
      setActionSuccess('Case escalated to senior review team');
      setIsEscalateOpen(false);
      setEscalationReason('');
      await fetchDetail();
    } catch (err: any) {
      handleActionError(err);
    } finally {
      setActionLoading(false);
    }
  };

  const handleResolve = async () => {
    if (!caseData) return;
    setActionLoading(true);
    setActionError(null);
    setActionSuccess(null);
    try {
      await resolveCase(caseData.case_id, {
        resolution_type: resolutionType,
        resolution_notes: resolutionNotes.trim(),
        expected_version: caseData.version,
        actor: 'analyst_ui',
      });
      setActionSuccess(`Case marked as RESOLVED (${resolutionType})`);
      setIsResolveOpen(false);
      setResolutionNotes('');
      await fetchDetail();
    } catch (err: any) {
      handleActionError(err);
    } finally {
      setActionLoading(false);
    }
  };

  const handleActionError = (err: any) => {
    if (err.response?.status === 409) {
      setActionError('Concurrency Conflict (409): This case was modified by another session. Refreshed with latest data.');
      fetchDetail();
    } else {
      setActionError(err.response?.data?.detail || err.message || 'Action failed');
    }
  };

  const getStatusBadge = (status: CaseStatus) => {
    switch (status) {
      case 'OPEN':
        return <Badge variant="warning" className="px-2.5 py-0.5 font-semibold text-amber-400 bg-amber-500/10 border-amber-500/30">OPEN</Badge>;
      case 'INVESTIGATING':
        return <Badge variant="default" className="px-2.5 py-0.5 font-semibold text-blue-400 bg-blue-500/10 border-blue-500/30">INVESTIGATING</Badge>;
      case 'ESCALATED':
        return <Badge variant="danger" className="px-2.5 py-0.5 font-semibold text-rose-400 bg-rose-500/10 border-rose-500/30">ESCALATED</Badge>;
      case 'RESOLVED':
        return <Badge variant="success" className="px-2.5 py-0.5 font-semibold text-emerald-400 bg-emerald-500/10 border-emerald-500/30">RESOLVED</Badge>;
      default:
        return <Badge variant="default">{status}</Badge>;
    }
  };

  const getPriorityBadge = (priority: CasePriority) => {
    switch (priority) {
      case 'CRITICAL':
        return <span className="inline-flex items-center gap-1 text-[11px] font-bold text-rose-400 bg-rose-500/15 border border-rose-500/30 px-2 py-0.5 rounded"><Flame size={12} /> CRITICAL</span>;
      case 'HIGH':
        return <span className="inline-flex items-center gap-1 text-[11px] font-bold text-amber-400 bg-amber-500/15 border border-amber-500/30 px-2 py-0.5 rounded"><AlertTriangle size={12} /> HIGH</span>;
      case 'MEDIUM':
        return <span className="inline-flex items-center gap-1 text-[11px] font-bold text-blue-400 bg-blue-500/15 border border-blue-500/30 px-2 py-0.5 rounded">MEDIUM</span>;
      case 'LOW':
        return <span className="inline-flex items-center gap-1 text-[11px] font-bold text-slate-400 bg-slate-500/15 border border-slate-500/30 px-2 py-0.5 rounded">LOW</span>;
      default:
        return <span>{priority}</span>;
    }
  };

  if (loading && !caseData) {
    return (
      <div className="flex h-[calc(100vh-12rem)] items-center justify-center space-x-2">
        <div className="w-4 h-4 bg-brand rounded-full animate-bounce" />
        <div className="w-4 h-4 bg-brand rounded-full animate-bounce delay-75" />
        <div className="w-4 h-4 bg-brand rounded-full animate-bounce delay-150" />
      </div>
    );
  }

  if (error || !caseData) {
    return (
      <div className="max-w-4xl mx-auto mt-8 p-6 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300">
        <h2 className="text-lg font-bold mb-2">Unable to load case details</h2>
        <p className="text-sm mb-4">{error || 'Case not found'}</p>
        <Link to="/cases" className="text-sm underline text-brand-bright">
          &larr; Return to Cases Queue
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-12 animate-in fade-in duration-300">
      {/* Navigation & Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-border-subtle/60 pb-5">
        <div>
          <Link
            to="/cases"
            className="inline-flex items-center gap-2 text-text-muted hover:text-text-primary text-[13px] font-medium mb-2 transition-colors"
          >
            <ArrowLeft size={16} /> Back to Investigation Queue
          </Link>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold font-mono text-text-primary tracking-tight">
              {caseData.case_id}
            </h1>
            {getStatusBadge(caseData.status)}
            {getPriorityBadge(caseData.priority)}
            <span className="text-[11px] font-mono text-text-muted bg-bg-card-secondary px-2 py-0.5 rounded border border-border-subtle">
              v{caseData.version}
            </span>
          </div>
          <p className="text-[12.5px] text-text-muted mt-1">
            Origin: <span className="font-semibold text-text-secondary">{caseData.created_from_decision}</span> &bull; {caseData.created_from_reason}
          </p>
        </div>

        {/* Action Buttons Toolbar */}
        <div className="flex flex-wrap items-center gap-2">
          {caseData.status === 'OPEN' && (
            <Button
              variant="primary"
              size="sm"
              disabled={actionLoading}
              onClick={handleStartInvestigation}
              className="gap-1.5"
            >
              <FileText size={14} /> Start Investigation
            </Button>
          )}

          {caseData.status !== 'RESOLVED' && (
            <Button
              variant="secondary"
              size="sm"
              disabled={actionLoading}
              onClick={() => {
                setAssigneeInput(caseData.assigned_to || '');
                setIsAssignOpen(true);
              }}
              className="gap-1.5"
            >
              <User size={14} /> {caseData.assigned_to ? 'Reassign' : 'Assign'}
            </Button>
          )}

          {caseData.status === 'INVESTIGATING' && (
            <Button
              variant="danger"
              size="sm"
              disabled={actionLoading}
              onClick={() => setIsEscalateOpen(true)}
              className="gap-1.5"
            >
              <AlertTriangle size={14} /> Escalate
            </Button>
          )}

          {caseData.status === 'ESCALATED' && (
            <Button
              variant="primary"
              size="sm"
              disabled={actionLoading}
              onClick={handleStartInvestigation}
              className="gap-1.5"
            >
              <RefreshCw size={14} /> Resume Investigation
            </Button>
          )}

          {caseData.status !== 'RESOLVED' && (
            <Button
              variant="primary"
              size="sm"
              disabled={actionLoading}
              onClick={() => setIsResolveOpen(true)}
              className="gap-1.5 bg-emerald-600 hover:bg-emerald-500 text-white border-emerald-500/30"
            >
              <CheckCircle2 size={14} /> Resolve Case
            </Button>
          )}

          <Button
            variant="ghost"
            size="sm"
            onClick={fetchDetail}
            disabled={actionLoading || loading}
            title="Refresh"
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          </Button>
        </div>
      </div>

      {/* Notifications */}
      {actionError && (
        <div className="p-3.5 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-300 text-[13px] flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertCircle size={16} />
            <span>{actionError}</span>
          </div>
          <button type="button" onClick={() => setActionError(null)} className="text-text-muted hover:text-text-primary">
            <X size={14} />
          </button>
        </div>
      )}

      {actionSuccess && (
        <div className="p-3.5 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-[13px] flex items-center justify-between">
          <div className="flex items-center gap-2">
            <CheckCircle2 size={16} />
            <span>{actionSuccess}</span>
          </div>
          <button type="button" onClick={() => setActionSuccess(null)} className="text-text-muted hover:text-text-primary">
            <X size={14} />
          </button>
        </div>
      )}

      {/* Case Resolution Banner if Resolved */}
      {caseData.status === 'RESOLVED' && (
        <div className="p-4 rounded-xl bg-emerald-500/10 border border-emerald-500/30 flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex items-start gap-3">
            <ShieldCheck size={24} className="text-emerald-400 mt-0.5 shrink-0" />
            <div>
              <div className="flex items-center gap-2">
                <span className="font-bold text-emerald-300 text-[14px]">Case Resolved:</span>
                <span className="font-mono font-semibold px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-200 text-[12px]">
                  {caseData.resolution_type}
                </span>
                <span className="text-[12px] text-emerald-400/80">
                  at {new Date(caseData.resolved_at || '').toUTCString()}
                </span>
              </div>
              {caseData.resolution_notes && (
                <p className="text-[13px] text-emerald-200/90 mt-1">
                  <strong>Analyst Notes:</strong> {caseData.resolution_notes}
                </p>
              )}
            </div>
          </div>
          <div className="text-[11.5px] text-emerald-400/80 bg-emerald-900/20 px-3 py-1.5 rounded border border-emerald-500/20 shrink-0">
            Lifecycle: Completed
          </div>
        </div>
      )}

      {/* Grid: Context & Snapshots */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Col: Case Meta & SLA */}
        <div className="space-y-6">
          {/* Metadata Card */}
          <Card>
            <CardHeader className="pb-3 border-b border-border-subtle/50">
              <CardTitle className="text-[14px] flex items-center gap-2 text-text-primary">
                <Briefcase size={16} className="text-brand" /> Case Information
              </CardTitle>
            </CardHeader>
            <div className="p-4 space-y-3.5 text-[13px]">
              <div className="flex justify-between items-center py-1 border-b border-border-subtle/40">
                <span className="text-text-muted">Transaction ID:</span>
                <Link
                  to={`/transactions/${caseData.transaction_id}`}
                  className="font-mono text-brand-bright hover:underline flex items-center gap-1 font-medium"
                >
                  {caseData.transaction_id} <ExternalLink size={12} />
                </Link>
              </div>

              <div className="flex justify-between items-center py-1 border-b border-border-subtle/40">
                <span className="text-text-muted">Assessment ID:</span>
                <span className="font-mono text-text-secondary text-[12px] truncate max-w-[180px]">
                  {caseData.assessment_id}
                </span>
              </div>

              <div className="flex justify-between items-center py-1 border-b border-border-subtle/40">
                <span className="text-text-muted">Assigned Investigator:</span>
                <span className="font-medium text-text-primary">
                  {caseData.assigned_to || <span className="text-text-muted italic">Unassigned</span>}
                </span>
              </div>

              <div className="flex justify-between items-center py-1 border-b border-border-subtle/40">
                <span className="text-text-muted">Policy Version:</span>
                <span className="font-mono text-text-secondary">{caseData.case_policy_version}</span>
              </div>

              <div className="flex justify-between items-center py-1 border-b border-border-subtle/40">
                <span className="text-text-muted">Created (UTC):</span>
                <span className="text-text-secondary text-[12px]">
                  {new Date(caseData.created_at).toUTCString()}
                </span>
              </div>

              <div className="flex justify-between items-center py-1">
                <span className="text-text-muted">Last Updated:</span>
                <span className="text-text-secondary text-[12px]">
                  {new Date(caseData.updated_at).toUTCString()}
                </span>
              </div>
            </div>
          </Card>

          {/* SLA Tracking Card */}
          <Card>
            <CardHeader className="pb-3 border-b border-border-subtle/50">
              <CardTitle className="text-[14px] flex items-center gap-2 text-text-primary">
                <Clock size={16} className="text-amber-400" /> SLA & Turnaround Target
              </CardTitle>
            </CardHeader>
            <div className="p-4 space-y-3">
              <div className="flex justify-between items-center">
                <span className="text-text-muted text-[13px]">Target Resolution Window:</span>
                <span className="font-semibold text-text-primary text-[13px]">
                  {sla.targetHours} Hours ({caseData.priority})
                </span>
              </div>

              <div className="flex justify-between items-center">
                <span className="text-text-muted text-[13px]">Deadline (UTC):</span>
                <span className="font-mono text-[12px] text-text-secondary">
                  {new Date(sla.deadline).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', month: 'short', day: 'numeric' })}
                </span>
              </div>

              <div className="mt-2 pt-2 border-t border-border-subtle/40">
                {sla.isResolved ? (
                  <div className="flex items-center gap-2 text-emerald-400 text-[12.5px]">
                    <CheckCircle2 size={16} />
                    <span>Resolved within standard lifecycle</span>
                  </div>
                ) : sla.isBreached ? (
                  <div className="p-2.5 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-300 text-[12px] flex items-center gap-2">
                    <AlertTriangle size={16} className="shrink-0 text-rose-400" />
                    <span>SLA Breached by {sla.diffHours} hrs. Urgent review requested.</span>
                  </div>
                ) : (
                  <div className="p-2.5 rounded-lg bg-blue-500/10 border border-blue-500/30 text-blue-300 text-[12px] flex items-center gap-2">
                    <Clock size={16} className="shrink-0 text-blue-400" />
                    <span>{sla.diffHours} hrs remaining to resolution SLA deadline</span>
                  </div>
                )}
              </div>
            </div>
          </Card>

          {/* Operational Feedback Disclaimer Box */}
          <div className="p-4 rounded-xl bg-amber-500/10 border border-amber-500/25 text-amber-200/90 text-[12px] leading-relaxed">
            <div className="flex items-center gap-1.5 font-bold text-amber-300 mb-1">
              <ShieldAlert size={15} /> OPERATIONAL GOVERNANCE NOTICE
            </div>
            Case management outcomes are business records for compliance and operations. Under SentinelML governance, manual case resolutions are strictly partitioned from model training data and do not modify the frozen scoring artifacts.
          </div>
        </div>

        {/* Right Col (2 cols): Immutable Evidence Snapshots & Timeline */}
        <div className="lg:col-span-2 space-y-6">
          {/* Frozen Risk & Decision Snapshots */}
          <Card>
            <CardHeader className="pb-3 border-b border-border-subtle/50">
              <CardTitle className="text-[14px] flex items-center justify-between text-text-primary">
                <span className="flex items-center gap-2">
                  <FileText size={16} className="text-brand" /> Frozen Decision & Risk Evidence
                </span>
                <span className="text-[11px] font-mono text-text-muted">
                  Snapshot taken at scoring time
                </span>
              </CardTitle>
            </CardHeader>
            <div className="p-5 space-y-5">
              {/* Decision Flow Strip */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 p-3 rounded-lg bg-bg-card-secondary/60 border border-border-subtle/40">
                <div>
                  <span className="text-[11px] uppercase tracking-wide text-text-muted font-semibold block">
                    Base Decision
                  </span>
                  <span className="text-[14px] font-bold text-text-primary">
                    {caseData.decision_snapshot?.base_decision || caseData.created_from_decision || 'N/A'}
                  </span>
                </div>
                <div>
                  <span className="text-[11px] uppercase tracking-wide text-text-muted font-semibold block">
                    Final Decision
                  </span>
                  <span className="text-[14px] font-bold text-amber-400">
                    {caseData.decision_snapshot?.final_decision || caseData.created_from_decision || 'N/A'}
                  </span>
                </div>
                <div>
                  <span className="text-[11px] uppercase tracking-wide text-text-muted font-semibold block">
                    Calibrated Prob
                  </span>
                  <span className="text-[14px] font-mono font-bold text-text-primary">
                    {caseData.risk_snapshot?.calibrated_probability !== undefined
                      ? `${(Number(caseData.risk_snapshot.calibrated_probability) * 100).toFixed(2)}%`
                      : 'N/A'}
                  </span>
                </div>
                <div>
                  <span className="text-[11px] uppercase tracking-wide text-text-muted font-semibold block">
                    Model Risk Tier
                  </span>
                  <span className="text-[14px] font-bold text-text-primary">
                    {caseData.risk_snapshot?.model_risk_level || 'N/A'}
                  </span>
                </div>
              </div>

              {/* Trigger Reason */}
              <div>
                <h4 className="text-[12px] font-semibold uppercase tracking-wider text-text-muted mb-1.5">
                  Trigger Reason & Escalation Context
                </h4>
                <div className="p-3 rounded bg-bg-main border border-border-subtle text-[13px] text-text-secondary leading-normal">
                  {caseData.created_from_reason || 'Manual or rule-triggered case creation'}
                </div>
              </div>

              {/* Triggered Rules List from Snapshot */}
              <div>
                <h4 className="text-[12px] font-semibold uppercase tracking-wider text-text-muted mb-2">
                  Triggered Operational Rules ({caseData.rule_snapshot?.triggered_rules?.length || 0})
                </h4>
                {caseData.rule_snapshot?.triggered_rules && caseData.rule_snapshot.triggered_rules.length > 0 ? (
                  <div className="space-y-2">
                    {caseData.rule_snapshot.triggered_rules.map((rule: any, idx: number) => (
                      <div
                        key={idx}
                        className="p-3 rounded-lg bg-bg-main border border-border-subtle/80 flex items-start justify-between gap-4"
                      >
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="font-mono text-xs font-semibold text-brand-bright">
                              {rule.rule_id || rule.id || `Rule #${idx + 1}`}
                            </span>
                            <span className="text-[12px] font-medium text-text-primary">
                              {rule.name || rule.rule_name || ''}
                            </span>
                          </div>
                          {rule.description && (
                            <p className="text-[11.5px] text-text-muted mt-0.5">
                              {rule.description}
                            </p>
                          )}
                        </div>
                        {rule.recommended_action && (
                          <span className="px-2 py-0.5 rounded text-[11px] font-bold bg-amber-500/15 text-amber-300 border border-amber-500/30 uppercase shrink-0">
                            {rule.recommended_action}
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-[12.5px] text-text-muted italic bg-bg-main p-3 rounded border border-border-subtle">
                    No individual deterministic rules triggered. Case opened via model risk policy or manual referral.
                  </p>
                )}
              </div>
            </div>
          </Card>

          {/* Audit Timeline */}
          <Card>
            <CardHeader className="pb-3 border-b border-border-subtle/50">
              <CardTitle className="text-[14px] flex items-center justify-between text-text-primary">
                <span className="flex items-center gap-2">
                  <History size={16} className="text-brand" /> Immutable Case Event Timeline
                </span>
                <span className="text-[11.5px] font-normal text-text-muted">
                  {events.length} audit {events.length === 1 ? 'event' : 'events'}
                </span>
              </CardTitle>
            </CardHeader>
            <div className="p-5">
              {events.length === 0 ? (
                <div className="text-center py-8 text-text-muted text-[13px]">
                  No events recorded for this case.
                </div>
              ) : (
                <div className="relative pl-6 space-y-6 before:absolute before:left-2 before:top-2 before:bottom-2 before:w-0.5 before:bg-border-subtle">
                  {events.map((evt, idx) => (
                    <div key={evt.event_id || idx} className="relative group">
                      {/* Timeline dot */}
                      <div className="absolute -left-[27px] top-1 w-3 h-3 rounded-full bg-brand ring-4 ring-bg-card" />

                      <div className="bg-bg-main/60 p-3.5 rounded-lg border border-border-subtle/60">
                        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1 mb-1">
                          <div className="flex items-center gap-2">
                            <span className="font-semibold text-[13px] text-text-primary font-mono">
                              {evt.event_type}
                            </span>
                            {evt.previous_state && evt.new_state && (
                              <span className="text-[11px] text-text-muted flex items-center gap-1 font-mono">
                                <span>{evt.previous_state}</span>
                                <ArrowRight size={10} />
                                <span className="text-brand-bright font-bold">{evt.new_state}</span>
                              </span>
                            )}
                          </div>
                          <span className="text-[11.5px] text-text-muted">
                            {new Date(evt.created_at).toUTCString()}
                          </span>
                        </div>

                        <div className="text-[12px] text-text-secondary flex items-center gap-2 mt-1">
                          <span className="text-text-muted">Actor:</span>
                          <span className="font-medium text-text-primary">{evt.actor}</span>
                        </div>

                        {evt.metadata && Object.keys(evt.metadata).length > 0 && (
                          <div className="mt-2 text-[11.5px] text-text-muted bg-bg-card p-2 rounded border border-border-subtle/40 overflow-x-auto">
                            {Object.entries(evt.metadata).map(([k, v]) => (
                              <div key={k} className="flex gap-2">
                                <span className="font-medium text-text-secondary">{k}:</span>
                                <span className="font-mono text-text-muted truncate">{String(v)}</span>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </Card>
        </div>
      </div>

      {/* MODAL: Assign Case */}
      {isAssignOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4">
          <div className="bg-bg-card border border-border-subtle rounded-xl max-w-md w-full p-6 shadow-2xl space-y-4">
            <h3 className="text-lg font-bold text-text-primary flex items-center gap-2">
              <User size={18} className="text-brand" /> Assign Investigator
            </h3>
            <p className="text-[13px] text-text-muted">
              Designate a fraud analyst responsible for investigating case <span className="font-mono text-brand-bright">{caseData.case_id}</span>.
            </p>

            <div>
              <label className="block text-[12px] font-semibold text-text-secondary mb-1.5">
                Analyst Name or ID
              </label>
              <input
                type="text"
                value={assigneeInput}
                onChange={(e) => setAssigneeInput(e.target.value)}
                placeholder="e.g. analyst.vikram@razorpay.com"
                className="w-full px-3.5 py-2 rounded-lg bg-bg-main border border-border-subtle text-text-primary text-[13px] focus:outline-none focus:border-brand"
                autoFocus
              />
            </div>

            <div className="flex justify-end gap-2 pt-3 border-t border-border-subtle">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setIsAssignOpen(false)}
                disabled={actionLoading}
              >
                Cancel
              </Button>
              <Button
                variant="primary"
                size="sm"
                onClick={handleAssign}
                disabled={actionLoading || !assigneeInput.trim()}
              >
                {actionLoading ? 'Assigning...' : 'Confirm Assignment'}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* MODAL: Escalate Case */}
      {isEscalateOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4">
          <div className="bg-bg-card border border-border-subtle rounded-xl max-w-md w-full p-6 shadow-2xl space-y-4">
            <h3 className="text-lg font-bold text-rose-400 flex items-center gap-2">
              <AlertTriangle size={18} /> Escalate Investigation
            </h3>
            <p className="text-[13px] text-text-muted">
              Escalate this case to Tier-2 / Senior Risk Review. Provide justification below.
            </p>

            <div>
              <label className="block text-[12px] font-semibold text-text-secondary mb-1.5">
                Escalation Reason *
              </label>
              <textarea
                rows={3}
                value={escalationReason}
                onChange={(e) => setEscalationReason(e.target.value)}
                placeholder="e.g. Velocity surge across multiple accounts with high transaction value requiring fraud lead review."
                className="w-full px-3.5 py-2 rounded-lg bg-bg-main border border-border-subtle text-text-primary text-[13px] focus:outline-none focus:border-brand resize-none"
                autoFocus
              />
            </div>

            <div className="flex justify-end gap-2 pt-3 border-t border-border-subtle">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setIsEscalateOpen(false)}
                disabled={actionLoading}
              >
                Cancel
              </Button>
              <Button
                variant="danger"
                size="sm"
                onClick={handleEscalate}
                disabled={actionLoading || !escalationReason.trim()}
              >
                {actionLoading ? 'Escalating...' : 'Confirm Escalation'}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* MODAL: Resolve Case */}
      {isResolveOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4">
          <div className="bg-bg-card border border-border-subtle rounded-xl max-w-lg w-full p-6 shadow-2xl space-y-4">
            <h3 className="text-lg font-bold text-text-primary flex items-center gap-2">
              <CheckCircle2 size={18} className="text-emerald-400" /> Complete Case Resolution
            </h3>

            {/* Governance Disclaimer */}
            <div className="p-3 rounded-lg bg-amber-500/10 border border-amber-500/25 text-amber-200 text-[12px] leading-relaxed">
              <strong>Notice:</strong> This operational outcome is logged in the audit trail. It does not alter or retrain the serving ML model.
            </div>

            <div>
              <label className="block text-[12px] font-semibold text-text-secondary mb-1.5">
                Resolution Outcome *
              </label>
              <select
                value={resolutionType}
                onChange={(e) => setResolutionType(e.target.value as ResolutionType)}
                className="w-full px-3.5 py-2 rounded-lg bg-bg-main border border-border-subtle text-text-primary text-[13px] focus:outline-none focus:border-brand"
              >
                <option value="CONFIRMED_FRAUD">CONFIRMED_FRAUD — Fraud confirmed by analyst investigation</option>
                <option value="CONFIRMED_LEGITIMATE">CONFIRMED_LEGITIMATE — Verified genuine customer payment</option>
                <option value="INCONCLUSIVE">INCONCLUSIVE — Insufficient customer/issuer evidence</option>
                <option value="DUPLICATE">DUPLICATE — Duplicate investigation case</option>
                <option value="OTHER">OTHER — Administrative or other resolution</option>
              </select>
            </div>

            <div>
              <label className="block text-[12px] font-semibold text-text-secondary mb-1.5">
                Investigator Notes
              </label>
              <textarea
                rows={3}
                value={resolutionNotes}
                onChange={(e) => setResolutionNotes(e.target.value)}
                placeholder="Detail the investigative evidence (e.g. verified OTP with user, cardholder confirmed stolen device)."
                className="w-full px-3.5 py-2 rounded-lg bg-bg-main border border-border-subtle text-text-primary text-[13px] focus:outline-none focus:border-brand resize-none"
              />
            </div>

            <div className="flex justify-end gap-2 pt-3 border-t border-border-subtle">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setIsResolveOpen(false)}
                disabled={actionLoading}
              >
                Cancel
              </Button>
              <Button
                variant="primary"
                size="sm"
                onClick={handleResolve}
                disabled={actionLoading}
                className="bg-emerald-600 hover:bg-emerald-500 text-white border-emerald-500/30"
              >
                {actionLoading ? 'Resolving...' : 'Submit Resolution'}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
