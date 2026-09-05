import { useState } from 'react';
import { Card, CardHeader, CardTitle, Button, Badge } from '../components/ui';
import { CreditCard, AlertTriangle, Play, ShieldAlert, CheckCircle, SearchCheck } from 'lucide-react';
import { createTestOrder, assessTestPayment } from '../services/api';

const RAZORPAY_KEY_ID = import.meta.env.VITE_RAZORPAY_KEY_ID || 'rzp_test_TXQNLlr2VVcfZi';

const loadRazorpayScript = () => {
  return new Promise((resolve) => {
    const script = document.createElement('script');
    script.src = 'https://checkout.razorpay.com/v1/checkout.js';
    script.onload = () => resolve(true);
    script.onerror = () => resolve(false);
    document.body.appendChild(script);
  });
};

export function RazorpayTest() {
  const [amount, setAmount] = useState('100.00');
  const [currency, setCurrency] = useState('INR');
  const [customerId, setCustomerId] = useState('cust_test123@example.com');
  const [merchantId, setMerchantId] = useState('merch_test1');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  const [order, setOrder] = useState<any>(null);
  const [paymentId, setPaymentId] = useState('');
  const [assessment, setAssessment] = useState<any>(null);

  const handleCreateOrder = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setOrder(null);
    setAssessment(null);
    setPaymentId('');

    try {
      const subunitAmount = Math.round(parseFloat(amount) * 100);
      const res = await createTestOrder({
        amount: subunitAmount,
        currency: currency,
        receipt: `rcpt_${Date.now()}`,
        notes: {
          customer_id: customerId,
          merchant_id: merchantId
        }
      });
      setOrder(res.data);
    } catch (err: any) {
      const msg = err.response?.data?.error?.message || err.response?.data?.detail || err.message;
      setError(msg || "Failed to create order");
    } finally {
      setLoading(false);
    }
  };

  const performAssessment = async (payId: string) => {
    setLoading(true);
    setError(null);
    try {
      const res = await assessTestPayment(payId);
      setAssessment(res.data);
    } catch (err: any) {
      const msg = err.response?.data?.error?.message || err.response?.data?.detail || err.message;
      setError(msg || "Failed to assess payment");
    } finally {
      setLoading(false);
    }
  };

  const handleAssessPayment = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!paymentId) {
      setError("Please enter a Payment ID");
      return;
    }
    await performAssessment(paymentId);
  };

  const handlePayment = async () => {
    setError(null);
    if (!order) return;
    
    const res = await loadRazorpayScript();
    if (!res) {
      setError("Razorpay SDK failed to load. Are you online?");
      return;
    }

    if (!RAZORPAY_KEY_ID) {
      setError("Razorpay Test Key ID is not configured (missing VITE_RAZORPAY_KEY_ID).");
      return;
    }

    const options = {
      key: RAZORPAY_KEY_ID,
      amount: order.amount,
      currency: order.currency,
      name: "RazorBrain Test Store",
      description: "Test Transaction",
      order_id: order.id,
      prefill: {
        email: customerId,
        contact: "9999999999"
      },
      notes: {
        merchant_id: merchantId,
        customer_id: customerId,
      },
      theme: {
        color: "#2f80ed"
      },
      handler: async function (response: any) {
        setPaymentId(response.razorpay_payment_id);
        await performAssessment(response.razorpay_payment_id);
      }
    };
    
    try {
        const rzp = new (window as any).Razorpay(options);
        rzp.on('payment.failed', function (response: any){
            setError(`Payment Failed: ${response.error.description}`);
        });
        rzp.open();
    } catch (err: any) {
        setError(`Failed to open Razorpay: ${err.message}`);
    }
  };

  return (
    <div className="space-y-4 md:space-y-6 animate-in fade-in duration-500 max-w-5xl mx-auto">
      
      <div className="bg-accent-yellow/10 border border-accent-yellow/30 p-4 md:p-5 rounded-[12px] flex items-start gap-4">
        <AlertTriangle size={24} className="text-accent-yellow shrink-0 mt-0.5" />
        <div>
          <h3 className="text-accent-yellow font-semibold text-[15px] mb-1">Razorpay Test Mode Integration</h3>
          <p className="text-[13px] text-text-secondary leading-relaxed">
            This is an internal test tool for Razorpay Test Mode integration. Do NOT use live credentials.
            Webhook endpoint is configured.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 md:gap-6">
        <Card>
          <CardHeader>
            <CardTitle icon={<CreditCard size={16} />}>1. Create Test Order</CardTitle>
          </CardHeader>
          <form onSubmit={handleCreateOrder} className="space-y-4">
            <div>
              <label className="block text-[12px] text-text-secondary mb-1.5 font-medium">Amount (Standard Units)</label>
              <input type="number" value={amount} onChange={e => setAmount(e.target.value)} className="w-full bg-[rgba(9,24,45,0.8)] border border-[rgba(120,150,210,0.2)] rounded-[8px] px-3 py-2.5 text-sm text-text-primary focus:outline-none focus:border-brand focus:shadow-[0_0_0_3px_rgba(47,128,237,0.12)]" />
            </div>
            <div>
              <label className="block text-[12px] text-text-secondary mb-1.5 font-medium">Currency</label>
              <input type="text" value={currency} onChange={e => setCurrency(e.target.value)} className="w-full bg-[rgba(9,24,45,0.8)] border border-[rgba(120,150,210,0.2)] rounded-[8px] px-3 py-2.5 text-sm text-text-primary focus:outline-none focus:border-brand focus:shadow-[0_0_0_3px_rgba(47,128,237,0.12)]" />
            </div>
            <div>
              <label className="block text-[12px] text-text-secondary mb-1.5 font-medium">Customer Email</label>
              <input type="email" value={customerId} onChange={e => setCustomerId(e.target.value)} className="w-full bg-[rgba(9,24,45,0.8)] border border-[rgba(120,150,210,0.2)] rounded-[8px] px-3 py-2.5 text-sm text-text-primary focus:outline-none focus:border-brand focus:shadow-[0_0_0_3px_rgba(47,128,237,0.12)]" />
            </div>
            <div>
              <label className="block text-[12px] text-text-secondary mb-1.5 font-medium">Merchant ID</label>
              <input type="text" value={merchantId} onChange={e => setMerchantId(e.target.value)} className="w-full bg-[rgba(9,24,45,0.8)] border border-[rgba(120,150,210,0.2)] rounded-[8px] px-3 py-2.5 text-sm text-text-primary focus:outline-none focus:border-brand focus:shadow-[0_0_0_3px_rgba(47,128,237,0.12)]" />
            </div>
            <Button type="submit" disabled={loading} fullWidth icon={<Play size={16} />}>
              Create Order
            </Button>
          </form>

          {order && (
            <div className="mt-6 p-4 md:p-5 bg-brand/5 border border-brand/20 rounded-[10px]">
              <div className="flex items-center gap-2 text-brand-bright mb-3">
                <CheckCircle size={18} />
                <h3 className="text-[14px] font-semibold">Order Created</h3>
              </div>
              <pre className="text-[11px] text-text-secondary overflow-x-auto bg-[#050C17] p-3 rounded-[6px] border border-border-subtle mb-4 custom-scrollbar">
                {JSON.stringify(order, null, 2)}
              </pre>
              
              <Button onClick={handlePayment} disabled={loading} variant="secondary" fullWidth className="bg-brand/20 border-brand/50 text-white hover:bg-brand/30 hover:border-brand">
                Pay with Razorpay
              </Button>
            </div>
          )}
        </Card>

        <Card>
          <CardHeader>
            <CardTitle icon={<SearchCheck size={16} />}>2. Assess Test Payment Manually (Optional)</CardTitle>
          </CardHeader>
          <form onSubmit={handleAssessPayment} className="space-y-4">
            <div>
              <label className="block text-[12px] text-text-secondary mb-1.5 font-medium">Razorpay Payment ID (pay_...)</label>
              <input type="text" value={paymentId} onChange={e => setPaymentId(e.target.value)} placeholder="pay_XXX" className="w-full bg-[rgba(9,24,45,0.8)] border border-[rgba(120,150,210,0.2)] rounded-[8px] px-3 py-2.5 text-sm text-text-primary focus:outline-none focus:border-brand focus:shadow-[0_0_0_3px_rgba(47,128,237,0.12)]" />
            </div>
            <Button type="submit" disabled={loading} variant="secondary" fullWidth>
              Assess Transaction
            </Button>
          </form>
        </Card>
      </div>
      
      {error && (
        <div className="p-4 bg-accent-red/10 border border-accent-red/30 rounded-[10px] flex items-center gap-3 text-accent-red">
          <ShieldAlert size={20} />
          <p className="text-[13px] font-medium">{error}</p>
        </div>
      )}

      {assessment && (
        <Card className="border-brand/40 shadow-[0_0_20px_rgba(47,128,237,0.1)] relative overflow-hidden">
          <div className="absolute top-0 right-0 w-64 h-64 bg-brand/10 rounded-full blur-[50px] -mr-10 -mt-10 pointer-events-none"></div>
          
          <CardHeader>
            <CardTitle icon={<CheckCircle size={18} className="text-accent-green" />}>RazorBrain AI Assessment</CardTitle>
          </CardHeader>
          
          <div className="grid grid-cols-2 md:grid-cols-3 gap-6 mb-6">
            <div>
              <p className="text-[11px] text-text-muted uppercase tracking-widest font-semibold mb-1.5">Decision</p>
              <Badge variant={assessment.decision === 'BLOCK' ? 'danger' : assessment.decision === 'ALLOW' ? 'success' : 'warning'} className="text-[14px] px-3 py-1">
                {assessment.decision}
              </Badge>
            </div>
            <div>
              <p className="text-[11px] text-text-muted uppercase tracking-widest font-semibold mb-1.5">Fraud Probability</p>
              <p className={`text-[20px] font-bold ${assessment.risk > 0.7 ? 'text-accent-red' : assessment.risk > 0.3 ? 'text-accent-yellow' : 'text-accent-green'}`}>
                {assessment.risk !== undefined && assessment.risk !== null 
                  ? (assessment.risk * 100).toFixed(2) + '%' 
                  : 'Unavailable'}
              </p>
            </div>
            <div>
              <p className="text-[11px] text-text-muted uppercase tracking-widest font-semibold mb-1.5">Model Track</p>
              <p className="text-[14px] text-text-primary font-medium">{assessment.model_track}</p>
            </div>
            <div>
              <p className="text-[11px] text-text-muted uppercase tracking-widest font-semibold mb-1.5">Assessment Type</p>
              <p className="text-[14px] text-text-primary font-medium">{assessment.assessment_type}</p>
            </div>
            <div>
              <p className="text-[11px] text-text-muted uppercase tracking-widest font-semibold mb-1.5">Assessment ID</p>
              <p className="text-[12px] font-mono text-text-secondary bg-bg-card-secondary px-2 py-1 rounded inline-block">{assessment.assessment_id}</p>
            </div>
            <div>
              <p className="text-[11px] text-text-muted uppercase tracking-widest font-semibold mb-1.5">Razorpay Identifiers</p>
              <div className="space-y-1">
                <p className="text-[11px] font-mono text-text-secondary"><span className="text-text-muted">Pay:</span> {assessment.transaction_id}</p>
                <p className="text-[11px] font-mono text-text-secondary"><span className="text-text-muted">Order:</span> {order?.id || 'Unknown'}</p>
              </div>
            </div>
          </div>
          
          <div className="pt-4 border-t border-border-subtle">
            <Button onClick={() => window.location.href = `/transactions/${assessment.assessment_id}`}>
              Investigate Assessment Details
            </Button>
          </div>
        </Card>
      )}
    </div>
  );
}
