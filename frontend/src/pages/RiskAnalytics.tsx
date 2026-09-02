import { useEffect, useState } from 'react';
import { getRiskDistribution, getRuleIntelligence, getProbabilityAmount, getShapIntelligence } from '../api';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, ScatterChart, Scatter, ZAxis } from 'recharts';
import { AlertCircle } from 'lucide-react';

export default function RiskAnalytics() {
  const [distData, setDistData] = useState<any[]>([]);
  const [ruleData, setRuleData] = useState<any[]>([]);
  const [scatterData, setScatterData] = useState<any[]>([]);
  const [shapData, setShapData] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    Promise.all([
      getRiskDistribution(), 
      getRuleIntelligence(), 
      getProbabilityAmount(),
      getShapIntelligence()
    ])
      .then(([distRes, ruleRes, scatterRes, shapRes]) => {
        const dData = distRes.data.labels.map((l: string, i: number) => ({
          name: l,
          count: distRes.data.counts[i]
        }));
        setDistData(dData);
        setRuleData(ruleRes.data);
        setScatterData(scatterRes.data.map((d: any) => ({ x: d.amount, y: d.prob })));
        setShapData(shapRes.data);
        setLoading(false);
      })
      .catch(() => {
        setError(true);
        setLoading(false);
      });
  }, []);

  if (loading) return <div className="text-slate-400 animate-pulse">Loading analytics...</div>;
  if (error) return <div className="text-red-400 border border-red-900 bg-red-950/20 p-4 rounded-md">Unable to load risk analytics.</div>;

  const totalRules = ruleData.reduce((acc, r) => acc + r.count, 0);

  return (
    <div className="space-y-6">
      
      {/* Top row: Prob Dist and SHAP */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-[#0f172a] border border-slate-800/60 p-6 rounded-xl shadow-sm">
          <h2 className="text-base font-semibold text-slate-200">Calibrated Risk Probability</h2>
          <p className="text-xs text-slate-400 mt-1 mb-6">Distribution of stored calibrated model probabilities.</p>
          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={distData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                <XAxis dataKey="name" stroke="#64748b" fontSize={10} tickLine={false} axisLine={false} />
                <YAxis stroke="#64748b" fontSize={10} tickLine={false} axisLine={false} />
                <Tooltip 
                  cursor={{ fill: '#1e293b' }}
                  contentStyle={{ backgroundColor: '#020617', borderColor: '#1e293b', color: '#e2e8f0', borderRadius: '8px' }}
                />
                <Bar dataKey="count" fill="#3b82f6" radius={[2, 2, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <p className="text-[10px] text-slate-500 mt-4 italic">Based on stored calibrated probabilities with non-null values.</p>
        </div>

        <div className="bg-[#0f172a] border border-slate-800/60 p-6 rounded-xl shadow-sm">
          <h2 className="text-base font-semibold text-slate-200">Model Evidence — Top Contributors</h2>
          <p className="text-xs text-slate-400 mt-1 mb-6">Global mean absolute SHAP magnitude per feature.</p>
          <div className="h-64 w-full">
            {shapData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={shapData} layout="vertical" margin={{ top: 5, right: 10, left: 100, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" horizontal={false} />
                  <XAxis type="number" stroke="#64748b" fontSize={10} tickLine={false} axisLine={false} />
                  <YAxis dataKey="feature_name" type="category" stroke="#94a3b8" fontSize={10} tickLine={false} axisLine={false} />
                  <Tooltip 
                    cursor={{ fill: '#1e293b' }}
                    contentStyle={{ backgroundColor: '#020617', borderColor: '#1e293b', color: '#e2e8f0', borderRadius: '8px' }}
                    formatter={(val: any) => val.toFixed(4)}
                  />
                  <Bar dataKey="mean_abs_shap" fill="#8b5cf6" radius={[0, 4, 4, 0]} barSize={12} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full flex items-center justify-center text-slate-500 text-sm">No stored SHAP evidence is available.</div>
            )}
          </div>
          <p className="text-[10px] text-slate-500 mt-4 italic">SHAP values describe model contribution and are not independent risk points.</p>
        </div>
      </div>

      {/* Bottom row: Rule Intel and Scatter */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-[#0f172a] border border-slate-800/60 p-6 rounded-xl shadow-sm">
          <h2 className="text-base font-semibold text-slate-200">Rule Intelligence</h2>
          <p className="text-xs text-slate-400 mt-1 mb-6">Triggered deterministic evidence counts.</p>
          <div className="space-y-3 max-h-72 overflow-y-auto pr-2 custom-scrollbar">
            {ruleData.length === 0 ? (
              <p className="text-slate-500 text-sm py-10 text-center">No rules have triggered.</p>
            ) : (
              ruleData.map((rule, idx) => {
                const pct = totalRules > 0 ? ((rule.count / totalRules) * 100).toFixed(1) : 0;
                return (
                <div key={`${rule.rule_id}-${idx}`} className="flex items-center justify-between p-3 border border-slate-800/60 bg-[#0B1120] rounded-lg group hover:border-slate-600 transition-colors">
                  <div className="flex items-center gap-3">
                    <AlertCircle size={16} className={
                      rule.severity === 'HIGH' ? 'text-rose-500' :
                      rule.severity === 'MEDIUM' ? 'text-amber-500' : 'text-blue-500'
                    } />
                    <div>
                      <p className="text-sm font-medium text-slate-300">{rule.rule_id}</p>
                      <p className="text-[10px] text-slate-500">{pct}% of total triggers</p>
                    </div>
                  </div>
                  <div className="text-right">
                    <p className="text-sm font-semibold text-slate-200">{rule.count.toLocaleString()}</p>
                    <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded-sm uppercase tracking-wider ${
                      rule.severity === 'HIGH' ? 'bg-rose-900/40 text-rose-400' :
                      rule.severity === 'MEDIUM' ? 'bg-amber-900/40 text-amber-400' : 'bg-blue-900/40 text-blue-400'
                    }`}>{rule.severity}</span>
                  </div>
                </div>
              )})
            )}
          </div>
          <p className="text-[10px] text-slate-500 mt-4 italic">Rule counts represent stored triggered rule evidence.</p>
        </div>

        <div className="bg-[#0f172a] border border-slate-800/60 p-6 rounded-xl shadow-sm">
          <h2 className="text-base font-semibold text-slate-200">Observed amount vs calibrated probability</h2>
          <p className="text-xs text-slate-400 mt-1 mb-6">Observed relationship between transaction amount and model probability.</p>
          <p className="text-[10px] text-slate-500 mb-6 italic border border-slate-800/60 p-2 rounded bg-slate-900/50">Bounded analytical sample (max 1000 latest observations).</p>
          <div className="h-72 w-full">
            {scatterData.length > 5 ? (
              <ResponsiveContainer width="100%" height="100%">
                <ScatterChart margin={{ top: 10, right: 10, bottom: 10, left: -20 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                  <XAxis type="number" dataKey="x" name="Amount" unit="$" stroke="#64748b" fontSize={10} tickLine={false} axisLine={false} />
                  <YAxis type="number" dataKey="y" name="Probability" stroke="#64748b" fontSize={10} tickLine={false} axisLine={false} />
                  <ZAxis type="number" range={[15, 15]} />
                  <Tooltip 
                    cursor={{ strokeDasharray: '3 3' }}
                    contentStyle={{ backgroundColor: '#020617', borderColor: '#1e293b', color: '#e2e8f0', borderRadius: '8px' }}
                    formatter={(value: any, name: any) => name === 'Amount' ? `$${value.toFixed(2)}` : value.toFixed(4)}
                  />
                  <Scatter name="Transactions" data={scatterData} fill="#3b82f6" fillOpacity={0.5} />
                </ScatterChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full flex items-center justify-center text-slate-500 text-sm">Insufficient paired observations.</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
