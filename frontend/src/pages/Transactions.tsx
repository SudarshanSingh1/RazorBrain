import { useEffect, useState } from 'react';
import { getTransactions } from '../api';
import { Link } from 'react-router-dom';
import { ShieldCheck, AlertTriangle, Ban, ChevronLeft, ChevronRight, Search } from 'lucide-react';

export default function Transactions() {
  const [data, setData] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const limit = 20;

  useEffect(() => {
    setLoading(true);
    getTransactions({ limit, offset: page * limit, transaction_id: search || undefined })
      .then(res => {
        setData(res.data.data);
        setTotal(res.data.total);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [page, search]);

  const getDecisionBadge = (decision: string) => {
    switch(decision) {
      case 'ALLOW': return <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded border border-emerald-900/50 bg-emerald-950/40 text-emerald-500 text-[10px] font-bold tracking-wider"><ShieldCheck size={12}/> ALLOW</span>;
      case 'REVIEW': return <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded border border-amber-900/50 bg-amber-950/40 text-amber-500 text-[10px] font-bold tracking-wider"><AlertTriangle size={12}/> REVIEW</span>;
      case 'BLOCK': return <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded border border-rose-900/50 bg-rose-950/40 text-rose-500 text-[10px] font-bold tracking-wider"><Ban size={12}/> BLOCK</span>;
      default: return null;
    }
  };

  const getConfBadge = (conf: string) => {
    switch(conf) {
      case 'HIGH': return <span className="px-1.5 py-0.5 rounded bg-blue-900/30 text-blue-400 text-[10px] font-semibold">HIGH</span>;
      case 'MEDIUM': return <span className="px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 text-[10px] font-semibold">MEDIUM</span>;
      case 'LOW': return <span className="px-1.5 py-0.5 rounded bg-amber-900/30 text-amber-400 text-[10px] font-semibold">LOW</span>;
      case 'NONE': return <span className="px-1.5 py-0.5 rounded bg-rose-900/30 text-rose-400 text-[10px] font-semibold">NONE</span>;
      default: return null;
    }
  }

  return (
    <div className="space-y-6">
      
      <div className="bg-[#0f172a] border border-slate-800/60 rounded-xl overflow-hidden shadow-sm flex flex-col h-[calc(100vh-12rem)]">
        
        {/* Toolbar */}
        <div className="p-3 border-b border-slate-800/60 flex items-center justify-between bg-[#0B1120]">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" size={14} />
            <input 
              type="text" 
              placeholder="Search transaction ID..." 
              className="bg-slate-900 border border-slate-700/60 text-slate-200 text-sm rounded-md pl-9 pr-4 py-1.5 focus:outline-none focus:border-blue-500 transition-colors w-64 placeholder:text-slate-600"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && data.length === 1) {
                  window.location.href = `/transactions/${data[0].assessment_id}`;
                }
              }}
            />
          </div>
          <div className="text-xs text-slate-500 flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-emerald-500 inline-block animate-pulse"></span>
            Live Database Connection
          </div>
        </div>

        <div className="overflow-x-auto flex-1 custom-scrollbar relative">
          <table className="w-full text-left text-sm whitespace-nowrap">
            <thead className="bg-[#0B1120] text-slate-400 uppercase tracking-widest text-[10px] sticky top-0 z-10 shadow-sm border-b border-slate-800/60">
              <tr>
                <th className="px-4 py-3 font-semibold">Timestamp</th>
                <th className="px-4 py-3 font-semibold">Transaction ID</th>
                <th className="px-4 py-3 font-semibold text-right">Amount</th>
                <th className="px-4 py-3 font-semibold">Probability</th>
                <th className="px-4 py-3 font-semibold">Confidence</th>
                <th className="px-4 py-3 font-semibold">Decision</th>
                <th className="px-4 py-3 font-semibold">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/40">
              {loading ? (
                <tr><td colSpan={7} className="p-12 text-center text-slate-500 animate-pulse">Fetching records...</td></tr>
              ) : data.length === 0 ? (
                <tr><td colSpan={7} className="p-12 text-center text-slate-500">No transactions found.</td></tr>
              ) : (
                data.map((row) => (
                  <tr key={row.assessment_id} className="hover:bg-slate-800/30 transition-colors group">
                    <td className="px-4 py-2.5 text-slate-300 text-xs font-mono">{new Date(row.timestamp).toLocaleString(undefined, {
                      year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit'
                    })}</td>
                    <td className="px-4 py-2.5 font-mono text-xs"><Link to={`/transactions/${row.assessment_id}`} className="text-blue-500 hover:text-blue-400 hover:underline transition-colors" title="Investigate Assessment">{row.transaction_id}</Link></td>
                    <td className="px-4 py-2.5 text-slate-200 text-right font-mono text-xs">${row.amount?.toFixed(2)}</td>
                    <td className="px-4 py-2.5 text-slate-300 font-mono text-xs">
                      {row.primary_risk_probability !== null ? row.primary_risk_probability.toFixed(4) : <span className="text-slate-600 italic">Unavailable</span>}
                    </td>
                    <td className="px-4 py-2.5">{getConfBadge(row.confidence_in_probability)}</td>
                    <td className="px-4 py-2.5">{getDecisionBadge(row.decision)}</td>
                    <td className="px-4 py-2.5">
                      <Link to={`/transactions/${row.assessment_id}`} className="text-blue-500 hover:text-blue-400 font-medium text-xs px-2 py-1 rounded bg-blue-900/20 hover:bg-blue-900/40 transition-colors">Inspect</Link>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        
        {/* Pagination */}
        <div className="p-3 border-t border-slate-800/60 bg-[#0B1120] flex items-center justify-between text-xs">
          <div className="text-slate-400">
            Showing <span className="font-medium text-slate-200">{data.length > 0 ? page * limit + 1 : 0}</span> to <span className="font-medium text-slate-200">{Math.min((page + 1) * limit, total)}</span> of <span className="font-medium text-slate-200">{total.toLocaleString()}</span> records
          </div>
          <div className="flex gap-1.5">
            <button 
              onClick={() => setPage(p => Math.max(0, p - 1))}
              disabled={page === 0}
              className="p-1.5 border border-slate-700/60 rounded hover:bg-slate-800 disabled:opacity-40 text-slate-300 transition-colors"
            >
              <ChevronLeft size={14}/>
            </button>
            <button 
              onClick={() => setPage(p => p + 1)}
              disabled={(page + 1) * limit >= total}
              className="p-1.5 border border-slate-700/60 rounded hover:bg-slate-800 disabled:opacity-40 text-slate-300 transition-colors"
            >
              <ChevronRight size={14}/>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
