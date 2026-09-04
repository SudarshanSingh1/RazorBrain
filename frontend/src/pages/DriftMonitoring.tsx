import { useEffect, useState } from 'react';
import { getDriftMonitoring } from '../api';
import { Activity, AlertTriangle, AlertCircle, TrendingUp, CheckCircle, Database } from 'lucide-react';

export default function DriftMonitoring() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [windowHours, setWindowHours] = useState(24);

  const fetchDrift = async () => {
    setLoading(true);
    try {
      const res = await getDriftMonitoring(windowHours);
      setData(res.data);
    } catch (err: any) {
      setError(err?.message || 'Failed to load drift data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDrift();
  }, [windowHours]);

  if (loading && !data) return <div className="p-8 flex justify-center"><Activity className="animate-spin text-indigo-500" /></div>;
  if (error) return <div className="text-red-400 border border-red-900 bg-red-950/20 p-4 rounded-md m-6">{error}</div>;

  return (
    <div className="max-w-6xl mx-auto space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100 flex items-center gap-3">
            <TrendingUp className="text-indigo-500" /> Drift Monitoring
          </h1>
          <p className="text-slate-400 mt-1 max-w-2xl text-sm">
            Drift indicates that the observed scoring population differs from the reference population. 
            Drift does not by itself prove that model accuracy has decreased.
            Drift monitoring does not automatically change fraud decisions.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <label className="text-sm text-slate-400">Window:</label>
          <select 
            value={windowHours} 
            onChange={(e) => setWindowHours(Number(e.target.value))}
            className="bg-slate-900 border border-slate-700 rounded px-3 py-1 text-sm text-slate-200 focus:outline-none"
          >
            <option value={1}>Last 1 Hour</option>
            <option value={24}>Last 24 Hours</option>
            <option value={72}>Last 3 Days</option>
            <option value={168}>Last 7 Days</option>
            <option value={720}>Last 30 Days</option>
          </select>
        </div>
      </div>

      {data?.status === 'NOT_MEASURED' ? (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-12 text-center">
          <Database size={48} className="mx-auto text-slate-600 mb-4" />
          <h3 className="text-lg font-medium text-slate-300">Not Measured</h3>
          <p className="text-slate-500 mt-2">{data.reason || 'Not enough observations to measure drift.'}</p>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className={`border p-6 rounded-xl ${
              data.overall_status === 'HIGH DRIFT SIGNAL' ? 'bg-red-950/20 border-red-900/50' :
              data.overall_status === 'MODERATE DRIFT SIGNAL' ? 'bg-amber-950/20 border-amber-900/50' :
              'bg-[#0f172a] border-slate-800'
            }`}>
              <p className="text-xs text-slate-400 uppercase tracking-widest mb-1">Monitoring Status</p>
              <h2 className={`text-2xl font-bold flex items-center gap-2 ${
                data.overall_status === 'HIGH DRIFT SIGNAL' ? 'text-red-400' :
                data.overall_status === 'MODERATE DRIFT SIGNAL' ? 'text-amber-400' :
                'text-emerald-400'
              }`}>
                {data.overall_status === 'HIGH DRIFT SIGNAL' && <AlertTriangle size={20} />}
                {data.overall_status === 'MODERATE DRIFT SIGNAL' && <AlertCircle size={20} />}
                {data.overall_status === 'NO MATERIAL SIGNAL' && <CheckCircle size={20} />}
                {data.overall_status}
              </h2>
            </div>
            <div className="bg-[#0f172a] border border-slate-800 p-6 rounded-xl">
              <p className="text-xs text-slate-400 uppercase tracking-widest mb-1">Current Window</p>
              <h2 className="text-2xl font-bold text-slate-200">{data.current_observations} <span className="text-sm font-normal text-slate-500">observations</span></h2>
            </div>
            <div className="bg-[#0f172a] border border-slate-800 p-6 rounded-xl">
              <p className="text-xs text-slate-400 uppercase tracking-widest mb-1">Reference Population</p>
              <h2 className="text-2xl font-bold text-slate-200">{data.reference_observations} <span className="text-sm font-normal text-slate-500">observations</span></h2>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
            <div className="bg-[#0f172a] border border-slate-800 rounded-xl overflow-hidden">
              <div className="p-5 border-b border-slate-800 bg-slate-900/50">
                <h3 className="font-semibold text-slate-200">Feature Drift</h3>
              </div>
              <div className="max-h-[400px] overflow-y-auto">
                <table className="w-full text-left text-sm">
                  <thead className="bg-slate-900/80 text-slate-400 sticky top-0">
                    <tr>
                      <th className="px-5 py-3 font-semibold">Feature</th>
                      <th className="px-5 py-3 font-semibold">PSI</th>
                      <th className="px-5 py-3 font-semibold">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/50">
                    {data.features?.sort((a: any, b: any) => b.psi - a.psi).map((f: any) => (
                      <tr key={f.feature} className="hover:bg-slate-800/30 transition-colors">
                        <td className="px-5 py-3 text-slate-300">{f.feature}</td>
                        <td className="px-5 py-3 font-mono text-slate-400">{f.psi.toFixed(4)}</td>
                        <td className="px-5 py-3">
                          <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                            f.status === 'HIGH' ? 'bg-red-900/40 text-red-400' :
                            f.status === 'MODERATE' ? 'bg-amber-900/40 text-amber-400' :
                            'bg-slate-800 text-slate-400'
                          }`}>{f.status}</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="space-y-8">
              <div className="bg-[#0f172a] border border-slate-800 rounded-xl overflow-hidden">
                <div className="p-5 border-b border-slate-800 bg-slate-900/50">
                  <h3 className="font-semibold text-slate-200">Prediction Drift</h3>
                </div>
                <div className="p-6">
                  {data.prediction_drift?.status === 'NOT_MEASURED' ? (
                    <p className="text-sm text-slate-500">{data.prediction_drift.reason}</p>
                  ) : (
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-xs text-slate-500 uppercase tracking-wider mb-1">Probability PSI</p>
                        <p className="text-3xl font-mono text-slate-200">{data.prediction_drift?.psi?.toFixed(4)}</p>
                      </div>
                      <div>
                        <span className={`px-3 py-1 rounded text-xs font-bold ${
                          data.prediction_drift?.status === 'HIGH' ? 'bg-red-900/40 text-red-400' :
                          data.prediction_drift?.status === 'MODERATE' ? 'bg-amber-900/40 text-amber-400' :
                          'bg-emerald-900/20 text-emerald-400'
                        }`}>{data.prediction_drift?.status}</span>
                      </div>
                    </div>
                  )}
                </div>
              </div>

              <div className="bg-[#0f172a] border border-slate-800 rounded-xl overflow-hidden">
                <div className="p-5 border-b border-slate-800 bg-slate-900/50">
                  <h3 className="font-semibold text-slate-200">Decision Distribution</h3>
                </div>
                <div className="p-6">
                  {data.decision_drift?.status === 'NOT_MEASURED' ? (
                    <p className="text-sm text-slate-500">{data.decision_drift.reason}</p>
                  ) : (
                    <table className="w-full text-left text-sm">
                      <thead className="text-slate-500 border-b border-slate-800">
                        <tr>
                          <th className="pb-3 font-medium">Decision</th>
                          <th className="pb-3 font-medium text-right">Reference</th>
                          <th className="pb-3 font-medium text-right">Current</th>
                          <th className="pb-3 font-medium text-right">Change</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800/30">
                        {['ALLOW', 'REVIEW', 'BLOCK'].map((dec) => {
                          const stats = data.decision_drift?.[dec];
                          if (!stats) return null;
                          const change = stats.change;
                          return (
                            <tr key={dec}>
                              <td className="py-3 font-medium text-slate-300">{dec}</td>
                              <td className="py-3 text-right font-mono text-slate-400">{(stats.reference * 100).toFixed(1)}%</td>
                              <td className="py-3 text-right font-mono text-slate-200">{(stats.current * 100).toFixed(1)}%</td>
                              <td className={`py-3 text-right font-mono font-medium ${
                                change > 0 ? 'text-amber-400' : change < 0 ? 'text-emerald-400' : 'text-slate-500'
                              }`}>
                                {change > 0 ? '+' : ''}{(change * 100).toFixed(1)} pp
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  )}
                </div>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
