import { useEffect, useState } from 'react';
import { getSummary, getTrends } from '../api';
import { ShieldCheck, AlertTriangle, Ban, Database, Activity, TrendingUp } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend } from 'recharts';

export default function Overview() {
  const [data, setData] = useState<any>(null);
  const [trends, setTrends] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    Promise.all([getSummary(), getTrends()])
      .then(([sumRes, trendRes]) => {
        setData(sumRes.data);
        setTrends(trendRes.data);
        setLoading(false);
      })
      .catch(() => {
        setError(true);
        setLoading(false);
      });
  }, []);

  if (loading) return <div className="text-slate-400 animate-pulse">Loading intelligence...</div>;
  if (error) return <div className="text-red-400 border border-red-900 bg-red-950/20 p-4 rounded-md">Unable to load risk intelligence.</div>;
  if (!data || data.total_assessments === 0) return (
    <div className="flex flex-col items-center justify-center py-20 text-slate-500">
      <Database size={48} className="mb-4 opacity-50" />
      <h3 className="text-lg font-medium text-slate-300">No assessments yet</h3>
      <p className="mt-2 text-sm">Run a transaction assessment to populate this workspace.</p>
    </div>
  );

  const total = data.total_assessments;
  const allow = data.decisions?.ALLOW || 0;
  const review = data.decisions?.REVIEW || 0;
  const block = data.decisions?.BLOCK || 0;
  
  const highConf = data.confidence?.HIGH || 0;
  const medConf = data.confidence?.MEDIUM || 0;
  const lowConf = data.confidence?.LOW || 0;
  const noneConf = data.confidence?.NONE || 0;
  
  const fullEv = highConf;
  const partEv = medConf;
  const limitEv = lowConf;
  const unavailEv = noneConf;

  return (
    <div className="space-y-8">
      {/* KPI Row */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-[#0f172a] border border-slate-800/60 p-5 rounded-xl shadow-sm hover:border-slate-700 transition-colors">
          <div className="flex items-center gap-3 mb-3">
            <div className="p-2 bg-blue-900/30 rounded-lg"><Activity size={16} className="text-blue-400" /></div>
            <p className="text-xs font-medium text-slate-400 uppercase tracking-wider">Total Assessments</p>
          </div>
          <p className="text-3xl font-semibold text-slate-100">{total.toLocaleString()}</p>
        </div>
        
        <div className="bg-[#0f172a] border border-slate-800/60 p-5 rounded-xl shadow-sm hover:border-slate-700 transition-colors">
          <div className="flex items-center gap-3 mb-3">
            <div className="p-2 bg-emerald-900/30 rounded-lg"><ShieldCheck size={16} className="text-emerald-500" /></div>
            <p className="text-xs font-medium text-slate-400 uppercase tracking-wider">Allow</p>
          </div>
          <div className="flex items-end gap-3">
            <p className="text-3xl font-semibold text-slate-100">{allow.toLocaleString()}</p>
            <p className="text-sm text-slate-500 mb-1">{((allow/total)*100).toFixed(1)}%</p>
          </div>
        </div>

        <div className="bg-[#0f172a] border border-slate-800/60 p-5 rounded-xl shadow-sm hover:border-slate-700 transition-colors">
          <div className="flex items-center gap-3 mb-3">
            <div className="p-2 bg-amber-900/30 rounded-lg"><AlertTriangle size={16} className="text-amber-500" /></div>
            <p className="text-xs font-medium text-slate-400 uppercase tracking-wider">Review</p>
          </div>
          <div className="flex items-end gap-3">
            <p className="text-3xl font-semibold text-slate-100">{review.toLocaleString()}</p>
            <p className="text-sm text-slate-500 mb-1">{((review/total)*100).toFixed(1)}%</p>
          </div>
        </div>

        <div className="bg-[#0f172a] border border-slate-800/60 p-5 rounded-xl shadow-sm hover:border-slate-700 transition-colors">
          <div className="flex items-center gap-3 mb-3">
            <div className="p-2 bg-rose-900/30 rounded-lg"><Ban size={16} className="text-rose-500" /></div>
            <p className="text-xs font-medium text-slate-400 uppercase tracking-wider">Block</p>
          </div>
          <div className="flex items-end gap-3">
            <p className="text-3xl font-semibold text-slate-100">{block.toLocaleString()}</p>
            <p className="text-sm text-slate-500 mb-1">{((block/total)*100).toFixed(1)}%</p>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Trend Chart */}
        <div className="bg-[#0f172a] border border-slate-800/60 p-6 rounded-xl shadow-sm lg:col-span-2">
          <div className="flex items-center justify-between mb-6">
            <div>
              <h2 className="text-base font-semibold text-slate-200">Decision Trend Over Time</h2>
              <p className="text-xs text-slate-400 mt-1">Aggregated actual decision volume by day.</p>
            </div>
            <TrendingUp className="text-slate-500" size={18}/>
          </div>
          <div className="h-72 w-full">
            {trends.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={trends} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                  <XAxis dataKey="date" stroke="#64748b" fontSize={12} tickLine={false} axisLine={false} />
                  <YAxis stroke="#64748b" fontSize={12} tickLine={false} axisLine={false} />
                  <Tooltip 
                    cursor={{ fill: '#1e293b' }}
                    contentStyle={{ backgroundColor: '#020617', borderColor: '#1e293b', color: '#e2e8f0', borderRadius: '8px' }}
                  />
                  <Legend iconType="circle" wrapperStyle={{ fontSize: '12px', color: '#94a3b8' }}/>
                  <Bar dataKey="BLOCK" stackId="a" fill="#f43f5e" radius={[0, 0, 4, 4]} />
                  <Bar dataKey="REVIEW" stackId="a" fill="#f59e0b" />
                  <Bar dataKey="ALLOW" stackId="a" fill="#10b981" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full flex items-center justify-center text-slate-500 text-sm">Insufficient time-series data</div>
            )}
          </div>
        </div>

        {/* Evidence Quality */}
        <div className="bg-[#0f172a] border border-slate-800/60 p-6 rounded-xl shadow-sm flex flex-col">
          <h2 className="text-base font-semibold text-slate-200">Evidence Quality</h2>
          <p className="text-xs text-slate-400 mt-1 mb-6">Completeness of context used in assessments.</p>
          
          <div className="space-y-5 flex-1">
            <div>
              <div className="flex justify-between text-sm mb-1">
                <span className="text-slate-300 font-medium">FULL</span>
                <span className="text-slate-400">{fullEv.toLocaleString()}</span>
              </div>
              <div className="w-full bg-slate-800 rounded-full h-2">
                <div className="bg-emerald-500 h-2 rounded-full" style={{ width: `${total > 0 ? (fullEv/total)*100 : 0}%` }}></div>
              </div>
              <p className="text-[10px] text-slate-500 mt-1">Complete historical evidence available</p>
            </div>
            
            <div>
              <div className="flex justify-between text-sm mb-1">
                <span className="text-slate-300 font-medium">PARTIAL</span>
                <span className="text-slate-400">{partEv.toLocaleString()}</span>
              </div>
              <div className="w-full bg-slate-800 rounded-full h-2">
                <div className="bg-blue-500 h-2 rounded-full" style={{ width: `${total > 0 ? (partEv/total)*100 : 0}%` }}></div>
              </div>
              <p className="text-[10px] text-slate-500 mt-1">Some contextual evidence missing</p>
            </div>

            <div>
              <div className="flex justify-between text-sm mb-1">
                <span className="text-slate-300 font-medium">LIMITED</span>
                <span className="text-slate-400">{limitEv.toLocaleString()}</span>
              </div>
              <div className="w-full bg-slate-800 rounded-full h-2">
                <div className="bg-amber-500 h-2 rounded-full" style={{ width: `${total > 0 ? (limitEv/total)*100 : 0}%` }}></div>
              </div>
              <p className="text-[10px] text-slate-500 mt-1">Limited evidence available</p>
            </div>

            <div>
              <div className="flex justify-between text-sm mb-1">
                <span className="text-slate-300 font-medium">UNAVAILABLE</span>
                <span className="text-slate-400">{unavailEv.toLocaleString()}</span>
              </div>
              <div className="w-full bg-slate-800 rounded-full h-2">
                <div className="bg-rose-500 h-2 rounded-full" style={{ width: `${total > 0 ? (unavailEv/total)*100 : 0}%` }}></div>
              </div>
              <p className="text-[10px] text-slate-500 mt-1">Required evidence insufficient for assessment</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
