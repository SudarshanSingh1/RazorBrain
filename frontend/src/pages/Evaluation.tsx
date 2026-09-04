import { useEffect, useState } from 'react';
import axios from 'axios';
import { Activity, ShieldAlert, ShieldCheck, FileText, TrendingUp, AlertTriangle } from 'lucide-react';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const API_KEY = import.meta.env.VITE_API_KEY || 'dev-api-key-123';

export default function Evaluation() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchAnalytics = async () => {
      try {
        const response = await axios.get(`${API_URL}/analytics/evaluation`, {
          headers: {
            'X-API-Key': API_KEY
          }
        });
        setData(response.data);
      } catch (err: any) {
        setError(err.message || 'Failed to fetch evaluation analytics');
      } finally {
        setLoading(false);
      }
    };
    fetchAnalytics();
  }, []);

  if (loading) return <div className="p-8 text-slate-400">Loading evaluation analytics...</div>;
  if (error) return <div className="p-8 text-red-400">Error: {error}</div>;

  const metrics = data?.metrics;
  const isMeasured = metrics?.labeled_volume > 0;

  if (!isMeasured) {
    return (
      <div className="p-8 flex flex-col items-center justify-center h-[70vh]">
        <div className="w-16 h-16 bg-slate-800/50 rounded-full flex items-center justify-center mb-6 border border-slate-700/50">
          <Activity size={32} className="text-slate-500" />
        </div>
        <h2 className="text-2xl font-semibold text-slate-200 mb-2">NOT MEASURED</h2>
        <p className="text-slate-400 max-w-lg text-center mb-6">
          RazorBrain currently has predictions and decisions, but no production ground-truth labels have been recorded. 
          Ground-truth feedback is not available yet.
        </p>
        <div className="flex gap-4 items-center justify-center w-full max-w-2xl text-sm mt-8 border-t border-slate-800 pt-8">
          <div className="flex flex-col items-center p-4 bg-slate-900/50 rounded-lg border border-slate-800 w-1/3">
            <span className="text-slate-500 font-mono mb-1">PRECISION</span>
            <span className="text-xl font-bold text-slate-300">NOT MEASURED</span>
          </div>
          <div className="flex flex-col items-center p-4 bg-slate-900/50 rounded-lg border border-slate-800 w-1/3">
            <span className="text-slate-500 font-mono mb-1">RECALL</span>
            <span className="text-xl font-bold text-slate-300">NOT MEASURED</span>
          </div>
        </div>
        <p className="text-xs text-slate-600 mt-12 text-center max-w-md">
          RazorBrain does not infer ground truth from its own decisions. 
          Razorpay webhook events are payment lifecycle events and are not automatically treated as fraud labels.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Top row stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-[#0f172a] p-5 rounded-xl border border-slate-800/60 shadow-lg">
          <div className="flex justify-between items-start mb-2">
            <span className="text-slate-400 text-sm font-medium">Labeled Volume</span>
            <FileText size={18} className="text-blue-500" />
          </div>
          <div className="text-3xl font-bold text-white tracking-tight">{metrics.labeled_volume.toLocaleString()}</div>
          <div className="mt-2 text-xs text-slate-500 flex gap-2">
            <span className="text-red-400">{metrics.fraud_labels} Fraud</span> 
            <span>•</span>
            <span className="text-emerald-400">{metrics.legitimate_labels} Legit</span>
          </div>
        </div>

        <div className="bg-[#0f172a] p-5 rounded-xl border border-slate-800/60 shadow-lg">
          <div className="flex justify-between items-start mb-2">
            <span className="text-slate-400 text-sm font-medium">Precision</span>
            <TrendingUp size={18} className="text-emerald-500" />
          </div>
          <div className="text-3xl font-bold text-white tracking-tight">{metrics.precision}</div>
          <div className="mt-2 text-xs text-slate-500">
            True Positives / Predicted Positives
          </div>
        </div>

        <div className="bg-[#0f172a] p-5 rounded-xl border border-slate-800/60 shadow-lg">
          <div className="flex justify-between items-start mb-2">
            <span className="text-slate-400 text-sm font-medium">Recall</span>
            <ShieldAlert size={18} className="text-orange-500" />
          </div>
          <div className="text-3xl font-bold text-white tracking-tight">{metrics.recall}</div>
          <div className="mt-2 text-xs text-slate-500">
            True Positives / Actual Fraud
          </div>
        </div>

        <div className="bg-[#0f172a] p-5 rounded-xl border border-slate-800/60 shadow-lg">
          <div className="flex justify-between items-start mb-2">
            <span className="text-slate-400 text-sm font-medium">Specificity</span>
            <ShieldCheck size={18} className="text-blue-500" />
          </div>
          <div className="text-3xl font-bold text-white tracking-tight">{metrics.specificity}</div>
          <div className="mt-2 text-xs text-slate-500">
            True Negatives / Actual Legit
          </div>
        </div>
      </div>

      {/* Confusion Matrix */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-[#0f172a] rounded-xl border border-slate-800/60 shadow-lg p-6">
          <h3 className="text-lg font-semibold text-slate-200 mb-6 flex items-center gap-2">
            <Activity size={18} className="text-blue-500" /> 
            Confusion Matrix
          </h3>
          
          <div className="grid grid-cols-2 gap-4">
            <div className="p-4 bg-slate-900/50 rounded-lg border border-red-900/30">
              <div className="text-slate-400 text-sm mb-1">True Positives (TP)</div>
              <div className="text-2xl font-bold text-red-500 mb-1">{metrics.tp.toLocaleString()}</div>
              <div className="text-xs text-slate-500">BLOCK + FRAUD</div>
            </div>
            <div className="p-4 bg-slate-900/50 rounded-lg border border-emerald-900/30">
              <div className="text-slate-400 text-sm mb-1">True Negatives (TN)</div>
              <div className="text-2xl font-bold text-emerald-500 mb-1">{metrics.tn.toLocaleString()}</div>
              <div className="text-xs text-slate-500">ALLOW + LEGIT</div>
            </div>
            <div className="p-4 bg-slate-900/50 rounded-lg border border-orange-900/30">
              <div className="text-slate-400 text-sm mb-1">False Positives (FP)</div>
              <div className="text-2xl font-bold text-orange-500 mb-1">{metrics.fp.toLocaleString()}</div>
              <div className="text-xs text-slate-500">BLOCK + LEGIT</div>
            </div>
            <div className="p-4 bg-slate-900/50 rounded-lg border border-rose-900/30">
              <div className="text-slate-400 text-sm mb-1">False Negatives (FN)</div>
              <div className="text-2xl font-bold text-rose-500 mb-1">{metrics.fn.toLocaleString()}</div>
              <div className="text-xs text-slate-500">ALLOW + FRAUD</div>
            </div>
          </div>
          
          <div className="mt-4 p-4 bg-slate-900/50 rounded-lg border border-blue-900/30">
            <div className="flex justify-between items-end">
              <div>
                <div className="text-slate-400 text-sm mb-1">Unresolved / Reviewed</div>
                <div className="text-2xl font-bold text-blue-500">{metrics.unresolved.toLocaleString()}</div>
              </div>
              <div className="text-xs text-slate-500 text-right">
                REVIEW + FRAUD<br/>REVIEW + LEGIT
              </div>
            </div>
          </div>
        </div>

        <div className="bg-[#0f172a] rounded-xl border border-slate-800/60 shadow-lg p-6">
          <h3 className="text-lg font-semibold text-slate-200 mb-4 flex items-center gap-2">
            <AlertTriangle size={18} className="text-yellow-500" /> 
            Operational Semantics
          </h3>
          <div className="text-sm text-slate-400 space-y-4">
            <p>
              RazorBrain computes evaluation metrics using <strong>strict operational boundaries</strong>.
            </p>
            <ul className="list-disc pl-5 space-y-2">
              <li><strong>Predicted Positive:</strong> A transaction that was <span className="text-red-400 font-mono">BLOCK</span>ed by the decision engine.</li>
              <li><strong>Predicted Negative:</strong> A transaction that was <span className="text-emerald-400 font-mono">ALLOW</span>ed by the decision engine.</li>
              <li><strong>Unresolved:</strong> A transaction that was routed to <span className="text-blue-400 font-mono">REVIEW</span>. This explicitly avoids skewing automated precision/recall metrics.</li>
            </ul>
            <p className="pt-2 border-t border-slate-800">
              F1 Score: <strong className="text-slate-200">{metrics.f1}</strong><br/>
              False Positive Rate: <strong className="text-slate-200">{metrics.fpr}</strong><br/>
              False Negative Rate: <strong className="text-slate-200">{metrics.fnr}</strong>
            </p>
          </div>
        </div>
      </div>

      {/* Timeseries Placeholder */}
      <div className="bg-[#0f172a] rounded-xl border border-slate-800/60 shadow-lg p-6">
        <h3 className="text-lg font-semibold text-slate-200 mb-4">Historical Trend</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-slate-800 text-slate-400">
                <th className="py-3 px-4 font-medium">Date</th>
                <th className="py-3 px-4 font-medium">Labeled</th>
                <th className="py-3 px-4 font-medium">Fraud</th>
                <th className="py-3 px-4 font-medium">Legit</th>
                <th className="py-3 px-4 font-medium text-emerald-500">TP / TN</th>
                <th className="py-3 px-4 font-medium text-red-500">FP / FN</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/50">
              {data.timeseries.map((day: any) => (
                <tr key={day.date} className="hover:bg-slate-800/20 transition-colors">
                  <td className="py-3 px-4 text-slate-300 font-mono">{day.date}</td>
                  <td className="py-3 px-4 text-slate-400">{day.labeled_volume.toLocaleString()}</td>
                  <td className="py-3 px-4 text-red-400">{day.FRAUD.toLocaleString()}</td>
                  <td className="py-3 px-4 text-emerald-400">{day.LEGITIMATE.toLocaleString()}</td>
                  <td className="py-3 px-4 text-slate-400">
                    <span className="text-red-400">{day.TP}</span> / <span className="text-emerald-400">{day.TN}</span>
                  </td>
                  <td className="py-3 px-4 text-slate-400">
                    <span className="text-orange-400">{day.FP}</span> / <span className="text-rose-400">{day.FN}</span>
                  </td>
                </tr>
              ))}
              {data.timeseries.length === 0 && (
                <tr>
                  <td colSpan={6} className="py-6 text-center text-slate-500">No historical data available.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
