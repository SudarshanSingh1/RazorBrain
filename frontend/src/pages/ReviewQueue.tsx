import { useEffect, useState } from 'react';
import { getTransactions } from '../api';
import { Link } from 'react-router-dom';
import { ChevronLeft, ChevronRight, Inbox } from 'lucide-react';

export default function ReviewQueue() {
  const [data, setData] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(true);
  const limit = 20;

  useEffect(() => {
    setLoading(true);
    getTransactions({ limit, offset: page * limit, decision: 'REVIEW' })
      .then(res => {
        setData(res.data.data);
        setTotal(res.data.total);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [page]);

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
      
      <div className="bg-[#0f172a] border border-amber-900/30 rounded-xl overflow-hidden shadow-sm flex flex-col h-[calc(100vh-12rem)] shadow-amber-900/5">
        
        <div className="overflow-x-auto flex-1 custom-scrollbar relative">
          <table className="w-full text-left text-sm whitespace-nowrap">
            <thead className="bg-[#0B1120] text-slate-400 uppercase tracking-widest text-[10px] sticky top-0 z-10 shadow-sm border-b border-amber-900/30">
              <tr>
                <th className="px-4 py-3 font-semibold">Timestamp</th>
                <th className="px-4 py-3 font-semibold">Transaction ID</th>
                <th className="px-4 py-3 font-semibold text-right">Amount</th>
                <th className="px-4 py-3 font-semibold">Probability</th>
                <th className="px-4 py-3 font-semibold">Confidence</th>
                <th className="px-4 py-3 font-semibold text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/40">
              {loading ? (
                <tr><td colSpan={6} className="p-12 text-center text-slate-500 animate-pulse">Loading review queue...</td></tr>
              ) : data.length === 0 ? (
                <tr>
                  <td colSpan={6} className="p-20 text-center">
                    <div className="flex flex-col items-center justify-center text-slate-500">
                      <Inbox size={48} className="mb-4 opacity-30" />
                      <h3 className="text-base font-medium text-slate-300">No review cases</h3>
                      <p className="mt-1 text-sm">There are currently no stored REVIEW decisions.</p>
                    </div>
                  </td>
                </tr>
              ) : (
                data.map((row) => (
                  <tr key={row.assessment_id} className="hover:bg-amber-900/10 transition-colors group border-l-2 border-l-amber-500">
                    <td className="px-4 py-3 text-slate-300 text-xs font-mono">{new Date(row.timestamp).toLocaleString()}</td>
                    <td className="px-4 py-3 font-mono text-xs text-slate-500 group-hover:text-slate-300 transition-colors">{row.transaction_id}</td>
                    <td className="px-4 py-3 text-slate-200 text-right font-mono text-xs">${row.amount?.toFixed(2)}</td>
                    <td className="px-4 py-3 text-amber-400 font-mono text-xs font-medium">
                      {row.primary_risk_probability !== null ? row.primary_risk_probability.toFixed(4) : <span className="text-slate-600 italic">Unavailable</span>}
                    </td>
                    <td className="px-4 py-3">{getConfBadge(row.confidence_in_probability)}</td>
                    <td className="px-4 py-3 text-right">
                      <Link to={`/transactions/${row.assessment_id}`} className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-amber-600/20 text-amber-500 hover:bg-amber-600/30 rounded text-xs font-medium transition-colors border border-amber-900/50">
                        Investigate
                      </Link>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        
        {/* Pagination */}
        <div className="p-3 border-t border-amber-900/30 bg-[#0B1120] flex items-center justify-between text-xs">
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
