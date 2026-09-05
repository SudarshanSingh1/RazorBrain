import { useEffect, useState } from 'react';
import { getTransactions } from '../api';
import { useNavigate } from 'react-router-dom';
import { ChevronLeft, ChevronRight, ShieldCheck, Ban, AlertTriangle } from 'lucide-react';
import { Card, DataTable, Badge, Button, LinkText } from '../components/ui';
import type { Column } from '../components/ui';

export default function AuditTrail() {
  const [data, setData] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(true);
  const limit = 20;
  const navigate = useNavigate();

  useEffect(() => {
    let active = true;
    getTransactions({ limit, offset: page * limit })
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
      header: 'Timestamp (UTC)',
      cell: (row) => (
        <span className="font-mono text-text-secondary">
          {new Date(row.timestamp).toISOString()}
        </span>
      )
    },
    {
      header: 'Assessment ID',
      cell: (row) => (
        <span className="font-mono text-[11px] text-text-muted">
          {row.assessment_id}
        </span>
      )
    },
    {
      header: 'Transaction ID',
      cell: (row) => (
        <span className="font-mono text-[11px] text-text-secondary">
          {row.transaction_id}
        </span>
      )
    },
    {
      header: 'Decision',
      cell: (row) => {
        switch(row.decision) {
          case 'ALLOW': return <span className="text-accent-green font-medium flex items-center gap-1.5"><ShieldCheck size={14}/> ALLOW</span>;
          case 'REVIEW': return <span className="text-accent-yellow font-medium flex items-center gap-1.5"><AlertTriangle size={14}/> REVIEW</span>;
          case 'BLOCK': return <span className="text-accent-red font-medium flex items-center gap-1.5"><Ban size={14}/> BLOCK</span>;
          default: return null;
        }
      }
    },
    {
      header: 'Provider',
      cell: (row) => {
        if (row.provider) {
          return (
            <Badge variant={row.grounded ? 'default' : 'secondary'} className={row.grounded ? 'bg-brand/15 text-brand-bright border-brand/30' : ''}>
              {row.provider} {row.grounded && '(Grounded)'}
            </Badge>
          );
        }
        return <span className="text-text-muted text-[11px] italic">Unavailable</span>;
      }
    },
    {
      header: 'Action',
      className: 'text-right',
      cell: (row) => (
        <LinkText onClick={(e: any) => { e.stopPropagation(); navigate(`/transactions/${row.assessment_id}`); }} className="ml-auto">
          Verify Record
        </LinkText>
      )
    }
  ];

  return (
    <div className="space-y-4 md:space-y-6 animate-in fade-in duration-500 h-[calc(100vh-10rem)] md:h-[calc(100vh-12rem)] flex flex-col">
      <Card noPadding className="flex flex-col flex-1 overflow-hidden">
        
        <div className="p-3 md:p-4 border-b border-border-subtle flex items-center justify-between bg-bg-card">
          <div className="text-[11px] text-text-muted uppercase tracking-widest font-semibold">
            Immutable Audit Logs
          </div>
          <div className="text-[10px] text-text-secondary bg-bg-card-secondary border border-border-subtle px-2 py-1 rounded-[6px]">
            Source: SQLite audit records
          </div>
        </div>

        <div className="flex-1 overflow-hidden relative">
          <div className="absolute inset-0 overflow-y-auto custom-scrollbar">
            {loading ? (
              <div className="p-12 text-center text-text-muted animate-pulse">Loading audit logs...</div>
            ) : (
              <DataTable
                data={data}
                columns={columns}
                keyExtractor={(item) => item.assessment_id}
                onRowClick={(item) => navigate(`/transactions/${item.assessment_id}`)}
                emptyMessage="No audit records found."
              />
            )}
          </div>
        </div>
        
        {/* Pagination */}
        <div className="p-3 md:p-4 border-t border-border-subtle bg-bg-card-secondary flex items-center justify-between text-[13px]">
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
