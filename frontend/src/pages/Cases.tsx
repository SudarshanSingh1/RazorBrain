import { safeFormatDate } from '../utils/date';
import { useState, useEffect, useRef, useCallback } from 'react';
import { Link } from 'react-router-dom';
import {
  Briefcase,
  Search,
  Clock,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  RotateCcw,
  Eye,
  Flame,
  ShieldAlert,
} from 'lucide-react';
import { getCases } from '../services/api';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import type { InvestigationCase, CaseListStats, CaseStatus, CasePriority } from '../types';

export default function Cases() {
  const [cases, setCases] = useState<InvestigationCase[]>([]);
  const [stats, setStats] = useState<CaseListStats>({
    open_cases: 0,
    investigating_cases: 0,
    escalated_cases: 0,
    resolved_cases: 0,
    high_critical_open: 0,
    resolved_today: 0,
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters & Pagination
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [priorityFilter, setPriorityFilter] = useState<string>('');
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalItems, setTotalItems] = useState(0);

  const abortControllerRef = useRef<AbortController | null>(null);

  // Debounce search input
  useEffect(() => {
    const handler = setTimeout(() => {
      setDebouncedSearch(search);
      setPage(1);
    }, 300);
    return () => clearTimeout(handler);
  }, [search]);

  // Fetch cases
  const fetchCases = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    abortControllerRef.current = new AbortController();

    setLoading(true);
    setError(null);

    const params: Record<string, any> = {
      page,
      page_size: 15,
    };
    if (debouncedSearch.trim()) params.search = debouncedSearch.trim();
    if (statusFilter) params.status = statusFilter;
    if (priorityFilter) params.priority = priorityFilter;

    getCases(params, { signal: abortControllerRef.current.signal })
      .then((res) => {
        if (res.data && res.data.success) {
          setCases(res.data.items || []);
          setStats((prev) => res.data.stats || prev);
          setTotalPages(res.data.pagination?.total_pages || 1);
          setTotalItems(res.data.pagination?.total_items || 0);
        }
      })
      .catch((err: any) => {
        if (err.name === 'CanceledError' || err.name === 'AbortError') return;
        setError(err.response?.data?.detail || err.message || 'Failed to load cases');
      })
      .finally(() => {
        setLoading(false);
      });
  }, [page, debouncedSearch, statusFilter, priorityFilter]);

  useEffect(() => {
    fetchCases();
    return () => {
      if (abortControllerRef.current) abortControllerRef.current.abort();
    };
  }, [fetchCases]);

  const resetFilters = () => {
    setSearch('');
    setDebouncedSearch('');
    setStatusFilter('');
    setPriorityFilter('');
    setPage(1);
  };

  const getStatusBadge = (st: CaseStatus) => {
    switch (st) {
      case 'OPEN':
        return (
          <span className="px-2 py-0.5 rounded text-[11px] font-bold bg-blue-500/15 text-blue-400 border border-blue-500/30">
            OPEN
          </span>
        );
      case 'INVESTIGATING':
        return (
          <span className="px-2 py-0.5 rounded text-[11px] font-bold bg-amber-500/15 text-amber-400 border border-amber-500/30">
            INVESTIGATING
          </span>
        );
      case 'ESCALATED':
        return (
          <span className="px-2 py-0.5 rounded text-[11px] font-bold bg-rose-500/15 text-rose-400 border border-rose-500/30 flex items-center gap-1">
            <Flame size={11} /> ESCALATED
          </span>
        );
      case 'RESOLVED':
        return (
          <span className="px-2 py-0.5 rounded text-[11px] font-bold bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 flex items-center gap-1">
            <CheckCircle2 size={11} /> RESOLVED
          </span>
        );
    }
  };

  const getPriorityBadge = (pr: CasePriority) => {
    switch (pr) {
      case 'CRITICAL':
        return (
          <span className="px-2 py-0.5 rounded text-[10.5px] font-extrabold bg-rose-600/20 text-rose-400 border border-rose-500/40">
            CRITICAL
          </span>
        );
      case 'HIGH':
        return (
          <span className="px-2 py-0.5 rounded text-[10.5px] font-bold bg-orange-500/15 text-orange-400 border border-orange-500/30">
            HIGH
          </span>
        );
      case 'MEDIUM':
        return (
          <span className="px-2 py-0.5 rounded text-[10.5px] font-semibold bg-amber-500/10 text-amber-300 border border-amber-500/20">
            MEDIUM
          </span>
        );
      case 'LOW':
        return (
          <span className="px-2 py-0.5 rounded text-[10.5px] font-medium bg-slate-500/10 text-slate-400 border border-slate-500/20">
            LOW
          </span>
        );
    }
  };

  return (
    <div className="space-y-6 max-w-[1600px] mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-2 border-b border-border-subtle/50">
        <div>
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-brand/20 border border-brand/40 flex items-center justify-center text-brand-bright">
              <Briefcase size={18} />
            </div>
            <h1 className="text-2xl font-bold text-text-primary tracking-tight">
              Investigation Cases
            </h1>
          </div>
          <p className="text-[13.5px] text-text-muted mt-1">
            Post-decision transaction lifecycle, operational triage, and immutable audit trail.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={fetchCases}
            disabled={loading}
            className="flex items-center gap-1.5 text-text-muted hover:text-text-primary"
          >
            <RotateCcw size={14} className={loading ? 'animate-spin' : ''} />
            Refresh
          </Button>
        </div>
      </div>

      {/* KPI Stats Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="p-4 rounded-xl bg-bg-card border border-border-subtle/80 flex items-center justify-between">
          <div>
            <span className="text-[11.5px] font-semibold uppercase tracking-wider text-text-muted block">
              Open Cases
            </span>
            <span className="text-2xl font-extrabold text-text-primary mt-1 block">
              {stats.open_cases}
            </span>
            <span className="text-[11px] text-blue-400">Awaiting analyst triage</span>
          </div>
          <div className="w-10 h-10 rounded-lg bg-blue-500/10 border border-blue-500/25 flex items-center justify-center text-blue-400">
            <Clock size={20} />
          </div>
        </div>

        <div className="p-4 rounded-xl bg-bg-card border border-border-subtle/80 flex items-center justify-between">
          <div>
            <span className="text-[11.5px] font-semibold uppercase tracking-wider text-text-muted block">
              High / Critical SLA
            </span>
            <span className="text-2xl font-extrabold text-rose-400 mt-1 block">
              {stats.high_critical_open}
            </span>
            <span className="text-[11px] text-text-muted">Urgent operational focus</span>
          </div>
          <div className="w-10 h-10 rounded-lg bg-rose-500/10 border border-rose-500/25 flex items-center justify-center text-rose-400">
            <ShieldAlert size={20} />
          </div>
        </div>

        <div className="p-4 rounded-xl bg-bg-card border border-border-subtle/80 flex items-center justify-between">
          <div>
            <span className="text-[11.5px] font-semibold uppercase tracking-wider text-text-muted block">
              Escalated Cases
            </span>
            <span className="text-2xl font-extrabold text-amber-400 mt-1 block">
              {stats.escalated_cases}
            </span>
            <span className="text-[11px] text-amber-400/80">Senior review required</span>
          </div>
          <div className="w-10 h-10 rounded-lg bg-amber-500/10 border border-amber-500/25 flex items-center justify-center text-amber-400">
            <Flame size={20} />
          </div>
        </div>

        <div className="p-4 rounded-xl bg-bg-card border border-border-subtle/80 flex items-center justify-between">
          <div>
            <span className="text-[11.5px] font-semibold uppercase tracking-wider text-text-muted block">
              Resolved Today
            </span>
            <span className="text-2xl font-extrabold text-emerald-400 mt-1 block">
              {stats.resolved_today}
            </span>
            <span className="text-[11px] text-text-muted">{stats.resolved_cases} total closed</span>
          </div>
          <div className="w-10 h-10 rounded-lg bg-emerald-500/10 border border-emerald-500/25 flex items-center justify-center text-emerald-400">
            <CheckCircle2 size={20} />
          </div>
        </div>
      </div>

      {/* Filter & Search Toolbar */}
      <Card>
        <div className="p-4 flex flex-col md:flex-row items-center gap-3 justify-between">
          {/* Search Box */}
          <div className="relative w-full md:w-96">
            <Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-text-muted" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search by case ID or transaction ID..."
              className="w-full pl-9 pr-3.5 py-2 rounded-lg bg-bg-main border border-border-subtle text-text-primary text-[13px] focus:outline-none focus:border-brand"
            />
          </div>

          {/* Filter Dropdowns */}
          <div className="flex flex-wrap items-center gap-2.5 w-full md:w-auto">
            <select
              value={statusFilter}
              onChange={(e) => {
                setStatusFilter(e.target.value);
                setPage(1);
              }}
              className="px-3 py-2 rounded-lg bg-bg-main border border-border-subtle text-text-primary text-[13px] focus:outline-none focus:border-brand"
            >
              <option value="">All Statuses</option>
              <option value="OPEN">Open</option>
              <option value="INVESTIGATING">Investigating</option>
              <option value="ESCALATED">Escalated</option>
              <option value="RESOLVED">Resolved</option>
            </select>

            <select
              value={priorityFilter}
              onChange={(e) => {
                setPriorityFilter(e.target.value);
                setPage(1);
              }}
              className="px-3 py-2 rounded-lg bg-bg-main border border-border-subtle text-text-primary text-[13px] focus:outline-none focus:border-brand"
            >
              <option value="">All Priorities</option>
              <option value="CRITICAL">Critical</option>
              <option value="HIGH">High</option>
              <option value="MEDIUM">Medium</option>
              <option value="LOW">Low</option>
            </select>

            {(search || statusFilter || priorityFilter) && (
              <Button variant="ghost" size="sm" onClick={resetFilters} className="text-[12px] text-text-muted hover:text-text-primary">
                Clear Filters
              </Button>
            )}
          </div>
        </div>

        {/* Error Alert */}
        {error && (
          <div className="mx-4 mb-4 p-3 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-300 text-[12.5px] flex items-center justify-between">
            <span>{error}</span>
            <button type="button" onClick={fetchCases} className="underline text-[12px]">Retry</button>
          </div>
        )}

        {/* Cases Table */}
        <div className="overflow-x-auto">
          <table className="w-full text-left text-[13px]">
            <thead className="bg-bg-card-secondary/50 text-[11.5px] uppercase font-semibold text-text-muted border-y border-border-subtle/60">
              <tr>
                <th className="px-4 py-3">Case ID</th>
                <th className="px-4 py-3">Transaction</th>
                <th className="px-4 py-3">Trigger Decision</th>
                <th className="px-4 py-3">Priority</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Assignee</th>
                <th className="px-4 py-3">Created (UTC)</th>
                <th className="px-4 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border-subtle/40">
              {loading && cases.length === 0 ? (
                <tr>
                  <td colSpan={8} className="py-12 text-center text-text-muted">
                    <div className="w-6 h-6 border-2 border-brand/30 border-t-brand rounded-full animate-spin mx-auto mb-2" />
                    Loading cases...
                  </td>
                </tr>
              ) : cases.length === 0 ? (
                <tr>
                  <td colSpan={8} className="py-12 text-center text-text-muted">
                    <Briefcase size={28} className="mx-auto mb-2 opacity-40" />
                    <p className="font-medium text-text-secondary">No investigation cases found</p>
                    <p className="text-[12px] mt-0.5">Try clearing filters or search queries</p>
                  </td>
                </tr>
              ) : (
                cases.map((c) => (
                  <tr key={c.case_id} className="hover:bg-bg-card-secondary/40 transition-colors">
                    <td className="px-4 py-3 font-mono font-medium text-brand-bright">
                      <Link to={`/cases/${c.case_id}`} className="hover:underline">
                        {c.case_id}
                      </Link>
                    </td>
                    <td className="px-4 py-3 font-mono text-text-primary">
                      <Link to={`/transactions/${c.transaction_id}`} className="hover:underline text-text-secondary">
                        {c.transaction_id}
                      </Link>
                    </td>
                    <td className="px-4 py-3">
                      <span className="font-semibold text-text-primary">{c.created_from_decision}</span>
                      <span className="block text-[11px] text-text-muted truncate max-w-[180px]" title={c.created_from_reason}>
                        {c.created_from_reason}
                      </span>
                    </td>
                    <td className="px-4 py-3">{getPriorityBadge(c.priority)}</td>
                    <td className="px-4 py-3">{getStatusBadge(c.status)}</td>
                    <td className="px-4 py-3 text-text-secondary">
                      {c.assigned_to ? (
                        <span className="font-medium">{c.assigned_to}</span>
                      ) : (
                        <span className="text-text-muted italic">Unassigned</span>
                      )}
                    </td>
                    <td className="px-4 py-3 font-mono text-[12px] text-text-muted">
                      {safeFormatDate(c.created_at)}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <Link
                        to={`/cases/${c.case_id}`}
                        className="inline-flex items-center gap-1 px-2.5 py-1 rounded bg-bg-card-secondary hover:bg-brand/20 hover:text-brand-bright text-text-secondary text-[12px] font-medium border border-border-subtle transition-colors"
                      >
                        <Eye size={13} />
                        View
                      </Link>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination Footer */}
        <div className="p-4 border-t border-border-subtle/50 flex flex-col sm:flex-row items-center justify-between gap-3 text-[12.5px] text-text-muted">
          <div>
            Showing <span className="font-semibold text-text-primary">{cases.length}</span> of{' '}
            <span className="font-semibold text-text-primary">{totalItems}</span> cases
          </div>

          <div className="flex items-center gap-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page <= 1 || loading}
              className="flex items-center gap-1"
            >
              <ChevronLeft size={14} /> Previous
            </Button>
            <span className="px-2 font-medium text-text-primary">
              Page {page} of {totalPages}
            </span>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page >= totalPages || loading}
              className="flex items-center gap-1"
            >
              Next <ChevronRight size={14} />
            </Button>
          </div>
        </div>
      </Card>
    </div>
  );
}
