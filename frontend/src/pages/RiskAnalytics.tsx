import { useEffect, useState } from 'react';
import { getRiskDistribution, getRuleIntelligence, getProbabilityAmount, getShapIntelligence } from '../api';
import { AlertCircle, Target, ShieldAlert, BarChart2, Activity } from 'lucide-react';
import { 
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
  ScatterChart, Scatter, ZAxis
} from 'recharts';
import { Card, CardHeader, CardTitle, Badge } from '../components/ui';

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
      Unable to load risk analytics.
    </Card>
  );

  const totalRules = ruleData.reduce((acc, r) => acc + r.count, 0);

  return (
    <div className="space-y-4 md:space-y-6 animate-in fade-in duration-500">
      
      {/* Top row: Prob Dist and SHAP */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 md:gap-6">
        <Card>
          <CardHeader>
            <CardTitle icon={<BarChart2 size={16} />}>Calibrated Risk Probability</CardTitle>
          </CardHeader>
          <p className="text-[12px] text-text-secondary mt-1 mb-6">Distribution of stored calibrated model probabilities.</p>
          <div className="h-[260px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={distData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.08)" vertical={false} />
                <XAxis dataKey="name" stroke="#9eacc4" fontSize={11} tickLine={false} axisLine={false} />
                <YAxis stroke="#9eacc4" fontSize={11} tickLine={false} axisLine={false} />
                <Tooltip 
                  cursor={{ fill: 'rgba(255,255,255,0.04)' }}
                  contentStyle={{ backgroundColor: '#0d1d33', borderColor: 'rgba(110,150,210,0.16)', color: '#f5f8ff', borderRadius: '8px' }}
                />
                <Bar dataKey="count" fill="url(#blueGradient)" radius={[4, 4, 0, 0]} />
                <defs>
                  <linearGradient id="blueGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#3b9cff" />
                    <stop offset="100%" stopColor="#2f80ed" />
                  </linearGradient>
                </defs>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <p className="text-[11px] text-text-muted mt-4 italic">Based on stored calibrated probabilities with non-null values.</p>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle icon={<Target size={16} />}>Model Evidence — Top Contributors</CardTitle>
          </CardHeader>
          <p className="text-[12px] text-text-secondary mt-1 mb-6">Global mean absolute SHAP magnitude per feature.</p>
          <div className="h-[260px] w-full">
            {shapData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={shapData} layout="vertical" margin={{ top: 5, right: 10, left: 100, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.08)" horizontal={false} />
                  <XAxis type="number" stroke="#9eacc4" fontSize={11} tickLine={false} axisLine={false} />
                  <YAxis dataKey="feature_name" type="category" stroke="#9eacc4" fontSize={11} tickLine={false} axisLine={false} />
                  <Tooltip 
                    cursor={{ fill: 'rgba(255,255,255,0.04)' }}
                    contentStyle={{ backgroundColor: '#0d1d33', borderColor: 'rgba(110,150,210,0.16)', color: '#f5f8ff', borderRadius: '8px' }}
                    formatter={(val: any) => val.toFixed(4)}
                  />
                  <Bar dataKey="mean_abs_shap" fill="#1769d1" radius={[0, 4, 4, 0]} barSize={14} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full flex items-center justify-center text-text-muted text-[13px]">No stored SHAP evidence is available.</div>
            )}
          </div>
          <p className="text-[11px] text-text-muted mt-4 italic">SHAP values describe model contribution and are not independent risk points.</p>
        </Card>
      </div>

      {/* Bottom row: Rule Intel and Scatter */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 md:gap-6">
        <Card>
          <CardHeader>
            <CardTitle icon={<ShieldAlert size={16} />}>Rule Intelligence</CardTitle>
          </CardHeader>
          <p className="text-[12px] text-text-secondary mt-1 mb-6">Triggered deterministic evidence counts.</p>
          <div className="space-y-2.5 max-h-[300px] overflow-y-auto pr-2 custom-scrollbar">
            {ruleData.length === 0 ? (
              <p className="text-text-muted text-[13px] py-10 text-center">No rules have triggered.</p>
            ) : (
              ruleData.map((rule, idx) => {
                const pct = totalRules > 0 ? ((rule.count / totalRules) * 100).toFixed(1) : 0;
                
                let variant: 'danger' | 'warning' | 'default' = 'default';
                let iconColor = 'text-brand';
                if (rule.severity === 'HIGH') {
                  variant = 'danger';
                  iconColor = 'text-accent-red';
                } else if (rule.severity === 'MEDIUM') {
                  variant = 'warning';
                  iconColor = 'text-accent-yellow';
                }

                return (
                <div key={`${rule.rule_id}-${idx}`} className="flex items-center justify-between p-3.5 border border-border-subtle bg-bg-card-secondary rounded-[10px] group hover:border-brand/40 transition-colors">
                  <div className="flex items-center gap-3">
                    <AlertCircle size={16} className={iconColor} />
                    <div>
                      <p className="text-[13px] font-medium text-text-primary">{rule.rule_id}</p>
                      <p className="text-[11px] text-text-muted mt-0.5">{pct}% of total triggers</p>
                    </div>
                  </div>
                  <div className="text-right flex flex-col items-end gap-1.5">
                    <p className="text-[14px] font-bold text-text-primary">{rule.count.toLocaleString()}</p>
                    <Badge variant={variant}>{rule.severity}</Badge>
                  </div>
                </div>
              )})
            )}
          </div>
          <p className="text-[11px] text-text-muted mt-5 italic">Rule counts represent stored triggered rule evidence.</p>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle icon={<Activity size={16} />}>Observed amount vs calibrated probability</CardTitle>
          </CardHeader>
          <p className="text-[12px] text-text-secondary mt-1 mb-4">Observed relationship between transaction amount and model probability.</p>
          <div className="text-[11px] text-text-muted mb-6 italic border border-border-subtle p-2.5 rounded-[8px] bg-bg-card-secondary/50 inline-block">
            Bounded analytical sample (max 1000 latest observations).
          </div>
          <div className="h-[240px] w-full">
            {scatterData.length > 5 ? (
              <ResponsiveContainer width="100%" height="100%">
                <ScatterChart margin={{ top: 10, right: 10, bottom: 10, left: -20 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.08)" />
                  <XAxis type="number" dataKey="x" name="Amount" unit="$" stroke="#9eacc4" fontSize={11} tickLine={false} axisLine={false} />
                  <YAxis type="number" dataKey="y" name="Probability" stroke="#9eacc4" fontSize={11} tickLine={false} axisLine={false} />
                  <ZAxis type="number" range={[15, 15]} />
                  <Tooltip 
                    cursor={{ strokeDasharray: '3 3' }}
                    contentStyle={{ backgroundColor: '#0d1d33', borderColor: 'rgba(110,150,210,0.16)', color: '#f5f8ff', borderRadius: '8px' }}
                    formatter={(value: any, name: any) => name === 'Amount' ? `$${value.toFixed(2)}` : value.toFixed(4)}
                  />
                  <Scatter name="Transactions" data={scatterData} fill="#3b9cff" fillOpacity={0.6} />
                </ScatterChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full flex items-center justify-center text-text-muted text-[13px]">Insufficient paired observations.</div>
            )}
          </div>
        </Card>
      </div>
    </div>
  );
}
