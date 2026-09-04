import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { getTransactionDetail, getServingTransactionDetail, recordFeedback } from '../api';
import { ArrowLeft, ShieldCheck, AlertTriangle, Ban, AlertCircle, Cpu, FileText, Activity, Layers, CheckCircle } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Cell } from 'recharts';
import ServingTransactionDetail from './ServingTransactionDetail';

export default function TransactionDetail() {
  const { id } = useParams<{ id: string }>();
  const [submittingFeedback, setSubmittingFeedback] = useState(false);
  const [feedbackError, setFeedbackError] = useState<string | null>(null);
  const [feedbackSuccess, setFeedbackSuccess] = useState<string | null>(null);
  const [showConfirm, setShowConfirm] = useState<'FRAUD' | 'LEGITIMATE' | null>(null);

  const handleFeedback = async (groundTruth: 'FRAUD' | 'LEGITIMATE') => {
    setSubmittingFeedback(true);
    setFeedbackError(null);
    setFeedbackSuccess(null);
    try {
      const res = await recordFeedback(id!, groundTruth);
      setData((prev: any) => ({
        ...prev,
        ground_truth: res.data.ground_truth,
        label_source: res.data.label_source,
        evaluation_outcome: res.data.evaluation_outcome,
        labeled_at: res.data.labeled_at
      }));
      setFeedbackSuccess(`Successfully recorded ${groundTruth} as ground truth.`);
      setShowConfirm(null);
    } catch (err: any) {
      setFeedbackError(err.response?.data?.detail || err.message || 'Failed to submit feedback.');
    } finally {
      setSubmittingFeedback(false);
    }
  };

  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | boolean>(false);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    const isServing = id.includes('pay_') || id.startsWith('order_');
    
    if (isServing) {
      getServingTransactionDetail(id)
        .then(res => {
          setData({ ...res.data, isServing: true });
          setLoading(false);
        })
        .catch(err => {
          setError(err.response?.data?.detail || err.message || "Failed to load serving assessment.");
          setLoading(false);
        });
    } else {
      getTransactionDetail(id)
        .then(res => {
          setData({ ...res.data, isServing: false });
          setLoading(false);
        })
        .catch(err => {
          setError(err.response?.data?.detail || err.message || "Unable to load investigation details.");
          setLoading(false);
        });
    }
  }, [id]);

  if (loading) return <div className="text-slate-400 animate-pulse p-6">Loading assessment details...</div>;
  if (error || !data) return <div className="text-red-400 border border-red-900 bg-red-950/20 p-4 rounded-md m-6">{typeof error === 'string' ? error : "Unable to load investigation details."}</div>;

  if (data.isServing) {
    return <ServingTransactionDetail data={data} />;
  }

  const {
    assessment_id, transaction_id, timestamp, amount, customer_id, merchant_id, payment_method,
    primary_risk_probability, confidence_in_probability, decision, decision_reason,
    rule_evidence, model_evidence, context_data, explanation_text, provider, grounded
  } = data;

  const shapData = (model_evidence || []).map((ev: any) => ({
    name: ev.feature_name,
    contribution: ev.shap_contribution
  })).sort((a: any, b: any) => Math.abs(b.contribution) - Math.abs(a.contribution));

  const getDecisionIcon = (decision: string) => {
    switch(decision) {
      case 'ALLOW': return <ShieldCheck className="text-emerald-500" size={32}/>;
      case 'REVIEW': return <AlertTriangle className="text-amber-500" size={32}/>;
      case 'BLOCK': return <Ban className="text-rose-500" size={32}/>;
      default: return <AlertCircle className="text-slate-500" size={32}/>;
    }
  };
  
  const getDecisionColor = (decision: string) => {
    switch(decision) {
      case 'ALLOW': return 'text-emerald-500';
      case 'REVIEW': return 'text-amber-500';
      case 'BLOCK': return 'text-rose-500';
      default: return 'text-slate-500';
    }
  };

  const getDecisionBg = (decision: string) => {
    switch(decision) {
      case 'ALLOW': return 'bg-emerald-950/30 border-emerald-900/50';
      case 'REVIEW': return 'bg-amber-950/30 border-amber-900/50';
      case 'BLOCK': return 'bg-rose-950/30 border-rose-900/50';
      default: return 'bg-slate-900 border-slate-800';
    }
  };

  const getRuleIcon = (severity: string) => {
    if (severity === 'HIGH') return <Ban className="text-rose-500" size={16}/>;
    if (severity === 'MEDIUM') return <AlertTriangle className="text-amber-500" size={16}/>;
    return <AlertCircle className="text-blue-500" size={16}/>;
  };

  return (
    <div className="p-8 max-w-7xl mx-auto pb-24">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <Link to="/transactions" className="inline-flex items-center gap-1 text-slate-500 hover:text-slate-300 text-sm mb-3 transition-colors">
            <ArrowLeft size={14}/> Back to Explorer
          </Link>
          <h1 className="text-2xl font-bold text-slate-100 font-mono tracking-tight flex items-center gap-3">
            Investigation: {transaction_id}
          </h1>
          <p className="text-slate-500 mt-1 text-sm">Assessment ID: {assessment_id}</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        
        {/* Left Column */}
        <div className="space-y-6">
          {/* A. DECISION SUMMARY */}
          <div className={`border rounded-xl p-6 ${getDecisionBg(decision)}`}>
            <div className="flex items-start justify-between">
              <div>
                <p className="text-xs text-slate-400 uppercase tracking-wider font-semibold mb-1">Final Decision</p>
                <p className={`text-4xl font-bold ${getDecisionColor(decision)}`}>{decision || 'UNKNOWN'}</p>
              </div>
              <div className="p-3 bg-black/20 rounded-xl">
                {getDecisionIcon(decision)}
              </div>
            </div>
            
            <div className="mt-6 pt-6 border-t border-slate-700/30 space-y-4">
              <div className="flex justify-between items-center">
                <span className="text-sm text-slate-400">Primary Risk Probability</span>
                <span className="text-sm font-medium text-slate-200">
                  {primary_risk_probability !== null && primary_risk_probability !== undefined 
                    ? `${(primary_risk_probability * 100).toFixed(2)}%` 
                    : <span className="text-slate-500 italic">Unavailable</span>}
                </span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-sm text-slate-400">Confidence</span>
                <span className="text-sm font-medium text-slate-200">
                  {confidence_in_probability ? confidence_in_probability.replace('_', ' ').toUpperCase() : <span className="text-slate-500 italic">Unavailable</span>}
                </span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-sm text-slate-400">Evidence Completeness</span>
                <span className="text-sm font-medium text-emerald-400 flex items-center gap-1"><CheckCircle size={14}/> Recorded</span>
              </div>
            </div>
          </div>

          {/* F. TRANSACTION CONTEXT */}
          <div className="bg-[#0f172a] border border-slate-800/60 p-5 rounded-xl shadow-sm">
            <h2 className="text-sm font-semibold text-slate-200 uppercase tracking-wider mb-4 flex items-center gap-2"><Layers size={16}/> Transaction Context</h2>
            <div className="space-y-3">
              <div className="flex justify-between"><span className="text-xs text-slate-500">Timestamp</span><span className="text-xs text-slate-300">{new Date(timestamp).toLocaleString()}</span></div>
              <div className="flex justify-between"><span className="text-xs text-slate-500">Amount</span><span className="text-xs font-mono text-slate-200">${amount?.toFixed(2) || 'Unavailable'}</span></div>
              <div className="flex justify-between"><span className="text-xs text-slate-500">Currency</span><span className="text-xs font-mono text-slate-300">{context_data?.currency || 'Unavailable'}</span></div>
              <div className="flex justify-between"><span className="text-xs text-slate-500">Customer ID</span><span className="text-xs font-mono text-slate-300">{customer_id || 'Unavailable'}</span></div>
              <div className="flex justify-between"><span className="text-xs text-slate-500">Merchant ID</span><span className="text-xs font-mono text-slate-300">{merchant_id || 'Unavailable'}</span></div>
              <div className="flex justify-between"><span className="text-xs text-slate-500">Payment Method</span><span className="text-xs text-slate-300">{payment_method || 'Unavailable'}</span></div>
              <div className="flex justify-between"><span className="text-xs text-slate-500">IP / Location</span><span className="text-xs text-slate-300">{context_data?.ip_address || 'Unavailable'}</span></div>
            </div>
          </div>

          {/* G. AUDIT INFORMATION */}
          <div className="bg-[#0f172a] border border-slate-800/60 p-5 rounded-xl shadow-sm">
            <h2 className="text-sm font-semibold text-slate-200 uppercase tracking-wider mb-4">Audit Information</h2>
            <div className="space-y-3">
              <div className="flex justify-between"><span className="text-xs text-slate-500">Persistence Status</span><span className="text-xs text-emerald-500">Persisted</span></div>
              <div className="flex justify-between"><span className="text-xs text-slate-500">Explanation Provider</span><span className="text-xs text-slate-300">{provider || 'Unavailable'}</span></div>
            </div>
          </div>
        </div>

        {/* Right Column */}
        <div className="lg:col-span-2 space-y-6">
          
          {/* B. WHY THIS DECISION? */}
          <div className={`border p-6 rounded-xl shadow-sm ${getDecisionBg(decision)}`}>
            <h2 className={`text-sm font-bold uppercase tracking-wider mb-2 flex items-center gap-2 ${getDecisionColor(decision)}`}>
              {getDecisionIcon(decision)}
              Why this transaction was {decision === 'ALLOW' ? 'allowed' : decision === 'REVIEW' ? 'reviewed' : decision === 'BLOCK' ? 'blocked' : 'flagged'}
            </h2>
            <p className="text-slate-300 text-sm mt-4 bg-black/20 p-4 rounded-lg font-medium border border-white/5">
              {decision_reason || <span className="italic text-slate-500">No deterministic decision reason recorded by the engine.</span>}
            </p>
          </div>
          
          
          {/* F. HUMAN REVIEW / FEEDBACK */}
          {decision === 'REVIEW' && (
            <div className="bg-[#0f172a] border border-blue-900/30 shadow-blue-900/5 p-6 rounded-xl shadow-sm mb-6">
              
              {data.review_priority && (
                <div className="mb-6 pb-6 border-b border-slate-800">
                  <h2 className="text-sm font-semibold text-amber-500 uppercase tracking-wider flex items-center gap-2 mb-3">
                    <AlertTriangle size={16}/> Operational Review Priority
                  </h2>
                  <div className="bg-slate-900/50 p-4 rounded-lg border border-slate-800/80">
                    <div className="flex items-start justify-between">
                      <div>
                        <div className="flex items-center gap-2 mb-2">
                          <span className={`px-2 py-0.5 rounded text-xs font-bold ${
                            data.review_priority.tier === 'CRITICAL' ? 'bg-red-900/40 text-red-400' :
                            data.review_priority.tier === 'HIGH' ? 'bg-orange-900/40 text-orange-400' :
                            'bg-blue-900/40 text-blue-400'
                          }`}>
                            {data.review_priority.tier}
                          </span>
                        </div>
                        <ul className="list-disc pl-5 text-sm text-slate-300 space-y-1">
                          {data.review_priority.reasons.map((r: string, idx: number) => (
                            <li key={idx}>{r}</li>
                          ))}
                        </ul>
                        <p className="text-xs text-slate-500 mt-3">
                          This priority affects review ordering only. It does not change the RazorBrain decision.
                        </p>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              <div className="flex items-center justify-between mb-4">

                <h2 className="text-sm font-semibold text-blue-400 uppercase tracking-wider flex items-center gap-2"><CheckCircle size={16}/> Human Review Outcome</h2>
              </div>
              
              {data.ground_truth ? (
                <div className="bg-slate-900/50 p-4 rounded-lg border border-slate-800">
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                    <div><span className="text-slate-500 block text-xs">Ground Truth</span><span className={`font-semibold ${data.ground_truth === 'FRAUD' ? 'text-red-400' : 'text-emerald-400'}`}>{data.ground_truth}</span></div>
                    <div><span className="text-slate-500 block text-xs">Source</span><span className="text-slate-300">{data.label_source}</span></div>
                    <div><span className="text-slate-500 block text-xs">Evaluation</span><span className="text-slate-300">{data.evaluation_outcome}</span></div>
                    <div><span className="text-slate-500 block text-xs">Labeled At</span><span className="text-slate-300">{new Date(data.labeled_at).toLocaleString()}</span></div>
                  </div>
                </div>
              ) : (
                <div className="space-y-4">
                  <p className="text-sm text-slate-400">
                    Recording this outcome adds ground-truth feedback for evaluation. It does not change the original RazorBrain decision.
                  </p>
                  
                  {feedbackError && <div className="text-red-400 text-sm bg-red-950/20 p-3 rounded border border-red-900">{feedbackError}</div>}
                  {feedbackSuccess && <div className="text-emerald-400 text-sm bg-emerald-950/20 p-3 rounded border border-emerald-900">{feedbackSuccess}</div>}

                  {!showConfirm ? (
                    <div className="flex gap-4">
                      <button 
                        onClick={() => setShowConfirm('FRAUD')}
                        disabled={submittingFeedback}
                        className="bg-red-500/10 hover:bg-red-500/20 text-red-400 border border-red-500/30 px-4 py-2 rounded font-medium transition-colors disabled:opacity-50"
                      >
                        Confirm Fraud
                      </button>
                      <button 
                        onClick={() => setShowConfirm('LEGITIMATE')}
                        disabled={submittingFeedback}
                        className="bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 px-4 py-2 rounded font-medium transition-colors disabled:opacity-50"
                      >
                        Confirm Legitimate
                      </button>
                    </div>
                  ) : (
                    <div className="bg-slate-900 border border-slate-700 p-4 rounded-lg">
                      <p className="text-slate-300 text-sm mb-4">
                        You are about to record <strong className={showConfirm === 'FRAUD' ? 'text-red-400' : 'text-emerald-400'}>{showConfirm}</strong> as the ground-truth outcome for this assessment. This will be used in evaluation analytics and cannot currently be changed.
                      </p>
                      <div className="flex gap-3">
                        <button 
                          onClick={() => handleFeedback(showConfirm)}
                          disabled={submittingFeedback}
                          className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded font-medium transition-colors disabled:opacity-50 text-sm"
                        >
                          {submittingFeedback ? 'Submitting...' : 'Confirm'}
                        </button>
                        <button 
                          onClick={() => setShowConfirm(null)}
                          disabled={submittingFeedback}
                          className="bg-slate-800 hover:bg-slate-700 text-slate-300 px-4 py-2 rounded font-medium transition-colors disabled:opacity-50 text-sm"
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* E. AI / EXPLANATION SECTION */}

          <div className="bg-[#0f172a] border border-indigo-900/30 shadow-indigo-900/5 p-6 rounded-xl shadow-sm">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-semibold text-indigo-400 uppercase tracking-wider flex items-center gap-2"><Cpu size={16}/> Engine Explanation</h2>
              {provider && (
                <span className={`px-2 py-0.5 rounded text-[10px] uppercase font-bold tracking-wider ${grounded ? 'bg-indigo-900/40 text-indigo-400 border border-indigo-800/50' : 'bg-slate-800 text-slate-400 border border-slate-700'}`}>
                  {provider === 'deterministic_fallback' ? 'Deterministic Fallback' : provider}
                </span>
              )}
            </div>
            {explanation_text ? (
              <p className="text-sm text-slate-300 whitespace-pre-wrap leading-relaxed bg-[#020617] p-4 rounded-lg border border-slate-800/60 font-serif tracking-wide">
                {explanation_text}
              </p>
            ) : (
              <div className="bg-[#020617] p-4 rounded-lg border border-slate-800/60 text-slate-500 text-sm italic">
                No stored explanation generated for this assessment.
              </div>
            )}
            {provider && <p className="text-[10px] text-indigo-500/70 mt-3 uppercase tracking-widest font-bold">{grounded ? 'Grounded explicitly in stored evidence' : 'Provider status unverified'}</p>}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            
            {/* C. RULE EVIDENCE */}
            <div className="bg-[#0f172a] border border-slate-800/60 p-5 rounded-xl shadow-sm">
              <h2 className="text-sm font-semibold text-slate-200 uppercase tracking-wider mb-4 flex items-center gap-2"><FileText size={16}/> Rule Evidence</h2>
              <div className="space-y-3">
                {!rule_evidence || rule_evidence.length === 0 ? (
                  <p className="text-slate-500 text-sm py-4 italic border border-slate-800 border-dashed rounded-lg text-center">No rules triggered.</p>
                ) : (
                  rule_evidence.map((rule: any, i: number) => (
                    <div key={i} className="flex items-center justify-between p-3 border border-slate-800/60 bg-[#0B1120] rounded-lg">
                      <div className="flex items-center gap-2.5">
                        {getRuleIcon(rule.severity)}
                        <span className="text-sm font-medium text-slate-300">{rule.rule_id}</span>
                      </div>
                      <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded-sm uppercase tracking-wider ${
                      rule.severity === 'HIGH' ? 'bg-rose-900/40 text-rose-400' :
                      rule.severity === 'MEDIUM' ? 'bg-amber-900/40 text-amber-400' : 'bg-blue-900/40 text-blue-400'
                    }`}>{rule.severity}</span>
                    </div>
                  ))
                )}
              </div>
            </div>

            {/* Behavioral */}
            <div className="bg-[#0f172a] border border-slate-800/60 p-5 rounded-xl shadow-sm">
              <h2 className="text-sm font-semibold text-slate-200 uppercase tracking-wider mb-4 flex items-center gap-2"><Activity size={16}/> Behavioral Signals</h2>
              <div className="grid grid-cols-2 gap-y-4 gap-x-2 text-xs">
                <div><p className="text-slate-500">Account Age</p><p className="text-slate-200 font-medium">{context_data?.customer_account_age_days ?? <span className="text-slate-600 italic font-normal">Unavailable</span>}</p></div>
                <div><p className="text-slate-500">Amt Deviation</p><p className="text-slate-200 font-medium">{context_data?.amount_deviation !== undefined ? context_data.amount_deviation.toFixed(2) : <span className="text-slate-600 italic font-normal">Unavailable</span>}</p></div>
                <div><p className="text-slate-500">Prev Txns</p><p className="text-slate-200 font-medium">{context_data?.previous_transaction_count ?? <span className="text-slate-600 italic font-normal">Unavailable</span>}</p></div>
                <div><p className="text-slate-500">Prev Fraud</p><p className="text-slate-200 font-medium">{context_data?.previous_fraud_count ?? <span className="text-slate-600 italic font-normal">Unavailable</span>}</p></div>
                <div><p className="text-slate-500">Txns (24h)</p><p className="text-slate-200 font-medium">{context_data?.txns_last_24h ?? <span className="text-slate-600 italic font-normal">Unavailable</span>}</p></div>
                <div><p className="text-slate-500">Merchant Fraud</p><p className="text-slate-200 font-medium">{context_data?.merchant_fraud_rate !== undefined ? context_data.merchant_fraud_rate.toFixed(4) : <span className="text-slate-600 italic font-normal">Unavailable</span>}</p></div>
              </div>
            </div>

          </div>

          {/* D. MODEL EVIDENCE */}
          <div className="bg-[#0f172a] border border-slate-800/60 p-5 rounded-xl shadow-sm">
            <h2 className="text-sm font-semibold text-slate-200 uppercase tracking-wider mb-4">Model Evidence (SHAP)</h2>
            {shapData.length > 0 ? (
              <div className="h-64 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={shapData} layout="vertical" margin={{ top: 5, right: 30, left: 120, bottom: 5 }}>
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
                <div className="flex items-center justify-between mt-4">
                  <p className="text-[10px] text-slate-500 italic max-w-xl">Positive contributions push toward higher risk probability. Negative contributions push toward lower risk. SHAP values do not explicitly decide ALLOW/BLOCK.</p>
                  <div className="flex items-center gap-4 text-[10px] uppercase font-semibold">
                    <div className="flex items-center gap-1.5 text-rose-500"><span className="w-2 h-2 rounded bg-rose-500"></span> Positive contribution</div>
                    <div className="flex items-center gap-1.5 text-emerald-500"><span className="w-2 h-2 rounded bg-emerald-500"></span> Negative contribution</div>
                  </div>
                </div>
              </div>
            ) : (
              <div className="py-8 flex items-center justify-center text-slate-500 text-sm italic border border-slate-800 border-dashed rounded-lg">
                No stored SHAP evidence is available for this assessment.
              </div>
            )}
          </div>

        </div>
      </div>
    </div>
  );
}
