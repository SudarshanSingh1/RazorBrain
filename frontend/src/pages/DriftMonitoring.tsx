import { useEffect, useState } from 'react';
import { getDriftMetrics } from '../api';
import { AlertCircle, Target, ShieldAlert, BarChart2, CheckCircle, Database, AlertTriangle } from 'lucide-react';
import { Card, CardHeader, CardTitle, Badge } from '../components/ui';

export default function DriftMonitoring() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    getDriftMetrics()
      .then(res => {
        setData(res.data);
        setLoading(false);
      })
      .catch(() => {
        setError(true);
        setLoading(false);
      });
  }, []);

  if (loading) return (
    <div className="flex h-64 items-center justify-center space-x-2">
      <div className="w-4 h-4 bg-brand rounded-full animate-bounce"></div>
      <div className="w-4 h-4 bg-brand rounded-full animate-bounce delay-75"></div>
      <div className="w-4 h-4 bg-brand rounded-full animate-bounce delay-150"></div>
    </div>
  );
  
  if (error) return (
    <Card className="text-accent-red border-accent-red/30 bg-accent-red/5 flex items-center gap-3">
      <AlertCircle size={20} />
      Unable to load drift metrics.
    </Card>
  );

  return (
    <div className="space-y-4 md:space-y-6 animate-in fade-in duration-500">
      
      {data?.status === 'NOT_MEASURED' ? (
        <Card className="p-12 text-center text-text-muted">
          <Database size={48} className="mx-auto text-brand mb-4 opacity-50" />
          <h3 className="text-lg font-medium text-text-primary">Not Measured</h3>
          <p className="mt-2 text-[14px]">{data.reason || 'Not enough observations to measure drift.'}</p>
        </Card>
      ) : (
        <>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 md:gap-6">
            <Card className={`border ${
              data.overall_status === 'HIGH DRIFT SIGNAL' ? 'bg-accent-red/10 border-accent-red/40' :
              data.overall_status === 'MODERATE DRIFT SIGNAL' ? 'bg-accent-yellow/10 border-accent-yellow/40' :
              ''
            }`}>
              <p className="text-[11px] text-text-muted uppercase tracking-widest mb-1.5 font-semibold">Monitoring Status</p>
              <h2 className={`text-[20px] md:text-[24px] font-bold flex items-center gap-2 tracking-tight ${
                data.overall_status === 'HIGH DRIFT SIGNAL' ? 'text-accent-red' :
                data.overall_status === 'MODERATE DRIFT SIGNAL' ? 'text-accent-yellow' :
                'text-accent-green'
              }`}>
                {data.overall_status === 'HIGH DRIFT SIGNAL' && <AlertTriangle size={24} />}
                {data.overall_status === 'MODERATE DRIFT SIGNAL' && <AlertCircle size={24} />}
                {data.overall_status === 'NO MATERIAL SIGNAL' && <CheckCircle size={24} />}
                {data.overall_status}
              </h2>
            </Card>
            <Card>
              <p className="text-[11px] text-text-muted uppercase tracking-widest mb-1.5 font-semibold">Current Window</p>
              <h2 className="text-[24px] font-bold text-text-primary tracking-tight">
                {data.current_observations} <span className="text-[13px] font-medium text-text-secondary">observations</span>
              </h2>
            </Card>
            <Card>
              <p className="text-[11px] text-text-muted uppercase tracking-widest mb-1.5 font-semibold">Reference Population</p>
              <h2 className="text-[24px] font-bold text-text-primary tracking-tight">
                {data.reference_observations} <span className="text-[13px] font-medium text-text-secondary">observations</span>
              </h2>
            </Card>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 md:gap-6">
            <Card noPadding className="flex flex-col h-full">
              <div className="p-5 md:p-6 border-b border-border-subtle">
                <CardTitle icon={<BarChart2 size={16} />}>Feature Drift</CardTitle>
              </div>
              <div className="max-h-[400px] overflow-y-auto custom-scrollbar flex-1">
                <table className="w-full text-left text-[13px]">
                  <thead className="bg-bg-card-secondary text-text-muted sticky top-0 border-b border-border-subtle z-10">
                    <tr>
                      <th className="px-5 md:px-6 py-3 font-semibold uppercase tracking-wider text-[11px]">Feature</th>
                      <th className="px-5 md:px-6 py-3 font-semibold uppercase tracking-wider text-[11px]">PSI</th>
                      <th className="px-5 md:px-6 py-3 font-semibold uppercase tracking-wider text-[11px]">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[rgba(255,255,255,0.05)]">
                    {data.features?.sort((a: any, b: any) => b.psi - a.psi).map((f: any) => (
                      <tr key={f.feature} className="hover:bg-[rgba(255,255,255,0.02)] transition-colors">
                        <td className="px-5 md:px-6 py-3.5 text-text-primary">{f.feature}</td>
                        <td className="px-5 md:px-6 py-3.5 font-mono text-text-secondary">{f.psi.toFixed(4)}</td>
                        <td className="px-5 md:px-6 py-3.5">
                          <Badge variant={
                            f.status === 'HIGH' ? 'danger' :
                            f.status === 'MODERATE' ? 'warning' : 'default'
                          }>{f.status}</Badge>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>

            <div className="space-y-4 md:space-y-6">
              <Card>
                <CardHeader>
                  <CardTitle icon={<Target size={16} />}>Prediction Drift</CardTitle>
                </CardHeader>
                <div>
                  {data.prediction_drift?.status === 'NOT_MEASURED' ? (
                    <p className="text-[13px] text-text-muted">{data.prediction_drift.reason}</p>
                  ) : (
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-[11px] text-text-muted uppercase tracking-wider mb-1.5 font-semibold">Probability PSI</p>
                        <p className="text-[28px] font-bold font-mono text-text-primary leading-none">{data.prediction_drift?.psi?.toFixed(4)}</p>
                      </div>
                      <div>
                         <Badge variant={
                            data.prediction_drift?.status === 'HIGH' ? 'danger' :
                            data.prediction_drift?.status === 'MODERATE' ? 'warning' : 'success'
                          }>{data.prediction_drift?.status}</Badge>
                      </div>
                    </div>
                  )}
                </div>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle icon={<ShieldAlert size={16} />}>Decision Distribution</CardTitle>
                </CardHeader>
                <div>
                  {data.decision_drift?.status === 'NOT_MEASURED' ? (
                    <p className="text-[13px] text-text-muted">{data.decision_drift.reason}</p>
                  ) : (
                    <table className="w-full text-left text-[13px]">
                      <thead className="text-text-muted border-b border-border-subtle uppercase tracking-wider text-[11px]">
                        <tr>
                          <th className="pb-3 font-semibold">Decision</th>
                          <th className="pb-3 font-semibold text-right">Reference</th>
                          <th className="pb-3 font-semibold text-right">Current</th>
                          <th className="pb-3 font-semibold text-right">Change</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-[rgba(255,255,255,0.05)]">
                        {['ALLOW', 'REVIEW', 'BLOCK'].map((dec) => {
                          const stats = data.decision_drift?.[dec];
                          if (!stats) return null;
                          const change = stats.change;
                          return (
                            <tr key={dec}>
                              <td className="py-3.5 font-medium text-text-primary">{dec}</td>
                              <td className="py-3.5 text-right font-mono text-text-secondary">{(stats.reference * 100).toFixed(1)}%</td>
                              <td className="py-3.5 text-right font-mono text-text-primary">{(stats.current * 100).toFixed(1)}%</td>
                              <td className={`py-3.5 text-right font-mono font-medium ${
                                change > 0 ? 'text-accent-yellow' : change < 0 ? 'text-accent-green' : 'text-text-muted'
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
              </Card>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
