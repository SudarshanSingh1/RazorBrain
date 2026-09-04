import React, { useState, useEffect } from 'react';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const API_KEY = import.meta.env.VITE_API_KEY || 'dev-api-key-123';
const RAZORPAY_KEY_ID = import.meta.env.VITE_RAZORPAY_KEY_ID;

export function RazorpayTest() {
  const [amount, setAmount] = useState('500');
  const [currency, setCurrency] = useState('INR');
  const [receipt] = useState('test_receipt_1');
  const [customerId, setCustomerId] = useState('test_user@example.com');
  const [merchantId, setMerchantId] = useState('m_internal_1');
  
  const [order, setOrder] = useState<any>(null);
const [assessment, setAssessment] = useState<any>(null);

  // Phase 40: Generate a persistent first-party session identifier
  useEffect(() => {
    if (!sessionStorage.getItem("rzp_test_session_id")) {
      const newSessionId = "sess_" + Math.random().toString(36).substring(2, 15) + Math.random().toString(36).substring(2, 15);
      sessionStorage.setItem("rzp_test_session_id", newSessionId);
    }
  }, []);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  const [paymentId, setPaymentId] = useState('');

  const loadRazorpayScript = () => {
    return new Promise((resolve) => {
      if ((window as any).Razorpay) {
        resolve(true);
        return;
      }
      const script = document.createElement('script');
      script.src = 'https://checkout.razorpay.com/v1/checkout.js';
      script.onload = () => resolve(true);
      script.onerror = () => resolve(false);
      document.body.appendChild(script);
    });
  };

  const handleCreateOrder = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setOrder(null);
    setAssessment(null);
    setPaymentId('');
    
    try {
const response = await fetch(`${API_URL}/razorpay/test/orders`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-API-Key': API_KEY,
          'X-Session-ID': sessionStorage.getItem("rzp_test_session_id") || "",
        },

        body: JSON.stringify({
          amount: Math.round(parseFloat(amount) * 100), // Convert to subunits
          currency,
          receipt,
          notes: {
            customer_id: customerId,
            merchant_id: merchantId,
          }
        }),
      });
      
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || data.error?.message || 'Order creation failed');
      }
      
      setOrder(data);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const performAssessment = async (pid: string) => {
    setLoading(true);
    setError(null);
    try {
const response = await fetch(`${API_URL}/razorpay/test/assess`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-API-Key': API_KEY,
          'X-Session-ID': sessionStorage.getItem("rzp_test_session_id") || "",
        },

        body: JSON.stringify({
          payment_id: pid
        }),
      });
      
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || data.error?.message || 'Assessment failed');
      }
      
      setAssessment(data);
    } catch (err: any) {
      setError(err.message);
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
      setError("Razorpay Test Key ID is not configured in the frontend (missing VITE_RAZORPAY_KEY_ID).");
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
        color: "#4f46e5"
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
    <div className="p-6">
      <h1 className="text-2xl font-bold mb-4">Razorpay TEST MODE</h1>
      <div className="mb-6 bg-yellow-50 border-l-4 border-yellow-400 p-4">
        <p className="text-sm text-yellow-700">
          This is an internal test tool for Razorpay Test Mode integration. Do NOT use live credentials.
        </p>
        <p className="text-sm text-yellow-700 mt-2">
          <strong>Webhook Status:</strong> Webhook endpoint configured.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        <div>
          <h2 className="text-xl font-semibold mb-4">1. Create Test Order</h2>
          <form onSubmit={handleCreateOrder} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700">Amount (Standard Units)</label>
              <input type="number" value={amount} onChange={e => setAmount(e.target.value)} className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm" />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700">Currency</label>
              <input type="text" value={currency} onChange={e => setCurrency(e.target.value)} className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm" />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700">Customer Email</label>
              <input type="email" value={customerId} onChange={e => setCustomerId(e.target.value)} className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm" />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700">Merchant ID</label>
              <input type="text" value={merchantId} onChange={e => setMerchantId(e.target.value)} className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm" />
            </div>
            <button type="submit" disabled={loading} className="inline-flex justify-center py-2 px-4 border border-transparent shadow-sm text-sm font-medium rounded-md text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500">
              Create Order
            </button>
          </form>

          {order && (
            <div className="mt-4 p-4 bg-gray-50 rounded-md">
              <h3 className="text-md font-medium text-green-700">Order Created</h3>
              <pre className="text-xs mt-2 overflow-x-auto">{JSON.stringify(order, null, 2)}</pre>
              
              <div className="mt-4">
                <button onClick={handlePayment} disabled={loading} className="inline-flex justify-center py-2 px-4 border border-transparent shadow-sm text-sm font-medium rounded-md text-white bg-green-600 hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-green-500">
                  Pay with Razorpay
                </button>
              </div>
            </div>
          )}
        </div>

        <div>
          <h2 className="text-xl font-semibold mb-4">2. Assess Test Payment Manually (Optional)</h2>
          <form onSubmit={handleAssessPayment} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700">Razorpay Payment ID (pay_...)</label>
              <input type="text" value={paymentId} onChange={e => setPaymentId(e.target.value)} placeholder="pay_XXX" className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm" />
            </div>
            <button type="submit" disabled={loading} className="inline-flex justify-center py-2 px-4 border border-transparent shadow-sm text-sm font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500">
              Assess Transaction
            </button>
          </form>
        </div>
      </div>
      
      {error && (
        <div className="mt-6 p-4 bg-red-50 border-l-4 border-red-400">
          <p className="text-sm text-red-700">{error}</p>
        </div>
      )}

      {assessment && (
        <div className="mt-8 p-6 bg-white border border-gray-200 shadow rounded-md">
          <h2 className="text-xl font-bold text-gray-800 mb-4">RazorBrain AI Assessment</h2>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <p className="text-sm text-gray-500">Decision</p>
              <p className={`text-lg font-bold ${assessment.decision === 'BLOCK' ? 'text-red-600' : assessment.decision === 'ALLOW' ? 'text-green-600' : 'text-yellow-600'}`}>
                {assessment.decision}
              </p>
            </div>
            <div>
              <p className="text-sm text-gray-500">Fraud Probability</p>
              <p className="text-lg font-bold">
                {assessment.risk !== undefined && assessment.risk !== null 
                  ? (assessment.risk * 100).toFixed(2) + '%' 
                  : 'Unavailable'}
              </p>
            </div>
            <div>
              <p className="text-sm text-gray-500">Model Track</p>
              <p className="text-md">{assessment.model_track}</p>
            </div>
            <div>
              <p className="text-sm text-gray-500">Assessment Type</p>
              <p className="text-md">{assessment.assessment_type}</p>
            </div>
            <div>
              <p className="text-sm text-gray-500">Assessment ID</p>
              <p className="text-sm font-mono">{assessment.assessment_id}</p>
            </div>
            <div>
              <p className="text-sm text-gray-500">Razorpay Identifiers</p>
              <p className="text-sm font-mono">Pay: {assessment.transaction_id}</p>
              <p className="text-sm font-mono">Order: {order?.id || 'Unknown'}</p>
            </div>
          </div>
          
          <div className="mt-6 flex gap-4">
            <a href={`/transactions/${assessment.assessment_id}`} className="inline-flex justify-center py-2 px-4 border border-transparent shadow-sm text-sm font-medium rounded-md text-white bg-indigo-600 hover:bg-indigo-700">
              Investigate Assessment Details
            </a>
          </div>
        </div>
      )}
    </div>
  );
}
