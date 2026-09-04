import { AlertTriangle, Ban, CheckCircle, Cpu, FileText, Database, Clock, CreditCard } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Cell } from 'recharts';

export default function ServingTransactionDetail({ data }: { data: any }) {
  const {
    assessment_id, transaction_id, amount, customer_id, merchant_id, txn_timestamp,
    model_track, assessment_type, risk, decision, decision_reason,
    feature_snapshot, feature_availability, shap, model_explanation_note, decision_reason_note
  } = data;

  const shapData = shap && shap.features_contributions ? shap.features_contributions.map((fc: any) => ({
    name: fc.feature,
    contribution: fc.contribution
  })) : [];

  return (
    <div className="animate-in fade-in slide-in-from-bottom-4 duration-500">
      <div className="flex flex-col md:flex-row md:items-center justify-between mb-6 gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-white flex items-center gap-3">
            {decision === 'BLOCK' ? <Ban className="text-rose-500" size={28}/> :
             decision === 'REVIEW' ? <AlertTriangle className="text-amber-500" size={28}/> :
             <CheckCircle className="text-emerald-500" size={28}/>}
            Investigation (Serving)
          </h1>
          <p className="text-slate-400 mt-1 flex items-center gap-2 text-sm font-mono">
            {assessment_id}
          </p>
        </div>
        <div className="flex flex-col items-end">
          <div className="text-[10px] text-slate-500 uppercase tracking-widest font-semibold mb-1">Risk Probability</div>
          <div className="text-4xl font-bold tracking-tighter text-white">
            {risk !== undefined && risk !== null ? (risk * 100).toFixed(2) + '%' : 'Unavailable'}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-1 space-y-6">
          <div className="bg-[#0f172a] border border-slate-800/60 p-5 rounded-xl shadow-sm">
            <h2 className="text-sm font-semibold text-slate-200 uppercase tracking-wider mb-4 flex items-center gap-2"><CreditCard size={16}/> Transaction Context</h2>
            <div className="space-y-3 text-sm">
              <div className="flex justify-between border-b border-slate-800/50 pb-2">
                <span className="text-slate-500">Payment ID</span>
                <span className="text-slate-300 font-mono text-xs">{transaction_id}</span>
              </div>
              <div className="flex justify-between border-b border-slate-800/50 pb-2">
                <span className="text-slate-500">Amount</span>
                <span className="text-slate-300 font-medium">{amount !== undefined ? amount : 'Unavailable'}</span>
              </div>
              <div className="flex justify-between border-b border-slate-800/50 pb-2">
                <span className="text-slate-500">Timestamp</span>
                <span className="text-slate-300 flex items-center gap-1.5"><Clock size={14} className="text-slate-500"/> {txn_timestamp || 'Unavailable'}</span>
              </div>
              <div className="flex justify-between border-b border-slate-800/50 pb-2">
                <span className="text-slate-500">Customer</span>
                <span className="text-slate-300 text-xs">{customer_id || 'Unavailable'}</span>
              </div>
              <div className="flex justify-between pb-1">
                <span className="text-slate-500">Merchant</span>
                <span className="text-slate-300 font-mono text-xs">{merchant_id || 'Unavailable'}</span>
              </div>
            </div>
          </div>
          
          <div className="bg-[#0f172a] border border-slate-800/60 p-5 rounded-xl shadow-sm">
            <h2 className="text-sm font-semibold text-slate-200 uppercase tracking-wider mb-4 flex items-center gap-2"><Database size={16}/> Model & Assessment</h2>
            <div className="space-y-3 text-sm">
              <div className="flex justify-between border-b border-slate-800/50 pb-2">
                <span className="text-slate-500">Track</span>
                <span className="text-indigo-400 font-mono text-[10px] bg-indigo-950/30 px-2 py-0.5 rounded">{model_track}</span>
              </div>
              <div className="flex justify-between pb-1">
                <span className="text-slate-500">Type</span>
                <span className="text-slate-300 font-mono text-[10px] bg-slate-800/50 px-2 py-0.5 rounded">{assessment_type}</span>
              </div>
            </div>
          </div>
        </div>

        <div className="lg:col-span-2 space-y-6">
          <div className="bg-[#0f172a] border border-slate-800/60 p-5 rounded-xl shadow-sm">
            <h2 className="text-sm font-semibold text-slate-200 uppercase tracking-wider mb-2 flex items-center gap-2"><FileText size={16}/> Decision Evidence</h2>
            <p className="text-[10px] text-slate-500 italic mb-4">{decision_reason_note}</p>
            <div className="bg-[#020617] p-4 rounded-lg border border-slate-800/60 text-slate-300 text-sm font-mono whitespace-pre-wrap">
              {decision_reason ? JSON.stringify(decision_reason, null, 2) : 'No deterministic decision evidence stored.'}
            </div>
          </div>

          <div className="bg-[#0f172a] border border-slate-800/60 p-5 rounded-xl shadow-sm">
            <h2 className="text-sm font-semibold text-slate-200 uppercase tracking-wider mb-2 flex items-center gap-2"><Cpu size={16}/> Model Evidence (SHAP)</h2>
            <p className="text-[10px] text-slate-500 italic mb-4">{model_explanation_note}</p>
            {shapData.length > 0 ? (
              <div className="h-64 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={shapData} layout="vertical" margin={{ top: 5, right: 30, left: 140, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" horizontal={false} />
                    <XAxis type="number" stroke="#64748b" fontSize={10} tickLine={false} axisLine={false} />
                    <YAxis dataKey="name" type="category" stroke="#94a3b8" fontSize={10} tickLine={false} axisLine={false} />
                    <Tooltip 
                      cursor={{ fill: '#1e293b' }}
                      contentStyle={{ backgroundColor: '#020617', borderColor: '#1e293b', color: '#e2e8f0', borderRadius: '8px' }}
                      formatter={(val: any) => val.toFixed(4)}
                    />
                    <Bar dataKey="contribution" radius={4} barSize={16}>
                      {
                        shapData.map((entry: any, index: number) => (
                          <Cell key={`cell-${index}`} fill={entry.contribution > 0 ? '#f43f5e' : '#10b981'} />
                        ))
                      }
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <div className="py-8 flex items-center justify-center text-slate-500 text-sm italic border border-slate-800 border-dashed rounded-lg">
                Explanation unavailable. (SHAP evidence was not generated for this assessment)
              </div>
            )}
          </div>
          
          <div className="bg-[#0f172a] border border-slate-800/60 p-5 rounded-xl shadow-sm">
            <h2 className="text-sm font-semibold text-slate-200 uppercase tracking-wider mb-4 flex items-center gap-2"><Database size={16}/> Feature Availability</h2>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-y-4 gap-x-2 text-xs">
              {feature_availability && Object.entries(feature_availability).map(([key, available]) => (
                <div key={key}>
                  <p className="text-slate-500 text-[10px] uppercase truncate" title={key}>{key}</p>
                  <p className={`font-medium ${available ? 'text-emerald-400' : 'text-rose-400'}`}>{available ? 'Available' : 'Missing'}</p>
                  <p className="text-slate-400 mt-1 font-mono">{feature_snapshot?.[key] !== undefined ? String(feature_snapshot[key]) : '-'}</p>
                </div>
              ))}
              {(!feature_availability || Object.keys(feature_availability).length === 0) && (
                  <div className="col-span-full py-4 text-center text-slate-500 italic">No feature data recorded.</div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
