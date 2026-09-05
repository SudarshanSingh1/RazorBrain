import { useEffect, useState } from 'react';
import { getEvaluationMetrics } from '../api';
import { Activity, ShieldAlert, ShieldCheck, TrendingUp, AlertTriangle, Database } from 'lucide-react';
import { Card, CardHeader, CardTitle } from '../components/ui';

export default function Evaluation() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getEvaluationMetrics()
      .then(res => {
        setData(res.data);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  if (loading) return (
    <div className="flex h-64 items-center justify-center space-x-2">
      <div className="w-4 h-4 bg-brand rounded-full animate-bounce"></div>
      <div className="w-4 h-4 bg-brand rounded-full animate-bounce delay-75"></div>
      <div className="w-4 h-4 bg-brand rounded-full animate-bounce delay-150"></div>
    </div>
  );

  if (!data || !data.metrics) return <div className="text-accent-red border border-accent-red bg-accent-red/20 p-4 rounded-md">Unable to load evaluation metrics.</div>;

  const metrics = data.metrics;

  return (
    <div className="space-y-4 md:space-y-6 animate-in fade-in duration-500">
      
      {/* Top row: Key Metrics */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 md:gap-6">
        <Card>
          <div className="flex justify-between items-start mb-2">
            <span className="text-text-muted text-[13px] font-semibold uppercase tracking-wider">Labeled Base</span>
            <Database size={18} className="text-brand" />
          </div>
          <div className="text-[32px] md:text-[36px] font-bold text-text-primary tracking-tight leading-none mb-2">{(metrics.labeled_assessments || 0).toLocaleString()}</div>
          <div className="mt-2 text-[12px] font-medium text-text-secondary flex gap-2">
            <span className="text-accent-red">{metrics.fraud_labels} Fraud</span> 
            <span className="text-border-active">•</span>
            <span className="text-accent-green">{metrics.legitimate_labels} Legit</span>
          </div>
        </Card>

        <Card>
          <div className="flex justify-between items-start mb-2">
            <span className="text-text-muted text-[13px] font-semibold uppercase tracking-wider">Precision</span>
            <TrendingUp size={18} className="text-accent-green" />
          </div>
          <div className="text-[32px] md:text-[36px] font-bold text-text-primary tracking-tight leading-none mb-2">{metrics.precision}</div>
          <div className="mt-2 text-[12px] text-text-muted">
            True Positives / Predicted Positives
          </div>
        </Card>

        <Card>
          <div className="flex justify-between items-start mb-2">
            <span className="text-text-muted text-[13px] font-semibold uppercase tracking-wider">Recall</span>
            <ShieldAlert size={18} className="text-accent-yellow" />
          </div>
          <div className="text-[32px] md:text-[36px] font-bold text-text-primary tracking-tight leading-none mb-2">{metrics.recall}</div>
          <div className="mt-2 text-[12px] text-text-muted">
            True Positives / Actual Fraud
          </div>
        </Card>

        <Card>
          <div className="flex justify-between items-start mb-2">
            <span className="text-text-muted text-[13px] font-semibold uppercase tracking-wider">Specificity</span>
            <ShieldCheck size={18} className="text-brand-bright" />
          </div>
          <div className="text-[32px] md:text-[36px] font-bold text-text-primary tracking-tight leading-none mb-2">{metrics.specificity}</div>
          <div className="mt-2 text-[12px] text-text-muted">
            True Negatives / Actual Legit
          </div>
        </Card>
      </div>

      {/* Confusion Matrix */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 md:gap-6">
        <Card>
          <CardHeader>
            <CardTitle icon={<Activity size={16} />}>Confusion Matrix</CardTitle>
          </CardHeader>
          
          <div className="grid grid-cols-2 gap-4">
            <div className="p-4 bg-accent-red/5 rounded-xl border border-accent-red/20">
              <div className="text-text-muted text-[12px] mb-1 font-semibold uppercase tracking-widest">True Positives (TP)</div>
              <div className="text-[28px] font-bold text-accent-red mb-1 leading-none">{(metrics.tp || 0).toLocaleString()}</div>
              <div className="text-[11px] text-text-secondary mt-2">BLOCK + FRAUD</div>
            </div>
            <div className="p-4 bg-accent-green/5 rounded-xl border border-accent-green/20">
              <div className="text-text-muted text-[12px] mb-1 font-semibold uppercase tracking-widest">True Negatives (TN)</div>
              <div className="text-[28px] font-bold text-accent-green mb-1 leading-none">{(metrics.tn || 0).toLocaleString()}</div>
              <div className="text-[11px] text-text-secondary mt-2">ALLOW + LEGIT</div>
            </div>
            <div className="p-4 bg-accent-yellow/5 rounded-xl border border-accent-yellow/20">
              <div className="text-text-muted text-[12px] mb-1 font-semibold uppercase tracking-widest">False Positives (FP)</div>
              <div className="text-[28px] font-bold text-accent-yellow mb-1 leading-none">{(metrics.fp || 0).toLocaleString()}</div>
              <div className="text-[11px] text-text-secondary mt-2">BLOCK + LEGIT</div>
            </div>
            <div className="p-4 bg-accent-red/10 rounded-xl border border-accent-red/30">
              <div className="text-text-muted text-[12px] mb-1 font-semibold uppercase tracking-widest">False Negatives (FN)</div>
              <div className="text-[28px] font-bold text-accent-red mb-1 leading-none">{(metrics.fn || 0).toLocaleString()}</div>
              <div className="text-[11px] text-text-secondary mt-2">ALLOW + FRAUD</div>
            </div>
          </div>
          
          <div className="mt-4 p-4 bg-brand/5 rounded-xl border border-brand/20">
            <div className="flex justify-between items-end">
              <div>
                <div className="text-text-muted text-[12px] mb-1 font-semibold uppercase tracking-widest">Unresolved / Reviewed</div>
                <div className="text-[28px] font-bold text-brand-bright leading-none">{(metrics.unresolved || 0).toLocaleString()}</div>
              </div>
              <div className="text-[11px] text-text-secondary text-right">
                REVIEW + FRAUD<br/>REVIEW + LEGIT
              </div>
            </div>
          </div>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle icon={<AlertTriangle size={16} />}>Operational Semantics</CardTitle>
          </CardHeader>
          <div className="text-[14px] text-text-secondary space-y-4">
            <p>
              RazorBrain computes evaluation metrics using <strong className="text-text-primary">strict operational boundaries</strong>.
            </p>
            <ul className="list-disc pl-5 space-y-2 marker:text-text-muted">
              <li><strong className="text-text-primary">Predicted Positive:</strong> A transaction that was <span className="text-accent-red font-mono font-semibold">BLOCK</span>ed by the decision engine.</li>
              <li><strong className="text-text-primary">Predicted Negative:</strong> A transaction that was <span className="text-accent-green font-mono font-semibold">ALLOW</span>ed by the decision engine.</li>
              <li><strong className="text-text-primary">Unresolved:</strong> A transaction that was routed to <span className="text-brand-bright font-mono font-semibold">REVIEW</span>. This explicitly avoids skewing automated precision/recall metrics.</li>
            </ul>
            <div className="pt-4 mt-2 border-t border-border-subtle flex flex-col gap-2">
              <div className="flex justify-between">
                <span>F1 Score:</span>
                <strong className="text-text-primary">{metrics.f1}</strong>
              </div>
              <div className="flex justify-between">
                <span>False Positive Rate:</span>
                <strong className="text-text-primary">{metrics.fpr}</strong>
              </div>
              <div className="flex justify-between">
                <span>False Negative Rate:</span>
                <strong className="text-text-primary">{metrics.fnr}</strong>
              </div>
            </div>
          </div>
        </Card>
      </div>

      {/* Historical Trend */}
      <Card noPadding>
        <div className="p-5 md:p-6 border-b border-border-subtle">
          <CardTitle>Historical Trend</CardTitle>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-[13px]">
            <thead className="bg-bg-card-secondary text-text-muted uppercase tracking-wider text-[11px] border-b border-border-subtle">
              <tr>
                <th className="py-3 px-5 md:px-6 font-semibold">Date</th>
                <th className="py-3 px-5 md:px-6 font-semibold">Labeled</th>
                <th className="py-3 px-5 md:px-6 font-semibold">Fraud</th>
                <th className="py-3 px-5 md:px-6 font-semibold">Legit</th>
                <th className="py-3 px-5 md:px-6 font-semibold text-accent-green">TP / TN</th>
                <th className="py-3 px-5 md:px-6 font-semibold text-accent-red">FP / FN</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[rgba(255,255,255,0.05)]">
              {(data.timeseries || []).map((day: any) => (
                <tr key={day.date} className="hover:bg-[rgba(255,255,255,0.02)] transition-colors">
                  <td className="py-3.5 px-5 md:px-6 text-text-primary font-mono">{day.date}</td>
                  <td className="py-3.5 px-5 md:px-6 text-text-secondary">{(day.labeled_volume || 0).toLocaleString()}</td>
                  <td className="py-3.5 px-5 md:px-6 text-accent-red">{(day.FRAUD || 0).toLocaleString()}</td>
                  <td className="py-3.5 px-5 md:px-6 text-accent-green">{(day.LEGITIMATE || 0).toLocaleString()}</td>
                  <td className="py-3.5 px-5 md:px-6 text-text-secondary">
                    <span className="text-accent-red">{day.TP}</span> / <span className="text-accent-green">{day.TN}</span>
                  </td>
                  <td className="py-3.5 px-5 md:px-6 text-text-secondary">
                    <span className="text-accent-yellow">{day.FP}</span> / <span className="text-accent-red">{day.FN}</span>
                  </td>
                </tr>
              ))}
              {(data.timeseries || []).length === 0 && (
                <tr>
                  <td colSpan={6} className="py-8 text-center text-text-muted">No historical data available.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
