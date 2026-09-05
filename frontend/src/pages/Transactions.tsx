import { safeFormatDate } from '../utils/date';
import { useEffect, useState } from 'react';
import { getTransactions } from '../api';
import { useNavigate } from 'react-router-dom';
import { ShieldCheck, AlertTriangle, Ban, ChevronLeft, ChevronRight } from 'lucide-react';
import { Card, DataTable, Badge, SearchInput, Button, LinkText } from '../components/ui';
import type { Column } from '../components/ui';

export default function Transactions() {
  const [data, setData] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const limit = 20;
  const navigate = useNavigate();

  useEffect(() => {
    let active = true;
    getTransactions({ limit, offset: page * limit, transaction_id: search || undefined })
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
  }, [page, search]);

  const columns: Column<any>[] = [
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
        <span className="font-mono text-text-secondary">
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
      header: 'Decision',
      cell: (row) => {
        switch(row.decision) {
          case 'ALLOW': return <Badge variant="success"><ShieldCheck size={12} className="mr-1.5"/> ALLOW</Badge>;
          case 'REVIEW': return <Badge variant="warning"><AlertTriangle size={12} className="mr-1.5"/> REVIEW</Badge>;
          case 'BLOCK': return <Badge variant="danger"><Ban size={12} className="mr-1.5"/> BLOCK</Badge>;
          default: return null;
        }
      }
    }
  ];

  return (
    <div className="space-y-4 md:space-y-6 animate-in fade-in duration-500 h-[calc(100vh-10rem)] md:h-[calc(100vh-12rem)] flex flex-col">
      <Card noPadding className="flex flex-col flex-1 overflow-hidden">
        
        {/* Toolbar */}
        <div className="p-3 md:p-4 border-b border-border-subtle flex flex-col sm:flex-row sm:items-center justify-between bg-bg-card gap-3">
          <div className="w-full sm:w-[300px]">
            <SearchInput 
              placeholder="Search transaction ID..." 
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && data.length === 1) {
                  navigate(`/transactions/${data[0].assessment_id}`);
                }
              }}
            />
          </div>
          <div className="text-[12px] text-text-muted flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-accent-green inline-block animate-pulse"></span>
            Live Database Connection
          </div>
        </div>

        <div className="flex-1 overflow-hidden relative">
          <div className="absolute inset-0 overflow-y-auto custom-scrollbar">
            {loading ? (
              <div className="p-12 text-center text-text-muted animate-pulse">Fetching records...</div>
            ) : (
              <DataTable
                data={data}
                columns={columns}
                keyExtractor={(item) => item.assessment_id}
                onRowClick={(item) => navigate(`/transactions/${item.assessment_id}`)}
                emptyMessage="No transactions found."
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
