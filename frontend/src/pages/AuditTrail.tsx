import { useEffect, useState } from 'react';
import { getTransactions } from '../api';
import { Link } from 'react-router-dom';
import { ChevronLeft, ChevronRight,  } from 'lucide-react';

export default function AuditTrail() {
  const [data, setData] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(true);
  const limit = 20;

  useEffect(() => {
    setLoading(true);
    getTransactions({ limit, offset: page * limit })
      .then(res => {
        setData(res.data.data);
        setTotal(res.data.total);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [page]);

  const getDecisionText = (decision: string) => {
    switch(decision) {
      case 'ALLOW': return <span className="text-emerald-500 font-medium">ALLOW</span>;
      case 'REVIEW': return <span className="text-amber-500 font-medium">REVIEW</span>;
      case 'BLOCK': return <span className="text-rose-500 font-medium">BLOCK</span>;
      default: return null;
    }
  };

  return (
    <div className="space-y-6">
      
      <div className="bg-[#0f172a] border border-slate-800/60 rounded-xl overflow-hidden shadow-sm flex flex-col h-[calc(100vh-12rem)]">
        
        <div className="p-3 border-b border-slate-800/60 flex items-center justify-between bg-[#0B1120]">
          <div className="text-xs text-slate-500 px-2 uppercase tracking-widest font-semibold">
            Immutable Audit Logs
          </div>
          <div className="text-[10px] text-slate-500 bg-slate-900 border border-slate-800 px-2 py-1 rounded">
            Source: SQLite audit records
          </div>
        </div>

        <div className="overflow-x-auto flex-1 custom-scrollbar relative">
          <table className="w-full text-left text-sm whitespace-nowrap">
            <thead className="bg-[#0B1120] text-slate-400 uppercase tracking-widest text-[10px] sticky top-0 z-10 shadow-sm border-b border-slate-800/60">
              <tr>
                <th className="px-4 py-3 font-semibold">Timestamp</th>
                <th className="px-4 py-3 font-semibold">Assessment ID</th>
                <th className="px-4 py-3 font-semibold">Txn ID</th>
                <th className="px-4 py-3 font-semibold">Decision</th>
                <th className="px-4 py-3 font-semibold">Provider</th>
                <th className="px-4 py-3 font-semibold">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/40">
              {loading ? (
                <tr><td colSpan={6} className="p-12 text-center text-slate-500 animate-pulse">Loading audit logs...</td></tr>
              ) : data.length === 0 ? (
                <tr><td colSpan={6} className="p-12 text-center text-slate-500">No audit records found.</td></tr>
              ) : (
                data.map((row) => (
                  <tr key={row.assessment_id} className="hover:bg-slate-800/30 transition-colors">
                    <td className="px-4 py-2.5 text-slate-400 text-xs font-mono">{new Date(row.timestamp).toISOString()}</td>
                    <td className="px-4 py-2.5 font-mono text-[10px] text-slate-500">{row.assessment_id}</td>
                    <td className="px-4 py-2.5 font-mono text-[10px] text-slate-400">{row.transaction_id}</td>
                    <td className="px-4 py-2.5 text-xs">{getDecisionText(row.decision)}</td>
                    <td className="px-4 py-2.5">
                      {row.provider ? (
                        <span className={`inline-flex px-1.5 py-0.5 rounded text-[9px] uppercase font-bold tracking-wider ${row.grounded ? 'bg-indigo-900/40 text-indigo-400 border border-indigo-800/50' : 'bg-slate-800 text-slate-400'}`}>
                          {row.provider} {row.grounded && '(Grounded)'}
                        </span>
                      ) : <span className="text-slate-600 text-[10px] italic">Unavailable</span>}
                    </td>
                    <td className="px-4 py-2.5">
                      <Link to={`/transactions/${row.assessment_id}`} className="text-blue-500 hover:text-blue-400 font-medium text-xs">Verify</Link>
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
