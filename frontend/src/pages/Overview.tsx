import { useEffect, useState } from 'react';
import { getOperationalAnalytics, simulateReviewCapacity } from '../api';
import { 
  Activity, 
  Clock, Target, Database,
  AlertCircle
, Calculator, ArrowRight } from 'lucide-react';
import { 
  BarChart, Bar, XAxis, YAxis, Tooltip, 
  ResponsiveContainer, CartesianGrid, Legend, Line, ComposedChart
, LineChart } from 'recharts';

export default function Overview() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [simAssumptions, setSimAssumptions] = useState({
    horizon_hours: 24,
    capacity_per_hour: 20,
    arrival_rate_per_hour: 10,
    use_observed_arrival: false,
    initial_backlog: 0
  });
  const [simResult, setSimResult] = useState<any>(null);
  const [simLoading, setSimLoading] = useState(false);
  const [simError, setSimError] = useState<string|null>(null);

  const handleSimulate = async () => {
    setSimLoading(true);
    setSimError(null);
    try {
      const res = await simulateReviewCapacity(simAssumptions);
      setSimResult(res.data);
    } catch (err: any) {
      setSimError(err.response?.data?.detail?.[0]?.msg || err.response?.data?.detail || "Simulation failed");
    } finally {
      setSimLoading(false);
    }
  };


  useEffect(() => {
    getOperationalAnalytics()
      .then(res => {
        setData(res.data);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  if (loading) return (
    <div className="flex h-64 items-center justify-center space-x-2">
      <div className="w-4 h-4 bg-blue-500 rounded-full animate-bounce"></div>
      <div className="w-4 h-4 bg-blue-500 rounded-full animate-bounce delay-75"></div>
      <div className="w-4 h-4 bg-blue-500 rounded-full animate-bounce delay-150"></div>
    </div>
  );

  if (!data || data.decision_distribution.total === 0) return (
    <div className="h-64 flex flex-col items-center justify-center text-slate-500 bg-[#0f172a] rounded-xl border border-slate-800">
      <Database size={48} className="mb-4 opacity-30" />
      <h3 className="text-xl font-semibold text-slate-300">NO DATA</h3>
      <p>There are no operational records in the database.</p>
    </div>
  );

  const { decision_distribution, review_workload, evaluation, timing, timeseries } = data;

  return (
    <div className="space-y-8">
      
      {/* 1. DECISION DISTRIBUTION */}
      <div>
        <h2 className="text-lg font-semibold text-slate-200 mb-4 flex items-center gap-2">
          <Activity size={18} className="text-blue-400" /> Decision Distribution
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div className="bg-[#0f172a] border border-slate-800 p-5 rounded-xl">
            <p className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-2">Total Volume</p>
            <p className="text-3xl font-semibold text-slate-100">{decision_distribution.total.toLocaleString()}</p>
          </div>
          <div className="bg-[#0f172a] border border-emerald-900/30 p-5 rounded-xl border-l-4 border-l-emerald-500">
            <p className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-2">Allow</p>
            <div className="flex items-end gap-3">
              <p className="text-3xl font-semibold text-emerald-400">{decision_distribution.allow.toLocaleString()}</p>
              <p className="text-sm text-slate-500 mb-1">{decision_distribution.allow_pct}</p>
            </div>
          </div>
          <div className="bg-[#0f172a] border border-amber-900/30 p-5 rounded-xl border-l-4 border-l-amber-500">
            <p className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-2">Review</p>
            <div className="flex items-end gap-3">
              <p className="text-3xl font-semibold text-amber-400">{decision_distribution.review.toLocaleString()}</p>
              <p className="text-sm text-slate-500 mb-1">{decision_distribution.review_pct}</p>
            </div>
          </div>
          <div className="bg-[#0f172a] border border-rose-900/30 p-5 rounded-xl border-l-4 border-l-rose-500">
            <p className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-2">Block</p>
            <div className="flex items-end gap-3">
              <p className="text-3xl font-semibold text-rose-400">{decision_distribution.block.toLocaleString()}</p>
              <p className="text-sm text-slate-500 mb-1">{decision_distribution.block_pct}</p>
            </div>
          </div>
        </div>
      </div>

      {/* 2. REVIEW OPERATIONS */}
      <div>
        <h2 className="text-lg font-semibold text-slate-200 mb-4 flex items-center gap-2">
          <Clock size={18} className="text-amber-400" /> Review Operations
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div className="bg-[#0f172a] border border-slate-800 p-5 rounded-xl">
            <p className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-2">Pending Review</p>
            <p className="text-3xl font-semibold text-amber-400">{review_workload.pending.toLocaleString()}</p>
          </div>
          <div className="bg-[#0f172a] border border-slate-800 p-5 rounded-xl">
            <p className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-2">Feedback Recorded</p>
            <p className="text-3xl font-semibold text-blue-400">{review_workload.feedback_recorded.toLocaleString()}</p>
          </div>
          <div className="bg-[#0f172a] border border-slate-800 p-5 rounded-xl">
            <p className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-2">Resolution Rate</p>
            <p className="text-3xl font-semibold text-slate-100">{review_workload.resolution_rate}</p>
          </div>
          <div className="bg-[#0f172a] border border-slate-800 p-5 rounded-xl">
            <p className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-2 flex items-center gap-1">Median Time <span className="text-[9px] text-slate-500 lowercase">(assess-to-label)</span></p>
            <p className="text-3xl font-semibold text-slate-100">
              {timing.median_seconds === 'NOT MEASURED' ? 'N/A' : `${timing.median_seconds}s`}
            </p>
          </div>
        </div>
      </div>

      {/* 3. EVALUATION */}
      <div>
        <h2 className="text-lg font-semibold text-slate-200 mb-4 flex items-center gap-2">
          <Target size={18} className="text-indigo-400" /> Evaluation
        </h2>
        {evaluation.labeled_assessments === 0 ? (
          <div className="bg-[#0f172a] p-6 rounded-xl border border-slate-800 text-slate-400 flex items-center gap-3">
            <AlertCircle size={20} className="text-amber-500" />
            <div>
              <p className="font-semibold text-slate-300">Ground-truth feedback is not available yet.</p>
              <p className="text-sm">Performance metrics are NOT MEASURED.</p>
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-6 gap-4">
            <div className="bg-[#0f172a] border border-indigo-900/40 p-4 rounded-xl md:col-span-2">
              <p className="text-xs font-medium text-indigo-400/80 uppercase tracking-wider mb-1">Labeled Assessments</p>
              <p className="text-2xl font-semibold text-indigo-400">{evaluation.labeled_assessments.toLocaleString()}</p>
            </div>
            <div className="bg-[#0f172a] border border-red-900/30 p-4 rounded-xl">
              <p className="text-xs font-medium text-red-500/80 uppercase tracking-wider mb-1">TP</p>
              <p className="text-2xl font-semibold text-red-500">{evaluation.tp.toLocaleString()}</p>
            </div>
            <div className="bg-[#0f172a] border border-emerald-900/30 p-4 rounded-xl">
              <p className="text-xs font-medium text-emerald-500/80 uppercase tracking-wider mb-1">TN</p>
              <p className="text-2xl font-semibold text-emerald-500">{evaluation.tn.toLocaleString()}</p>
            </div>
            <div className="bg-[#0f172a] border border-orange-900/30 p-4 rounded-xl">
              <p className="text-xs font-medium text-orange-500/80 uppercase tracking-wider mb-1">FP</p>
              <p className="text-2xl font-semibold text-orange-500">{evaluation.fp.toLocaleString()}</p>
            </div>
            <div className="bg-[#0f172a] border border-rose-900/30 p-4 rounded-xl">
              <p className="text-xs font-medium text-rose-500/80 uppercase tracking-wider mb-1">FN</p>
              <p className="text-2xl font-semibold text-rose-500">{evaluation.fn.toLocaleString()}</p>
            </div>
          </div>
        )}
      </div>

      {/* 4. CHARTS */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        
        {/* Chart 1 */}
        <div className="bg-[#0f172a] border border-slate-800 p-6 rounded-xl shadow-sm">
          <h2 className="text-base font-semibold text-slate-200 mb-6">Decision Volume over Time</h2>
          <div className="h-64">
            {timeseries.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={timeseries} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                  <XAxis dataKey="date" stroke="#64748b" fontSize={10} tickLine={false} axisLine={false} />
                  <YAxis stroke="#64748b" fontSize={10} tickLine={false} axisLine={false} />
                  <Tooltip cursor={{ fill: '#1e293b' }} contentStyle={{ backgroundColor: '#020617', borderColor: '#1e293b', color: '#e2e8f0', fontSize: '12px' }} />
                  <Legend wrapperStyle={{ fontSize: '10px' }} />
                  <Bar dataKey="block" name="BLOCK" stackId="a" fill="#f43f5e" />
                  <Bar dataKey="review" name="REVIEW" stackId="a" fill="#f59e0b" />
                  <Bar dataKey="allow" name="ALLOW" stackId="a" fill="#10b981" />
                </BarChart>
              </ResponsiveContainer>
            ) : <p className="text-slate-500 text-sm text-center pt-20">NO DATA</p>}
          </div>
        </div>

        {/* Chart 2 */}
        <div className="bg-[#0f172a] border border-slate-800 p-6 rounded-xl shadow-sm">
          <h2 className="text-base font-semibold text-slate-200 mb-6">Feedback Workload Flow</h2>
          <div className="h-64">
            {timeseries.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={timeseries} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                  <XAxis dataKey="date" stroke="#64748b" fontSize={10} tickLine={false} axisLine={false} />
                  <YAxis stroke="#64748b" fontSize={10} tickLine={false} axisLine={false} />
                  <Tooltip cursor={{ fill: '#1e293b' }} contentStyle={{ backgroundColor: '#020617', borderColor: '#1e293b', color: '#e2e8f0', fontSize: '12px' }} />
                  <Legend wrapperStyle={{ fontSize: '10px' }} />
                  <Bar dataKey="review" name="Arriving REVIEW" fill="#3b82f6" opacity={0.3} radius={[4,4,0,0]} />
                  <Line type="monotone" dataKey="feedback" name="Feedback Recorded" stroke="#60a5fa" strokeWidth={2} dot={{r:3}} />
                </ComposedChart>
              </ResponsiveContainer>
            ) : <p className="text-slate-500 text-sm text-center pt-20">NO DATA</p>}
          </div>
        </div>

      </div>

      {/* 5. SIMULATION SECTION */}
      <div className="mt-12 bg-slate-900 border border-indigo-900/50 rounded-xl overflow-hidden relative">
        <div className="absolute top-0 right-0 bg-indigo-600 text-white text-[10px] font-bold px-3 py-1 rounded-bl-lg tracking-widest uppercase">
          WHAT-IF SIMULATION
        </div>
        
        <div className="p-6 border-b border-indigo-900/30 bg-indigo-950/20">
          <h2 className="text-lg font-semibold text-indigo-300 flex items-center gap-2 mb-2">
            <Calculator size={18} /> Review Capacity What-If
          </h2>
          <p className="text-xs text-indigo-400/80 max-w-3xl">
            This planning tool demonstrates how the review backlog might evolve under hypothetical arrival and service rates. 
            <strong className="text-indigo-300 ml-1">It does NOT represent observed production performance or control the actual operational queue.</strong>
          </p>
        </div>

        <div className="p-6 grid grid-cols-1 lg:grid-cols-4 gap-8">
          
          <div className="space-y-4">
            <h3 className="text-sm font-semibold text-slate-300 mb-4">Scenario Inputs</h3>
            
            <div>
              <label className="block text-xs text-slate-500 mb-1">Capacity (reviews/hour)</label>
              <input type="number" min="0" value={simAssumptions.capacity_per_hour} onChange={e => setSimAssumptions({...simAssumptions, capacity_per_hour: Number(e.target.value)})} className="w-full bg-slate-950 border border-slate-700 rounded px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-indigo-500" />
            </div>

            <div>
              <div className="flex items-center justify-between mb-1">
                <label className="block text-xs text-slate-500">Arrival Rate (reviews/hour)</label>
                <label className="flex items-center gap-1 text-[10px] text-slate-400 cursor-pointer">
                  <input type="checkbox" checked={simAssumptions.use_observed_arrival} onChange={e => setSimAssumptions({...simAssumptions, use_observed_arrival: e.target.checked})} className="rounded bg-slate-800 border-slate-700" />
                  Use Observed
                </label>
              </div>
              <input type="number" min="0" disabled={simAssumptions.use_observed_arrival} value={simAssumptions.use_observed_arrival ? '' : simAssumptions.arrival_rate_per_hour} onChange={e => setSimAssumptions({...simAssumptions, arrival_rate_per_hour: Number(e.target.value)})} className="w-full bg-slate-950 border border-slate-700 rounded px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-indigo-500 disabled:opacity-50" placeholder={simAssumptions.use_observed_arrival ? 'Auto-calculated' : ''} />
            </div>

            <div>
              <label className="block text-xs text-slate-500 mb-1">Horizon (hours)</label>
              <input type="number" min="1" max="720" value={simAssumptions.horizon_hours} onChange={e => setSimAssumptions({...simAssumptions, horizon_hours: Number(e.target.value)})} className="w-full bg-slate-950 border border-slate-700 rounded px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-indigo-500" />
            </div>

            <div>
              <label className="block text-xs text-slate-500 mb-1">Initial Backlog</label>
              <input type="number" min="0" value={simAssumptions.initial_backlog} onChange={e => setSimAssumptions({...simAssumptions, initial_backlog: Number(e.target.value)})} className="w-full bg-slate-950 border border-slate-700 rounded px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-indigo-500" />
            </div>
            
            {simError && (
              <div className="text-xs text-red-400 bg-red-900/20 p-2 rounded border border-red-900/50">
                {simError}
              </div>
            )}

            <button 
              onClick={handleSimulate}
              disabled={simLoading}
              className="w-full bg-indigo-600 hover:bg-indigo-700 text-white font-medium py-2 rounded text-sm transition-colors flex items-center justify-center gap-2 disabled:opacity-70"
            >
              {simLoading ? 'Simulating...' : 'Run Simulation'} <ArrowRight size={14} />
            </button>
          </div>

          <div className="lg:col-span-3">
            {simResult ? (
              <div className="space-y-6 animate-in fade-in slide-in-from-bottom-2 duration-300">
                <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                  <div className="bg-slate-950 border border-slate-800 p-4 rounded-xl">
                    <p className="text-[10px] text-slate-500 uppercase tracking-widest mb-1">Total Arrivals</p>
                    <p className="text-xl font-mono text-slate-300">{simResult.results.total_arrivals}</p>
                  </div>
                  <div className="bg-slate-950 border border-slate-800 p-4 rounded-xl">
                    <p className="text-[10px] text-slate-500 uppercase tracking-widest mb-1">Completed</p>
                    <p className="text-xl font-mono text-emerald-400">{simResult.results.total_completed}</p>
                  </div>
                  <div className="bg-slate-950 border border-indigo-900/50 p-4 rounded-xl border-t-2 border-t-indigo-500">
                    <p className="text-[10px] text-indigo-400 uppercase tracking-widest mb-1">Ending Backlog</p>
                    <p className="text-xl font-mono text-indigo-300">{simResult.results.ending_backlog}</p>
                  </div>
                  <div className="bg-slate-950 border border-slate-800 p-4 rounded-xl">
                    <p className="text-[10px] text-slate-500 uppercase tracking-widest mb-1">Max Backlog</p>
                    <p className="text-xl font-mono text-slate-300">{simResult.results.maximum_backlog}</p>
                  </div>
                  <div className="bg-slate-950 border border-slate-800 p-4 rounded-xl">
                    <p className="text-[10px] text-slate-500 uppercase tracking-widest mb-1">Avg Backlog</p>
                    <p className="text-xl font-mono text-slate-300">{simResult.results.average_backlog}</p>
                  </div>
                </div>

                <div className="bg-slate-950 p-4 rounded-lg border border-slate-800 flex items-center gap-3">
                  <AlertCircle size={16} className={simResult.interpretation.includes('grows') ? 'text-amber-500' : 'text-emerald-500'} />
                  <span className="text-sm text-slate-300">{simResult.interpretation}</span>
                </div>

                <div className="h-64 mt-4">
                  <h3 className="text-xs font-semibold text-slate-400 mb-4">Backlog Trend (Simulated)</h3>
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={simResult.timeseries} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                      <XAxis dataKey="hour" stroke="#64748b" fontSize={10} tickLine={false} axisLine={false} />
                      <YAxis stroke="#64748b" fontSize={10} tickLine={false} axisLine={false} />
                      <Tooltip cursor={{ stroke: '#334155' }} contentStyle={{ backgroundColor: '#020617', borderColor: '#312e81', color: '#e2e8f0', fontSize: '12px' }} />
                      <Legend wrapperStyle={{ fontSize: '10px' }} />
                      <Line type="stepAfter" dataKey="backlog" name="Simulated Backlog" stroke="#818cf8" strokeWidth={2} dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </div>
            ) : (
              <div className="h-full flex items-center justify-center border-2 border-dashed border-slate-800 rounded-xl">
                <div className="text-center">
                  <Calculator size={32} className="mx-auto text-slate-600 mb-3" />
                  <p className="text-sm text-slate-400">Configure assumptions and click Run Simulation</p>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

    </div>
  );
}
