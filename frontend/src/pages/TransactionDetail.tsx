import { safeFormatDate } from "../utils/date";
import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { getTransactionDetail as getTransaction, recordFeedback } from '../api';
import { 
  ArrowLeft, ShieldCheck, AlertTriangle, Ban, Info, Cpu, 
  FileText, Activity, MapPin, SearchCheck
} from 'lucide-react';
import { 
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Cell 
} from 'recharts';
import { Card, CardHeader, CardTitle, Badge, Button } from '../components/ui';

export default function TransactionDetail() {
  const { id } = useParams();
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [label, setLabel] = useState<string>('FRAUD');
  const [notes, setNotes] = useState('');
  const [submittingFeedback, setSubmittingFeedback] = useState(false);
  
  const [feedbackError, setFeedbackError] = useState<string|null>(null);
  const [isReviewMode, setIsReviewMode] = useState(false);

  useEffect(() => {
    getTransaction(id as string)
      .then(res => {
        setData(res.data);
        const hasFeedback = !!(res.data.ground_truth || res.data.feedback);
        setIsReviewMode(res.data.decision === 'REVIEW' && !hasFeedback);
        setLoading(false);
      })
      .catch(() => {
        setError(true);
        setLoading(false);
      });
  }, [id]);

  const handleSubmitFeedback = async () => {
    setSubmittingFeedback(true);
    setFeedbackError(null);
    try {
      await recordFeedback(id as string, label as any, notes);
      setIsReviewMode(false);
      const res = await getTransaction(id as string);
      setData(res.data);
    } catch (err: any) {
      const isDuplicate = 
        err.response?.status === 409 || 
        err.response?.data?.error?.code === 'HTTP_409' || 
        (err.response?.data?.error?.message || '').includes('already exists');

      if (isDuplicate) {
        setIsReviewMode(false);
        const res = await getTransaction(id as string);
        setData(res.data);
        return;
      }
      const msg = err.response?.data?.error?.message || err.response?.data?.detail || err.message;
      setFeedbackError(msg || "Failed to record feedback");
    } finally {
      setSubmittingFeedback(false);
    }
  };

  if (loading) return (
    <div className="flex h-[calc(100vh-12rem)] items-center justify-center space-x-2">
      <div className="w-4 h-4 bg-brand rounded-full animate-bounce"></div>
      <div className="w-4 h-4 bg-brand rounded-full animate-bounce delay-75"></div>
      <div className="w-4 h-4 bg-brand rounded-full animate-bounce delay-150"></div>
    </div>
  );
  if (error || !data) return <div className="text-accent-red border border-accent-red bg-accent-red/20 p-4 rounded-md mt-6">Unable to load transaction details.</div>;

  const {
    transaction_id, timestamp, amount, decision, primary_risk_probability, 
    confidence_in_probability, explanation_text, provider, grounded,
    rule_evidence, model_evidence, context_data
  } = data;

  const feedback = data.feedback || (data.ground_truth ? {
    ground_truth_label: data.ground_truth,
    timestamp: data.labeled_at,
    reviewer_notes: data.notes,
    label_source: data.label_source,
    outcome: data.evaluation_outcome
  } : null);

  const getDecisionBadge = (decision: string) => {
    switch(decision) {
      case 'ALLOW': return <Badge variant="success" className="text-[13px] px-3 py-1 font-bold"><ShieldCheck size={16} className="mr-1.5"/> ALLOW</Badge>;
      case 'REVIEW': return <Badge variant="warning" className="text-[13px] px-3 py-1 font-bold"><AlertTriangle size={16} className="mr-1.5"/> REVIEW</Badge>;
      case 'BLOCK': return <Badge variant="danger" className="text-[13px] px-3 py-1 font-bold"><Ban size={16} className="mr-1.5"/> BLOCK</Badge>;
      default: return null;
    }
  };

  const shapData = Array.isArray(model_evidence) && model_evidence.length > 0 ? model_evidence.map((m: any) => ({ name: m.feature_name, contribution: m.shap_contribution })).sort((a: any, b: any) => Math.abs(b.contribution) - Math.abs(a.contribution)) : [];

  return (
    <div className="animate-in fade-in duration-500">
      
      {/* Header Area */}
      <div className="mb-6 flex items-center justify-between">
        <Link to="/transactions" className="flex items-center gap-2 text-text-muted hover:text-text-primary transition-colors text-[13px] font-medium">
          <ArrowLeft size={16} /> Back to Transactions
        </Link>
        <div className="text-[11px] text-text-muted bg-bg-card border border-border-subtle px-2.5 py-1 rounded-[6px] flex items-center gap-2">
          Assessment ID: <span className="font-mono text-text-secondary">{id}</span>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        
        {/* Left Col: Context */}
        <div className="space-y-6">
          <Card>
            <div className="flex items-start justify-between mb-6">
              <div>
                <p className="text-[11px] font-semibold text-text-muted uppercase tracking-wider mb-1">Transaction ID</p>
                <h1 className="text-[18px] font-mono text-text-primary tracking-tight">{transaction_id}</h1>
              </div>
              <div className="text-right">
                <p className="text-[11px] font-semibold text-text-muted uppercase tracking-wider mb-1">Amount</p>
                <h2 className="text-[24px] font-bold text-text-primary leading-none">${amount?.toFixed(2)}</h2>
              </div>
            </div>

            <div className="space-y-4 mb-6">
              <div className="flex items-center justify-between p-3.5 bg-bg-card-secondary border border-border-subtle rounded-[10px]">
                <span className="text-[12px] text-text-secondary font-medium">Model Probability</span>
                <span className="font-mono font-semibold text-text-primary">
                  {primary_risk_probability !== null ? primary_risk_probability.toFixed(4) : <span className="italic text-text-muted">Unavailable</span>}
                </span>
              </div>
              <div className="flex items-center justify-between p-3.5 bg-bg-card-secondary border border-border-subtle rounded-[10px]">
                <span className="text-[12px] text-text-secondary font-medium">Confidence Level</span>
                <Badge variant={confidence_in_probability === 'HIGH' ? 'default' : confidence_in_probability === 'LOW' || confidence_in_probability === 'NONE' ? 'danger' : 'secondary'} className={confidence_in_probability === 'HIGH' ? 'bg-brand/15 text-brand-bright border-brand/30' : ''}>
                  {confidence_in_probability}
                </Badge>
              </div>
            </div>

            <div className="pt-4 border-t border-border-subtle text-[12px] flex flex-col gap-2 text-text-secondary">
              <div className="flex justify-between">
                <span>Timestamp</span>
                <span className="font-mono">{safeFormatDate(timestamp)}</span>
              </div>
              <div className="flex justify-between items-center">
                <span>Location</span>
                <span className="flex items-center gap-1 font-medium"><MapPin size={12}/> {context_data?.ip_country || 'Unknown'}</span>
              </div>
            </div>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle icon={<Info size={16} />}>Final Decision</CardTitle>
            </CardHeader>
            <div className="flex items-center justify-center p-6 border border-border-subtle rounded-[10px] bg-bg-card-secondary">
              {getDecisionBadge(decision)}
            </div>

            {/* FEEDBACK UI */}
            {feedback ? (
              <div className="mt-4 p-4 border border-accent-green/30 bg-accent-green/5 rounded-[10px]">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2 text-accent-green">
                    <SearchCheck size={16} />
                    <span className="text-[13px] font-semibold tracking-wider uppercase">Feedback Recorded</span>
                  </div>
                  <span className="font-mono text-[10px] text-text-muted">{safeFormatDate(feedback.timestamp)}</span>
                </div>
                <div className="flex justify-between text-[13px] mt-3">
                  <span className="text-text-secondary font-medium">Ground Truth:</span>
                  <span className={`font-bold ${feedback.ground_truth_label === 'FRAUD' ? 'text-accent-red' : 'text-accent-green'}`}>{feedback.ground_truth_label}</span>
                </div>
                <div className="mt-2 text-[12px] text-text-secondary border-t border-accent-green/20 pt-2 italic">
                  "{feedback.reviewer_notes || 'No notes provided'}"
                </div>
              </div>
            ) : (
              decision === 'REVIEW' && (
                <div className="mt-4">
                  {!isReviewMode ? (
                    <Button fullWidth onClick={() => setIsReviewMode(true)}>
                      Record Review Decision
                    </Button>
                  ) : (
                    <div className="p-4 border border-brand/30 bg-brand/5 rounded-[10px] space-y-4">
                      <h3 className="text-[13px] font-semibold text-brand-bright uppercase tracking-wider mb-2">Manual Review</h3>
                      
                      {feedbackError && <div className="text-[12px] text-accent-red p-2 bg-accent-red/10 rounded border border-accent-red/30">{feedbackError}</div>}
                      
                      <div>
                        <label className="block text-[12px] text-text-secondary mb-1.5 font-medium">True Label</label>
                        <select 
                          value={label} 
                          onChange={(e) => setLabel(e.target.value)}
                          className="w-full bg-[rgba(9,24,45,0.8)] border border-[rgba(120,150,210,0.2)] rounded-[8px] px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-brand focus:shadow-[0_0_0_3px_rgba(47,128,237,0.12)]"
                        >
                          <option value="FRAUD">FRAUD (Reject)</option>
                          <option value="LEGITIMATE">LEGITIMATE (Approve)</option>
                        </select>
                      </div>
                      
                      <div>
                        <label className="block text-[12px] text-text-secondary mb-1.5 font-medium">Reviewer Notes</label>
                        <textarea 
                          value={notes}
                          onChange={(e) => setNotes(e.target.value)}
                          placeholder="Provide rationale for your decision..."
                          className="w-full bg-[rgba(9,24,45,0.8)] border border-[rgba(120,150,210,0.2)] rounded-[8px] px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-brand focus:shadow-[0_0_0_3px_rgba(47,128,237,0.12)] min-h-[80px]"
                        />
                      </div>
                      
                      <div className="flex gap-3 pt-2">
                        <Button 
                          onClick={handleSubmitFeedback} 
                          disabled={submittingFeedback}
                          className="flex-1"
                        >
                          {submittingFeedback ? 'Submitting...' : 'Submit Resolution'}
                        </Button>
                        <Button 
                          variant="ghost"
                          onClick={() => setIsReviewMode(false)}
                          disabled={submittingFeedback}
                          className="px-6 border border-border-subtle bg-bg-card-secondary"
                        >
                          Cancel
                        </Button>
                      </div>
                    </div>
                  )}
                </div>
              )
            )}
          </Card>
        </div>

        {/* Right Col: Evidence */}
        <div className="lg:col-span-2 space-y-6">

          {/* AI / EXPLANATION SECTION */}
          <Card className="border-brand/40 shadow-[0_0_15px_rgba(47,128,237,0.05)] bg-bg-card">
            <div className="flex items-center justify-between mb-4">
              <CardTitle icon={<Cpu size={16} />}>Engine Explanation</CardTitle>
              {provider && (
                <Badge variant={grounded ? 'default' : 'secondary'} className={grounded ? 'bg-brand/15 text-brand-bright border-brand/30' : ''}>
                  {provider === 'deterministic_fallback' ? 'Deterministic Fallback' : provider}
                </Badge>
              )}
            </div>
            {explanation_text ? (
              <p className="text-[13px] text-text-primary whitespace-pre-wrap leading-relaxed bg-[rgba(9,24,45,0.6)] p-4 rounded-lg border border-border-subtle tracking-wide relative">
                {explanation_text}
              </p>
            ) : (
              <div className="bg-[rgba(9,24,45,0.6)] p-4 rounded-lg border border-border-subtle text-text-muted text-[13px] italic">
                No stored explanation generated for this assessment.
              </div>
            )}
            {provider && <p className="text-[10px] text-brand-bright/70 mt-3 uppercase tracking-widest font-bold">{grounded ? 'Grounded explicitly in stored evidence' : 'Provider status unverified'}</p>}
          </Card>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            
            {/* RULE EVIDENCE */}
            <Card>
              <CardHeader>
                <CardTitle icon={<FileText size={16}/>}>Rule Evidence</CardTitle>
              </CardHeader>
              <div className="space-y-2.5">
                {!rule_evidence || (rule_evidence || []).length === 0 ? (
                  <p className="text-text-muted text-[13px] py-4 italic border border-border-subtle border-dashed rounded-lg text-center bg-bg-card-secondary/50">No rules triggered.</p>
                ) : (
                  (rule_evidence || []).map((rule: any, i: number) => {
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
                      <div key={i} className="flex items-center justify-between p-3 border border-border-subtle bg-bg-card-secondary rounded-[8px]">
                        <div className="flex items-center gap-2.5">
                          <AlertTriangle size={14} className={iconColor} />
                          <span className="text-[13px] font-medium text-text-primary">{rule.rule_id}</span>
                        </div>
                        <Badge variant={variant}>{rule.severity}</Badge>
                      </div>
                    )
                  })
                )}
              </div>
            </Card>

            {/* Behavioral */}
            <Card>
              <CardHeader>
                <CardTitle icon={<Activity size={16}/>}>Behavioral Signals</CardTitle>
              </CardHeader>
              <div className="grid grid-cols-2 gap-y-4 gap-x-2 text-[12px]">
                <div><p className="text-text-muted mb-0.5">Account Age</p><p className="text-text-primary font-medium">{context_data?.customer_account_age_days ?? <span className="text-text-secondary italic font-normal">Unavailable</span>}</p></div>
                <div><p className="text-text-muted mb-0.5">Amt Deviation</p><p className="text-text-primary font-medium">{context_data?.amount_deviation !== undefined ? context_data.amount_deviation.toFixed(2) : <span className="text-text-secondary italic font-normal">Unavailable</span>}</p></div>
                <div><p className="text-text-muted mb-0.5">Prev Txns</p><p className="text-text-primary font-medium">{context_data?.previous_transaction_count ?? <span className="text-text-secondary italic font-normal">Unavailable</span>}</p></div>
                <div><p className="text-text-muted mb-0.5">Prev Fraud</p><p className="text-text-primary font-medium">{context_data?.previous_fraud_count ?? <span className="text-text-secondary italic font-normal">Unavailable</span>}</p></div>
                <div><p className="text-text-muted mb-0.5">Txns (24h)</p><p className="text-text-primary font-medium">{context_data?.txns_last_24h ?? <span className="text-text-secondary italic font-normal">Unavailable</span>}</p></div>
                <div><p className="text-text-muted mb-0.5">Merchant Fraud</p><p className="text-text-primary font-medium">{context_data?.merchant_fraud_rate !== undefined ? context_data.merchant_fraud_rate.toFixed(4) : <span className="text-text-secondary italic font-normal">Unavailable</span>}</p></div>
              </div>
            </Card>

          </div>

          {/* MODEL EVIDENCE */}
          <Card>
            <CardHeader>
              <CardTitle>Model Evidence (SHAP)</CardTitle>
            </CardHeader>
            {shapData.length > 0 ? (
              <div className="h-[260px] w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={shapData} layout="vertical" margin={{ top: 5, right: 30, left: 120, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.08)" horizontal={false} />
                    <XAxis type="number" stroke="#9eacc4" fontSize={11} tickLine={false} axisLine={false} />
                    <YAxis dataKey="name" type="category" stroke="#9eacc4" fontSize={11} tickLine={false} axisLine={false} />
                    <Tooltip 
                      cursor={{ fill: 'rgba(255,255,255,0.04)' }}
                      contentStyle={{ backgroundColor: '#0d1d33', borderColor: 'rgba(110,150,210,0.16)', color: '#f5f8ff', borderRadius: '8px' }}
                      formatter={(val: any) => val.toFixed(4)}
                    />
                    <Bar dataKey="contribution" radius={4} barSize={16}>
                      {
                        shapData.map((entry: any, index: number) => (
                          <Cell key={`cell-${index}`} fill={entry.contribution > 0 ? '#ff5c70' : '#35d39e'} />
                        ))
                      }
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
                <div className="flex flex-col md:flex-row md:items-center justify-between mt-4 gap-3">
                  <p className="text-[11px] text-text-muted italic max-w-xl">Positive contributions push toward higher risk probability. Negative contributions push toward lower risk. SHAP values do not explicitly decide ALLOW/BLOCK.</p>
                  <div className="flex items-center gap-4 text-[10px] uppercase font-bold tracking-wider">
                    <div className="flex items-center gap-1.5 text-accent-red"><span className="w-2.5 h-2.5 rounded-sm bg-accent-red"></span> Positive contribution</div>
                    <div className="flex items-center gap-1.5 text-accent-green"><span className="w-2.5 h-2.5 rounded-sm bg-accent-green"></span> Negative contribution</div>
                  </div>
                </div>
              </div>
            ) : (
              <div className="py-8 flex items-center justify-center text-text-muted text-[13px] italic border border-border-subtle border-dashed rounded-lg bg-bg-card-secondary/30">
                No stored SHAP evidence is available for this assessment.
              </div>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}
