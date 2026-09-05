import { safeFormatDate } from '../utils/date';
import { useEffect, useState } from 'react';
import { getTransactions, getOperationalAnalytics } from '../api';
import { useNavigate } from 'react-router-dom';
import { ChevronLeft, ChevronRight, Inbox, AlertTriangle } from 'lucide-react';
import { Card, DataTable, Badge, Button, LinkText, MetricCard } from '../components/ui';
import type { Column } from '../components/ui';

export default function ReviewQueue() {
  const [data, setData] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(true);
  const limit = 20;
  const [distribution, setDistribution] = useState<any>(null);
  const navigate = useNavigate();

  useEffect(() => {
    getOperationalAnalytics().then(res => setDistribution(res.data.review_workload));
  }, []);

  useEffect(() => {
    let active = true;
    getTransactions({ limit, offset: page * limit, decision: 'REVIEW', unresolved_only: true })
      .then(res => {
        if (!active) return;
        setData(res.data.data);
        setTotal(res.data.total);
        setLoading(false);
      })
      .catch(() => {
        if (!active) return;
        setLoading(false);
      });
    return () => { active = false; };
  }, [page]);

  const columns: Column<any>[] = [
    {
      header: 'Priority',
      cell: (row) => {
        if (!row.priority_tier) return null;
        switch(row.priority_tier) {
          case 'CRITICAL': return <Badge variant="danger">CRITICAL</Badge>;
          case 'HIGH': return <Badge variant="warning">HIGH</Badge>;
          case 'NORMAL': return <Badge variant="default" className="bg-brand/15 text-brand-bright border-brand/30">NORMAL</Badge>;
          default: return null;
        }
      }
    },
    {
      header: 'Timestamp',
      cell: (row) => (
        <span className="font-mono text-text-secondary">
          {safeFormatDate(row.timestamp)}
        </span>
      )
    },
    {
      header: 'Transaction ID',
      cell: (row) => (
        <LinkText onClick={(e: any) => { e.stopPropagation(); navigate(`/transactions/${row.assessment_id}`); }}>
          {row.transaction_id}
        </LinkText>
      )
    },
    {
      header: 'Amount',
      className: 'text-right',
      cell: (row) => (
        <span className="font-mono">${row.amount?.toFixed(2)}</span>
      )
    },
    {
      header: 'Probability',
      cell: (row) => (
        <span className="font-mono font-medium text-accent-yellow">
          {row.primary_risk_probability !== null ? row.primary_risk_probability.toFixed(4) : <span className="italic text-text-muted">Unavailable</span>}
        </span>
      )
    },
    {
      header: 'Confidence',
      cell: (row) => {
        switch(row.confidence_in_probability) {
          case 'HIGH': return <Badge variant="default" className="bg-brand/15 text-brand-bright border-brand/30">HIGH</Badge>;
          case 'MEDIUM': return <Badge variant="default">MEDIUM</Badge>;
          case 'LOW': return <Badge variant="warning">LOW</Badge>;
          case 'NONE': return <Badge variant="danger">NONE</Badge>;
          default: return null;
        }
      }
    },
    {
      header: 'Action',
      className: 'text-right',
      cell: (row) => (
        <Button 
          variant="secondary"
          size="sm"
          className="border-accent-yellow/40 text-accent-yellow hover:bg-accent-yellow/10"
          onClick={(e) => { e.stopPropagation(); navigate(`/transactions/${row.assessment_id}`); }}
        >
          Investigate
        </Button>
      )
    }
  ];

  return (
    <div className="space-y-4 md:space-y-6 animate-in fade-in duration-500 h-[calc(100vh-10rem)] md:h-[calc(100vh-12rem)] flex flex-col">
      
      {distribution && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <MetricCard
            title="Pending Reviews"
            value={distribution.pending.toLocaleString()}
            accentColor="blue"
          />
          <MetricCard
            title="Critical Priority"
            value={distribution.priority_distribution.critical.toLocaleString()}
            accentColor="red"
          />
          <MetricCard
            title="High Priority"
            value={distribution.priority_distribution.high.toLocaleString()}
            accentColor="yellow"
          />
          <MetricCard
            title="Normal Priority"
            value={distribution.priority_distribution.normal.toLocaleString()}
            accentColor="blue"
          />
        </div>
      )}
      
      <Card noPadding className="flex flex-col flex-1 overflow-hidden border-accent-yellow/20 shadow-[0_0_20px_rgba(245,158,11,0.03)]">
        
        <div className="p-4 border-b border-accent-yellow/20 bg-bg-card flex items-center gap-2">
          <AlertTriangle size={16} className="text-accent-yellow" />
          <h3 className="font-semibold text-text-primary">Human Review Required</h3>
        </div>

        <div className="flex-1 overflow-hidden relative">
          <div className="absolute inset-0 overflow-y-auto custom-scrollbar">
            {loading ? (
              <div className="p-12 text-center text-text-muted animate-pulse">Loading review queue...</div>
            ) : data.length === 0 ? (
              <div className="h-full flex flex-col items-center justify-center text-text-muted p-12">
                <Inbox size={48} className="mb-4 opacity-30 text-accent-green" />
                <h3 className="text-[16px] font-semibold text-text-primary">No review cases</h3>
                <p className="mt-1 text-[13px] text-text-secondary">There are currently no stored REVIEW decisions.</p>
              </div>
            ) : (
              <DataTable
                data={data}
                columns={columns}
                keyExtractor={(item) => item.assessment_id}
                onRowClick={(item) => navigate(`/transactions/${item.assessment_id}`)}
                className="border-l-2 border-l-accent-yellow/50"
              />
            )}
          </div>
        </div>
        
        {/* Pagination */}
        <div className="p-3 md:p-4 border-t border-accent-yellow/20 bg-bg-card-secondary flex items-center justify-between text-[13px]">
          <div className="text-text-muted">
            Showing <span className="font-medium text-text-primary">{data.length > 0 ? page * limit + 1 : 0}</span> to <span className="font-medium text-text-primary">{Math.min((page + 1) * limit, total)}</span> of <span className="font-medium text-text-primary">{total.toLocaleString()}</span> records
          </div>
          <div className="flex gap-2">
            <Button 
              variant="secondary"
              size="sm"
              onClick={() => { setLoading(true); setPage(p => Math.max(0, p - 1)); }}
              disabled={page === 0}
            >
              <ChevronLeft size={16}/>
            </Button>
            <Button 
              variant="secondary"
              size="sm"
              onClick={() => { setLoading(true); setPage(p => p + 1); }}
              disabled={(page + 1) * limit >= total}
            >
              <ChevronRight size={16}/>
            </Button>
          </div>
        </div>
      </Card>
    </div>
  );
}
