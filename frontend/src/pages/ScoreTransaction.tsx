import React, { useState, useEffect, useRef } from 'react';
import {
  Zap,
  ShieldCheck,
  AlertTriangle,
  RotateCcw,
  Sparkles,
  CheckCircle2,
  Clock,
  CreditCard,
  User,
  Activity,
  Copy,
  Check,
  ArrowRight,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import { decideTransaction, getHealth } from '../services/api';
import { Card, CardHeader, CardTitle } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import type { DecisionDetails, RiskLevel } from '../types';

interface FormData {
  transaction_id: string;
  amount: string;
  customer_id: string;
  email: string;
  card_network: string;
  card_type: string;
  hour_of_day: string;
  day_of_week: string;
  is_new_customer: boolean;
  previous_transaction_count: string;
  avg_customer_amount: string;
  txns_last_1h: string;
  txns_last_24h: string;
}

const DAYS_OF_WEEK = [
  { value: '0', label: 'Monday (0)' },
  { value: '1', label: 'Tuesday (1)' },
  { value: '2', label: 'Wednesday (2)' },
  { value: '3', label: 'Thursday (3)' },
  { value: '4', label: 'Friday (4)' },
  { value: '5', label: 'Saturday (5)' },
  { value: '6', label: 'Sunday (6)' },
];

const CARD_NETWORKS = [
  { value: 'visa', label: 'Visa' },
  { value: 'mastercard', label: 'Mastercard' },
  { value: 'rupay', label: 'RuPay' },
  { value: 'amex', label: 'American Express' },
  { value: 'discover', label: 'Discover' },
  { value: 'MISSING', label: 'Other / Missing' },
];

const CARD_TYPES = [
  { value: 'credit', label: 'Credit Card' },
  { value: 'debit', label: 'Debit Card' },
  { value: 'prepaid', label: 'Prepaid Card' },
  { value: 'MISSING', label: 'Unknown / Missing' },
];

export default function ScoreTransaction() {
  const now = new Date();
  const defaultHour = String(now.getUTCHours());
  const defaultDow = String(now.getUTCDay() === 0 ? 6 : now.getUTCDay() - 1);

  const initialForm: FormData = {
    transaction_id: '',
    amount: '2500',
    customer_id: 'cust_live_01',
    email: 'alex@example.com',
    card_network: 'visa',
    card_type: 'credit',
    hour_of_day: defaultHour,
    day_of_week: defaultDow,
    is_new_customer: false,
    previous_transaction_count: '6',
    avg_customer_amount: '2200',
    txns_last_1h: '1',
    txns_last_24h: '3',
  };

  const [form, setForm] = useState<FormData>(initialForm);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<DecisionDetails | null>(null);
  const [apiError, setApiError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [showFeaturesTable, setShowFeaturesTable] = useState(false);
  const [showTrace, setShowTrace] = useState(false);
  const [apiStatus, setApiStatus] = useState<'Online' | 'Checking' | 'Offline'>('Checking');

  const isSubmittingRef = useRef(false);
  const abortControllerRef = useRef<AbortController | null>(null);
  const amountInputRef = useRef<HTMLInputElement>(null);

  // Check API status once on mount
  useEffect(() => {
    let mounted = true;
    getHealth()
      .then((res) => {
        if (mounted) {
          setApiStatus(res.data?.status === 'ok' ? 'Online' : 'Offline');
        }
      })
      .catch(() => {
        if (mounted) {
          setApiStatus('Offline');
        }
      });

    return () => {
      mounted = false;
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, []);

  // Validation logic
  const validate = (): boolean => {
    const newErrors: Record<string, string> = {};

    // Amount validation
    if (!form.amount || !form.amount.trim()) {
      newErrors.amount = 'Transaction amount is required.';
    } else {
      const amt = Number(form.amount);
      if (Number.isNaN(amt) || !Number.isFinite(amt)) {
        newErrors.amount = 'Amount must be a valid number.';
      } else if (amt <= 0) {
        newErrors.amount = 'Amount must be strictly greater than ₹0.';
      } else if (amt > 100_000_000) {
        newErrors.amount = 'Amount cannot exceed ₹100,000,000.';
      }
    }

    // Hour validation
    if (form.hour_of_day !== '') {
      const hr = Number(form.hour_of_day);
      if (Number.isNaN(hr) || !Number.isInteger(hr) || hr < 0 || hr > 23) {
        newErrors.hour_of_day = 'Hour must be an integer between 0 and 23.';
      }
    }

    // Day validation
    if (form.day_of_week !== '') {
      const dow = Number(form.day_of_week);
      if (Number.isNaN(dow) || !Number.isInteger(dow) || dow < 0 || dow > 6) {
        newErrors.day_of_week = 'Select a valid day of week (0 to 6).';
      }
    }

    // Velocity & history validation (only if not new customer)
    if (!form.is_new_customer) {
      if (form.previous_transaction_count !== '') {
        const count = Number(form.previous_transaction_count);
        if (Number.isNaN(count) || !Number.isInteger(count) || count < 0) {
          newErrors.previous_transaction_count = 'Must be an integer ≥ 0.';
        }
      }

      if (form.avg_customer_amount !== '') {
        const avg = Number(form.avg_customer_amount);
        if (Number.isNaN(avg) || avg < 0) {
          newErrors.avg_customer_amount = 'Average amount must be ≥ 0.';
        }
      }

      if (form.txns_last_1h !== '') {
        const t1h = Number(form.txns_last_1h);
        if (Number.isNaN(t1h) || !Number.isInteger(t1h) || t1h < 0) {
          newErrors.txns_last_1h = 'Must be an integer ≥ 0.';
        }
      }

      if (form.txns_last_24h !== '') {
        const t24h = Number(form.txns_last_24h);
        if (Number.isNaN(t24h) || !Number.isInteger(t24h) || t24h < 0) {
          newErrors.txns_last_24h = 'Must be an integer ≥ 0.';
        }
      }
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const { name, value } = e.target;
    setForm((prev) => ({ ...prev, [name]: value }));
    if (errors[name]) {
      setErrors((prev) => {
        const updated = { ...prev };
        delete updated[name];
        return updated;
      });
    }
  };

  const handleCheckboxChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const checked = e.target.checked;
    setForm((prev) => ({
      ...prev,
      is_new_customer: checked,
      ...(checked
        ? {
            previous_transaction_count: '0',
            avg_customer_amount: '0',
            txns_last_1h: '0',
            txns_last_24h: '0',
          }
        : {}),
    }));
  };

  // Submit Handler with double-click guard and timeout
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (isSubmittingRef.current || loading) {
      return; // prevent duplicate clicks
    }

    if (!validate()) {
      return;
    }

    isSubmittingRef.current = true;
    setLoading(true);
    setApiError(null);

    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    abortControllerRef.current = new AbortController();

    const payload: Record<string, any> = {
      amount: parseFloat(form.amount),
      transaction_id: form.transaction_id.trim() || undefined,
      customer_id: form.customer_id.trim() || undefined,
      email: form.email.trim() || undefined,
      card_network: form.card_network,
      card_type: form.card_type,
      hour_of_day: form.hour_of_day !== '' ? parseInt(form.hour_of_day, 10) : undefined,
      day_of_week: form.day_of_week !== '' ? parseInt(form.day_of_week, 10) : undefined,
      is_new_customer: form.is_new_customer ? 1 : 0,
      previous_transaction_count: form.is_new_customer
        ? 0
        : parseInt(form.previous_transaction_count || '0', 10),
      avg_customer_amount: form.is_new_customer
        ? 0.0
        : parseFloat(form.avg_customer_amount || '0'),
      txns_last_1h: form.is_new_customer ? 0 : parseInt(form.txns_last_1h || '0', 10),
      txns_last_24h: form.is_new_customer ? 0 : parseInt(form.txns_last_24h || '0', 10),
    };

    try {
      const response = await decideTransaction(payload, {
        signal: abortControllerRef.current.signal,
      });

      if (response.data && response.data.success && response.data.decision) {
        const pred = response.data.decision;
        // Validate response format safely
        if (
          typeof pred.fraud_probability === 'number' &&
          Number.isFinite(pred.fraud_probability) &&
          pred.fraud_probability >= 0 &&
          pred.fraud_probability <= 1
        ) {
          setResult(pred);
        } else {
          setApiError('The model returned an out-of-bounds probability.');
        }
      } else {
        setApiError('Server returned an unexpected prediction payload.');
      }
    } catch (err: any) {
      if (err.name === 'CanceledError' || err.name === 'AbortError') {
        return;
      }
      if (err.response) {
        const msg =
          err.response.data?.detail ||
          err.response.data?.error?.message ||
          `API Error (${err.response.status}): ${err.response.statusText}`;
        setApiError(msg);
      } else if (err.request) {
        setApiError('Prediction service is currently unavailable. Please verify backend is running on port 8000.');
      } else {
        setApiError(err.message || 'An unexpected error occurred while scoring.');
      }
    } finally {
      setLoading(false);
      isSubmittingRef.current = false;
    }
  };

  // Preset loaders
  const loadPreset = (preset: 'low' | 'high' | 'cold') => {
    setErrors({});
    setApiError(null);
    if (preset === 'low') {
      setForm({
        transaction_id: `txn_${Math.floor(Math.random() * 899999 + 100000)}`,
        amount: '1250',
        customer_id: 'cust_premium_44',
        email: 'priya.sharma@gmail.com',
        card_network: 'visa',
        card_type: 'debit',
        hour_of_day: '14',
        day_of_week: '2',
        is_new_customer: false,
        previous_transaction_count: '24',
        avg_customer_amount: '1150',
        txns_last_1h: '1',
        txns_last_24h: '2',
      });
    } else if (preset === 'high') {
      setForm({
        transaction_id: `txn_${Math.floor(Math.random() * 899999 + 100000)}`,
        amount: '89000',
        customer_id: 'cust_anomaly_99',
        email: 'tempuser@unknown-disposable.com',
        card_network: 'mastercard',
        card_type: 'credit',
        hour_of_day: '3',
        day_of_week: '5',
        is_new_customer: false,
        previous_transaction_count: '1',
        avg_customer_amount: '350',
        txns_last_1h: '6',
        txns_last_24h: '18',
      });
    } else if (preset === 'cold') {
      setForm({
        transaction_id: `txn_${Math.floor(Math.random() * 899999 + 100000)}`,
        amount: '3200',
        customer_id: 'cust_first_timer_01',
        email: 'newbuyer@gmail.com',
        card_network: 'rupay',
        card_type: 'debit',
        hour_of_day: '11',
        day_of_week: '1',
        is_new_customer: true,
        previous_transaction_count: '0',
        avg_customer_amount: '0',
        txns_last_1h: '0',
        txns_last_24h: '0',
      });
    }
  };

  const handleReset = () => {
    setForm(initialForm);
    setErrors({});
    setResult(null);
    setApiError(null);
    amountInputRef.current?.focus();
  };

  const copyResultJSON = () => {
    if (!result) return;
    navigator.clipboard.writeText(JSON.stringify(result, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const getRiskBadgeConfig = (level: RiskLevel) => {
    switch (level) {
      case 'LOW':
        return {
          label: 'LOW RISK',
          variant: 'success' as const,
          barColor: 'from-emerald-500 to-teal-400',
          textColor: 'text-emerald-400',
          border: 'border-emerald-500/30',
          bg: 'bg-emerald-500/10',
          desc: 'Calibrated score falls safely below the manual review threshold (12.13%).',
        };
      case 'MEDIUM':
        return {
          label: 'MEDIUM RISK',
          variant: 'warning' as const,
          barColor: 'from-amber-500 to-yellow-400',
          textColor: 'text-amber-400',
          border: 'border-amber-500/30',
          bg: 'bg-amber-500/10',
          desc: 'Score is elevated (12.13% – 20.53%). Requires manual verification.',
        };
      case 'HIGH':
        return {
          label: 'HIGH RISK',
          variant: 'danger' as const,
          barColor: 'from-rose-500 to-red-600',
          textColor: 'text-rose-400',
          border: 'border-rose-500/30',
          bg: 'bg-rose-500/10',
          desc: 'Score breaches automated policy threshold (≥ 20.53%). High fraud likelihood.',
        };
    }
  };

  
  const getDecisionBadgeConfig = (decision: string) => {
    switch (decision) {
      case 'APPROVE': return { label: 'APPROVE', variant: 'success' as const, textColor: 'text-emerald-400', border: 'border-emerald-500/30', bg: 'bg-emerald-500/10' };
      case 'REVIEW': return { label: 'REVIEW', variant: 'warning' as const, textColor: 'text-amber-400', border: 'border-amber-500/30', bg: 'bg-amber-500/10' };
      case 'STEP_UP': return { label: 'STEP UP', variant: 'warning' as const, textColor: 'text-orange-400', border: 'border-orange-500/30', bg: 'bg-orange-500/10' };
      case 'DECLINE': return { label: 'DECLINE', variant: 'danger' as const, textColor: 'text-rose-400', border: 'border-rose-500/30', bg: 'bg-rose-500/10' };
      default: return { label: decision, variant: 'default' as const, textColor: 'text-text-primary', border: 'border-border-subtle', bg: 'bg-bg-main' };
    }
  };

  return (
    <div className="space-y-6 max-w-[1600px] mx-auto">
      {/* Top Header & Service Status */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-2 border-b border-border-subtle/50">
        <div>
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-brand/20 border border-brand/40 flex items-center justify-center text-brand-bright">
              <Zap size={18} />
            </div>
            <h1 className="text-2xl font-bold text-text-primary tracking-tight">
              Score Transaction
            </h1>
          </div>
          <p className="text-[13.5px] text-text-muted mt-1">
            Manual inference against the authoritative 15-feature calibrated XGBoost serving model.
          </p>
        </div>

        <div className="flex items-center gap-3">
          {/* Lightweight non-intrusive status pill */}
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-bg-card border border-border-subtle text-[12px] font-medium text-text-secondary">
            <span className="relative flex h-2 w-2">
              <span
                className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${
                  apiStatus === 'Online'
                    ? 'bg-emerald-400'
                    : apiStatus === 'Checking'
                    ? 'bg-amber-400'
                    : 'bg-rose-400'
                }`}
              />
              <span
                className={`relative inline-flex rounded-full h-2 w-2 ${
                  apiStatus === 'Online'
                    ? 'bg-emerald-500'
                    : apiStatus === 'Checking'
                    ? 'bg-amber-500'
                    : 'bg-rose-500'
                }`}
              />
            </span>
            <span>Inference API: {apiStatus}</span>
          </div>

          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={handleReset}
            className="flex items-center gap-1.5 text-text-muted hover:text-text-primary"
          >
            <RotateCcw size={14} />
            Reset
          </Button>
        </div>
      </div>

      {/* Preset Scenario Shortcuts */}
      <div className="flex flex-wrap items-center gap-2 p-3 bg-bg-card/60 border border-border-subtle/80 rounded-xl">
        <span className="text-[12px] font-medium text-text-muted flex items-center gap-1.5 mr-1">
          <Sparkles size={14} className="text-brand-bright" />
          Quick Scenarios:
        </span>
        <button
          type="button"
          onClick={() => loadPreset('low')}
          className="px-2.5 py-1 text-[12px] font-medium rounded-lg bg-bg-card-secondary hover:bg-brand/15 hover:text-brand-bright text-text-secondary border border-border-subtle/60 transition-colors"
        >
          Normal Purchase (Low Risk)
        </button>
        <button
          type="button"
          onClick={() => loadPreset('high')}
          className="px-2.5 py-1 text-[12px] font-medium rounded-lg bg-bg-card-secondary hover:bg-rose-500/15 hover:text-rose-400 text-text-secondary border border-border-subtle/60 transition-colors"
        >
          High-Amount Anomaly (High Risk)
        </button>
        <button
          type="button"
          onClick={() => loadPreset('cold')}
          className="px-2.5 py-1 text-[12px] font-medium rounded-lg bg-bg-card-secondary hover:bg-blue-500/15 hover:text-blue-400 text-text-secondary border border-border-subtle/60 transition-colors"
        >
          New Customer (Cold Start)
        </button>
      </div>

      {/* Main Two-Column Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* LEFT COLUMN: Transaction Form (7 cols on desktop) */}
        <div className="lg:col-span-7">
          <Card>
            <CardHeader>
              <CardTitle icon={<CreditCard size={18} />}>
                Transaction Input Parameters
              </CardTitle>
            </CardHeader>

            <form onSubmit={handleSubmit} noValidate className="space-y-6">
              {/* Group 1: Transaction Information */}
              <div className="space-y-4">
                <div className="flex items-center gap-2 pb-1.5 border-b border-border-subtle/40">
                  <Activity size={15} className="text-brand-bright" />
                  <h4 className="text-[13px] font-semibold text-text-primary tracking-wide uppercase">
                    1. Transaction Information
                  </h4>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  {/* Amount Field */}
                  <div className="sm:col-span-2">
                    <label className="block text-[12.5px] font-medium text-text-secondary mb-1.5">
                      Transaction Amount (INR) <span className="text-rose-400">*</span>
                    </label>
                    <div className="relative">
                      <span className="absolute left-3.5 top-1/2 -translate-y-1/2 text-text-muted font-medium text-[14px]">
                        ₹
                      </span>
                      <input
                        ref={amountInputRef}
                        type="number"
                        step="any"
                        name="amount"
                        value={form.amount}
                        onChange={handleInputChange}
                        placeholder="e.g. 2500"
                        disabled={loading}
                        className={`w-full pl-8 pr-3.5 py-2.5 rounded-lg bg-bg-main border text-text-primary text-[14px] font-medium transition-colors focus:outline-none focus:ring-1 ${
                          errors.amount
                            ? 'border-rose-500 focus:border-rose-500 focus:ring-rose-500/30'
                            : 'border-border-subtle focus:border-brand focus:ring-brand/30'
                        }`}
                      />
                    </div>
                    {errors.amount && (
                      <p className="text-rose-400 text-[11.5px] mt-1.5 flex items-center gap-1">
                        <AlertTriangle size={12} />
                        {errors.amount}
                      </p>
                    )}
                  </div>

                  {/* Card Network */}
                  <div>
                    <label className="block text-[12.5px] font-medium text-text-secondary mb-1.5">
                      Card Network
                    </label>
                    <select
                      name="card_network"
                      value={form.card_network}
                      onChange={handleInputChange}
                      disabled={loading}
                      className="w-full px-3.5 py-2.5 rounded-lg bg-bg-main border border-border-subtle text-text-primary text-[13.5px] focus:outline-none focus:border-brand focus:ring-1 focus:ring-brand/30"
                    >
                      {CARD_NETWORKS.map((net) => (
                        <option key={net.value} value={net.value}>
                          {net.label}
                        </option>
                      ))}
                    </select>
                  </div>

                  {/* Card Type */}
                  <div>
                    <label className="block text-[12.5px] font-medium text-text-secondary mb-1.5">
                      Card Type
                    </label>
                    <select
                      name="card_type"
                      value={form.card_type}
                      onChange={handleInputChange}
                      disabled={loading}
                      className="w-full px-3.5 py-2.5 rounded-lg bg-bg-main border border-border-subtle text-text-primary text-[13.5px] focus:outline-none focus:border-brand focus:ring-1 focus:ring-brand/30"
                    >
                      {CARD_TYPES.map((type) => (
                        <option key={type.value} value={type.value}>
                          {type.label}
                        </option>
                      ))}
                    </select>
                  </div>

                  {/* Hour of Day */}
                  <div>
                    <div className="flex items-center justify-between mb-1.5">
                      <label className="text-[12.5px] font-medium text-text-secondary">
                        Hour of Day (0–23)
                      </label>
                      <button
                        type="button"
                        onClick={() =>
                          setForm((p) => ({ ...p, hour_of_day: String(new Date().getUTCHours()) }))
                        }
                        className="text-[11px] text-brand-bright hover:underline"
                      >
                        Set to Now
                      </button>
                    </div>
                    <input
                      type="number"
                      min="0"
                      max="23"
                      name="hour_of_day"
                      value={form.hour_of_day}
                      onChange={handleInputChange}
                      placeholder="0-23"
                      disabled={loading}
                      className={`w-full px-3.5 py-2.5 rounded-lg bg-bg-main border text-text-primary text-[13.5px] focus:outline-none focus:ring-1 ${
                        errors.hour_of_day
                          ? 'border-rose-500 focus:ring-rose-500/30'
                          : 'border-border-subtle focus:border-brand focus:ring-brand/30'
                      }`}
                    />
                    {errors.hour_of_day && (
                      <p className="text-rose-400 text-[11.5px] mt-1.5">{errors.hour_of_day}</p>
                    )}
                  </div>

                  {/* Day of Week */}
                  <div>
                    <label className="block text-[12.5px] font-medium text-text-secondary mb-1.5">
                      Day of Week
                    </label>
                    <select
                      name="day_of_week"
                      value={form.day_of_week}
                      onChange={handleInputChange}
                      disabled={loading}
                      className="w-full px-3.5 py-2.5 rounded-lg bg-bg-main border border-border-subtle text-text-primary text-[13.5px] focus:outline-none focus:border-brand focus:ring-1 focus:ring-brand/30"
                    >
                      {DAYS_OF_WEEK.map((d) => (
                        <option key={d.value} value={d.value}>
                          {d.label}
                        </option>
                      ))}
                    </select>
                    {errors.day_of_week && (
                      <p className="text-rose-400 text-[11.5px] mt-1.5">{errors.day_of_week}</p>
                    )}
                  </div>
                </div>
              </div>

              {/* Group 2: Customer / Account Information */}
              <div className="space-y-4">
                <div className="flex items-center gap-2 pb-1.5 border-b border-border-subtle/40">
                  <User size={15} className="text-brand-bright" />
                  <h4 className="text-[13px] font-semibold text-text-primary tracking-wide uppercase">
                    2. Customer / Account Information
                  </h4>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-[12.5px] font-medium text-text-secondary mb-1.5">
                      Customer ID (Optional)
                    </label>
                    <input
                      type="text"
                      name="customer_id"
                      value={form.customer_id}
                      onChange={handleInputChange}
                      placeholder="cust_94812"
                      disabled={loading}
                      className="w-full px-3.5 py-2.5 rounded-lg bg-bg-main border border-border-subtle text-text-primary text-[13.5px] focus:outline-none focus:border-brand focus:ring-1 focus:ring-brand/30"
                    />
                  </div>

                  <div>
                    <label className="block text-[12.5px] font-medium text-text-secondary mb-1.5">
                      Email or Domain
                    </label>
                    <input
                      type="text"
                      name="email"
                      value={form.email}
                      onChange={handleInputChange}
                      placeholder="user@gmail.com"
                      disabled={loading}
                      className="w-full px-3.5 py-2.5 rounded-lg bg-bg-main border border-border-subtle text-text-primary text-[13.5px] focus:outline-none focus:border-brand focus:ring-1 focus:ring-brand/30"
                    />
                  </div>

                  {/* Cold Start New Customer Toggle */}
                  <div className="sm:col-span-2">
                    <label className="flex items-center gap-3 p-3 rounded-lg border border-border-subtle/80 bg-bg-card-secondary/40 cursor-pointer hover:border-brand/40 transition-colors">
                      <input
                        type="checkbox"
                        checked={form.is_new_customer}
                        onChange={handleCheckboxChange}
                        disabled={loading}
                        className="w-4 h-4 rounded text-brand focus:ring-brand/40 border-border-subtle"
                      />
                      <div className="text-[13px]">
                        <span className="font-semibold text-text-primary">
                          First-Time Customer (Cold-Start Account)
                        </span>
                        <p className="text-[11.5px] text-text-muted mt-0.5">
                          Enforces causal cold-start defaults (0 prior transactions, neutral deviation).
                        </p>
                      </div>
                    </label>
                  </div>
                </div>
              </div>

              {/* Group 3: Behaviour / Velocity Information */}
              <div className="space-y-4">
                <div className="flex items-center justify-between pb-1.5 border-b border-border-subtle/40">
                  <div className="flex items-center gap-2">
                    <Clock size={15} className="text-brand-bright" />
                    <h4 className="text-[13px] font-semibold text-text-primary tracking-wide uppercase">
                      3. Behaviour & Velocity Information
                    </h4>
                  </div>
                  {form.is_new_customer && (
                    <span className="text-[11px] text-amber-400 font-medium">
                      Disabled (Cold Start)
                    </span>
                  )}
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-[12.5px] font-medium text-text-secondary mb-1.5">
                      Prior Transaction Count
                    </label>
                    <input
                      type="number"
                      min="0"
                      name="previous_transaction_count"
                      value={form.previous_transaction_count}
                      onChange={handleInputChange}
                      disabled={loading || form.is_new_customer}
                      className={`w-full px-3.5 py-2.5 rounded-lg bg-bg-main border text-text-primary text-[13.5px] disabled:opacity-40 disabled:cursor-not-allowed ${
                        errors.previous_transaction_count
                          ? 'border-rose-500'
                          : 'border-border-subtle focus:border-brand'
                      }`}
                    />
                    {errors.previous_transaction_count && (
                      <p className="text-rose-400 text-[11.5px] mt-1.5">
                        {errors.previous_transaction_count}
                      </p>
                    )}
                  </div>

                  <div>
                    <label className="block text-[12.5px] font-medium text-text-secondary mb-1.5">
                      Average Past Amount (INR)
                    </label>
                    <input
                      type="number"
                      step="any"
                      min="0"
                      name="avg_customer_amount"
                      value={form.avg_customer_amount}
                      onChange={handleInputChange}
                      disabled={loading || form.is_new_customer}
                      className={`w-full px-3.5 py-2.5 rounded-lg bg-bg-main border text-text-primary text-[13.5px] disabled:opacity-40 disabled:cursor-not-allowed ${
                        errors.avg_customer_amount
                          ? 'border-rose-500'
                          : 'border-border-subtle focus:border-brand'
                      }`}
                    />
                    {errors.avg_customer_amount && (
                      <p className="text-rose-400 text-[11.5px] mt-1.5">
                        {errors.avg_customer_amount}
                      </p>
                    )}
                  </div>

                  <div>
                    <label className="block text-[12.5px] font-medium text-text-secondary mb-1.5">
                      Transactions in Last 1 Hour
                    </label>
                    <input
                      type="number"
                      min="0"
                      name="txns_last_1h"
                      value={form.txns_last_1h}
                      onChange={handleInputChange}
                      disabled={loading || form.is_new_customer}
                      className={`w-full px-3.5 py-2.5 rounded-lg bg-bg-main border text-text-primary text-[13.5px] disabled:opacity-40 disabled:cursor-not-allowed ${
                        errors.txns_last_1h ? 'border-rose-500' : 'border-border-subtle focus:border-brand'
                      }`}
                    />
                    {errors.txns_last_1h && (
                      <p className="text-rose-400 text-[11.5px] mt-1.5">{errors.txns_last_1h}</p>
                    )}
                  </div>

                  <div>
                    <label className="block text-[12.5px] font-medium text-text-secondary mb-1.5">
                      Transactions in Last 24 Hours
                    </label>
                    <input
                      type="number"
                      min="0"
                      name="txns_last_24h"
                      value={form.txns_last_24h}
                      onChange={handleInputChange}
                      disabled={loading || form.is_new_customer}
                      className={`w-full px-3.5 py-2.5 rounded-lg bg-bg-main border text-text-primary text-[13.5px] disabled:opacity-40 disabled:cursor-not-allowed ${
                        errors.txns_last_24h ? 'border-rose-500' : 'border-border-subtle focus:border-brand'
                      }`}
                    />
                    {errors.txns_last_24h && (
                      <p className="text-rose-400 text-[11.5px] mt-1.5">{errors.txns_last_24h}</p>
                    )}
                  </div>
                </div>
              </div>

              {/* Submit & Reset Button */}
              <div className="pt-2 flex items-center gap-3">
                <Button
                  type="submit"
                  disabled={loading}
                  className="flex-1 py-3 bg-gradient-to-r from-brand to-brand-hover text-white font-semibold text-[14px] shadow-lg shadow-brand/20 hover:shadow-brand/40 flex items-center justify-center gap-2"
                >
                  {loading ? (
                    <>
                      <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                      Evaluating Model...
                    </>
                  ) : (
                    <>
                      <Zap size={16} />
                      Score Transaction
                      <ArrowRight size={16} />
                    </>
                  )}
                </Button>

                <Button
                  type="button"
                  variant="secondary"
                  onClick={handleReset}
                  disabled={loading}
                  className="py-3 px-4"
                >
                  Reset
                </Button>
              </div>
            </form>
          </Card>
        </div>

        {/* RIGHT COLUMN: Prediction Result (5 cols on desktop) */}
        <div className="lg:col-span-5 space-y-4">
          {/* API Error State */}
          {apiError && (
            <div className="p-4 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 space-y-2">
              <div className="flex items-center gap-2 font-semibold text-[13.5px] text-rose-400">
                <AlertTriangle size={17} />
                Prediction Request Failed
              </div>
              <p className="text-[12.5px] text-rose-200/90 leading-relaxed">{apiError}</p>
              <div className="pt-1">
                <button
                  type="button"
                  onClick={handleSubmit}
                  className="px-3 py-1 bg-rose-500/20 hover:bg-rose-500/30 border border-rose-500/40 text-rose-300 rounded text-[12px] font-medium transition-colors"
                >
                  Retry Scoring
                </button>
              </div>
            </div>
          )}

          {/* Loading State */}
          {loading && (
            <Card className="animate-pulse">
              <CardHeader>
                <CardTitle icon={<Zap size={18} className="text-brand-bright animate-spin" />}>
                  Scoring in Progress...
                </CardTitle>
              </CardHeader>
              <div className="space-y-4 py-4">
                <div className="h-6 bg-bg-card-secondary rounded w-3/4" />
                <div className="h-16 bg-bg-card-secondary rounded" />
                <div className="h-4 bg-bg-card-secondary rounded w-1/2" />
                <div className="h-10 bg-bg-card-secondary rounded" />
                <p className="text-[12px] text-text-muted text-center pt-2">
                  Passing 15 contract features to XGBoost serving model and applying Isotonic Calibration...
                </p>
              </div>
            </Card>
          )}

          {/* Success State */}
          {!loading && result && (
            <Card className="border-border-active/40 shadow-xl shadow-black/20">
              <CardHeader
                action={
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={copyResultJSON}
                    className="flex items-center gap-1 text-[11.5px] text-text-muted hover:text-text-primary"
                  >
                    {copied ? <Check size={14} className="text-emerald-400" /> : <Copy size={14} />}
                    {copied ? 'Copied' : 'Copy JSON'}
                  </Button>
                }
              >
                <CardTitle icon={<ShieldCheck size={18} className="text-emerald-400" />}>
                  Prediction Result
                </CardTitle>
              </CardHeader>

              <div className="space-y-5">
                {/* Score & Risk Level Card */}
                {(() => {
                  const cfg = getRiskBadgeConfig(result.risk_level);
                  const percentage = (result.fraud_probability * 100).toFixed(2);
                  return (
                    <div className={`p-4 rounded-xl border ${cfg.border} ${cfg.bg} space-y-3`}>
                      <div className="flex items-center justify-between">
                        <span className="text-[12px] uppercase font-semibold tracking-wider text-text-muted">
                          Fraud Probability
                        </span>
                        <Badge variant={cfg.variant}>{cfg.label}</Badge>
                      </div>

                      <div className="flex items-baseline gap-2">
                        <span className={`text-4xl font-extrabold tracking-tight ${cfg.textColor}`}>
                          {percentage}%
                        </span>
                        <span className="text-[13px] text-text-muted">
                          ({result.fraud_probability.toFixed(6)})
                        </span>
                      </div>

                      {/* Visual Probability Meter */}
                      <div className="space-y-1.5 pt-1">
                        <div className="w-full h-3 rounded-full bg-bg-main border border-border-subtle/50 overflow-hidden relative">
                          <div
                            className={`h-full rounded-full bg-gradient-to-r ${cfg.barColor} transition-all duration-700`}
                            style={{ width: `${Math.min(100, Math.max(2, result.fraud_probability * 100))}%` }}
                          />
                        </div>

                        {/* Cutoff markers */}
                        <div className="flex justify-between text-[10.5px] text-text-muted pt-0.5 font-mono">
                          <span>0% (Safe)</span>
                          <span className="text-emerald-400/80">Approve: &lt;12%</span>
                          <span className="text-amber-400/80">Review: 12-16%</span>
                          <span className="text-orange-400/80">Step Up: 16-20%</span>
                          <span className="text-rose-400/80">Decline: &gt;20%</span>
                          <span>100%</span>
                        </div>
                      </div>

                      <p className="text-[12px] text-text-secondary leading-relaxed pt-1">
                        {cfg.desc}
                      </p>
                    </div>
                  );
                })()}

                {/* HYBRID RISK ASSESSMENT SECTION */}
                {(() => {
                  const dCfg = getDecisionBadgeConfig(result.final_decision);
                  return (
                    <div className="p-4 rounded-xl border border-border-subtle/80 bg-bg-card-secondary/40 space-y-4">
                      <div className="flex items-center justify-between pb-2 border-b border-border-subtle/50">
                        <div className="flex items-center gap-2">
                          <ShieldCheck size={16} className="text-brand-bright" />
                          <span className="text-[12px] uppercase font-bold tracking-wider text-text-primary">
                            Hybrid Risk Assessment
                          </span>
                        </div>
                        <Badge variant={dCfg.variant} className="font-bold text-[12px] px-2.5 py-0.5">
                          FINAL: {dCfg.label}
                        </Badge>
                      </div>

                      {/* 4 Pillars Grid: Model Risk, Base Decision, Recommended Intervention, Final Decision */}
                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-center">
                        <div className="p-2 rounded-lg bg-bg-main/70 border border-border-subtle/60">
                          <span className="text-[10px] uppercase font-semibold text-text-muted block mb-0.5">
                            1. Model Risk
                          </span>
                          <span className="text-[14px] font-bold text-text-primary block">
                            {(result.fraud_probability * 100).toFixed(2)}%
                          </span>
                          <span className="text-[10px] text-text-muted font-medium">{result.risk_level}</span>
                        </div>

                        <div className="p-2 rounded-lg bg-bg-main/70 border border-border-subtle/60">
                          <span className="text-[10px] uppercase font-semibold text-text-muted block mb-0.5">
                            2. Base Decision
                          </span>
                          <span className="text-[13px] font-bold text-text-secondary block mt-0.5">
                            {result.base_decision || 'APPROVE'}
                          </span>
                          <span className="text-[9.5px] text-text-muted">ML Boundary</span>
                        </div>

                        <div className="p-2 rounded-lg bg-bg-main/70 border border-border-subtle/60">
                          <span className="text-[10px] uppercase font-semibold text-text-muted block mb-0.5">
                            3. Recommended
                          </span>
                          <span className="text-[13px] font-bold text-brand-bright block mt-0.5">
                            {result.hybrid_assessment?.recommended_minimum_decision || result.final_decision}
                          </span>
                          <span className="text-[9.5px] text-text-muted">Rule Fusion</span>
                        </div>

                        <div className="p-2 rounded-lg bg-bg-main/70 border border-border-subtle/60">
                          <span className="text-[10px] uppercase font-semibold text-text-muted block mb-0.5">
                            4. Final Action
                          </span>
                          <span className={`text-[13px] font-bold ${dCfg.textColor} block mt-0.5`}>
                            {result.final_decision}
                          </span>
                          <span className="text-[9.5px] text-text-muted">Guaranteed Safety</span>
                        </div>
                      </div>

                      {/* Evidence Conflict Banner if any */}
                      {result.hybrid_assessment?.conflict_status?.has_conflict && (
                        <div className="p-2.5 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-300 text-[11.5px] flex items-start gap-2">
                          <AlertTriangle size={15} className="shrink-0 text-amber-400 mt-0.5" />
                          <div>
                            <span className="font-semibold block text-amber-200">Evidence Conflict Detected</span>
                            {result.hybrid_assessment.conflict_status.reason}
                          </div>
                        </div>
                      )}

                      {/* Triggered Risk Signals (Rules) */}
                      <div className="space-y-2 pt-1">
                        <div className="flex items-center justify-between text-[11.5px]">
                          <span className="font-semibold uppercase tracking-wider text-text-muted flex items-center gap-1.5">
                            <Activity size={13} className="text-brand-bright" />
                            Triggered Risk Signals ({result.triggered_rules ? result.triggered_rules.length : 0})
                          </span>
                          {result.rule_policy_version && (
                            <span className="text-[10.5px] text-text-muted font-mono">
                              Policy v{result.rule_policy_version}
                            </span>
                          )}
                        </div>

                        {result.triggered_rules && result.triggered_rules.length > 0 ? (
                          <div className="space-y-1.5 max-h-[160px] overflow-y-auto pr-0.5">
                            {result.triggered_rules.map((rule, idx) => {
                              const rBadge = getDecisionBadgeConfig(rule.severity);
                              return (
                                <div
                                  key={idx}
                                  className="p-2 rounded-lg bg-bg-main/50 border border-border-subtle/40 text-[12px] space-y-1"
                                >
                                  <div className="flex items-center justify-between gap-2">
                                    <span className="font-medium text-text-primary text-[12px]">
                                      • {rule.rule_id}
                                    </span>
                                    <span className={`text-[10.5px] font-bold px-2 py-0.5 rounded ${rBadge.bg} ${rBadge.textColor} border ${rBadge.border}`}>
                                      {rule.severity} (Priority {rule.priority})
                                    </span>
                                  </div>
                                  <p className="text-[11.5px] text-text-muted leading-relaxed">
                                    {rule.description}
                                  </p>
                                  {rule.observed_values && Object.keys(rule.observed_values).length > 0 && (
                                    <div className="text-[10.5px] font-mono text-text-muted/80 bg-bg-card/40 p-1 rounded">
                                      Observed: {JSON.stringify(rule.observed_values)}
                                    </div>
                                  )}
                                </div>
                              );
                            })}
                          </div>
                        ) : (
                          <div className="p-2.5 rounded-lg bg-bg-main/40 border border-border-subtle/30 text-[12px] text-text-muted flex items-center gap-2">
                            <CheckCircle2 size={14} className="text-emerald-400 shrink-0" />
                            <span>No deterministic operational rules triggered. Standard baseline risk.</span>
                          </div>
                        )}
                      </div>

                      {/* Primary Decision Reason */}
                      <div className="pt-2 border-t border-border-subtle/50 text-[12px] flex items-baseline justify-between">
                        <span className="text-text-muted">Primary Decision Reason:</span>
                        <span className={`font-semibold ${dCfg.textColor}`}>{result.decision_reason}</span>
                      </div>
                    </div>
                  );
                })()}

                {/* Expandable Decision Trace & Audit Log */}
                <div className="border border-border-subtle/70 rounded-xl overflow-hidden bg-bg-card-secondary/30">
                  <button
                    type="button"
                    onClick={() => setShowTrace((p) => !p)}
                    className="w-full px-3.5 py-2.5 flex items-center justify-between text-[12.5px] font-medium text-text-secondary hover:text-text-primary transition-colors"
                  >
                    <span>Inspect Decision Trace & Rule Audit Log</span>
                    {showTrace ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
                  </button>

                  {showTrace && (
                    <div className="p-3 border-t border-border-subtle/70 max-h-[260px] overflow-y-auto space-y-2 text-[11.5px] font-mono">
                      {result.decision_trace && result.decision_trace.map((t, idx) => (
                        <div key={idx} className="p-2 rounded bg-bg-main/60 border border-border-subtle/30 space-y-0.5">
                          <div className="flex items-center justify-between text-brand-bright font-bold">
                            <span>[{t.stage}]</span>
                            {t.decision && <span className="text-text-primary">{t.decision}</span>}
                          </div>
                          {t.rule && <div className="text-text-muted">Rule: {t.rule}</div>}
                          {t.reason && <div className="text-text-secondary">Reason: {t.reason}</div>}
                          {t.proposed_decision && <div className="text-amber-400/90">Proposed: {t.proposed_decision}</div>}
                          {t.applied && <div className="text-emerald-400/90">Status: {t.applied}</div>}
                          {t.triggered_rules_count !== undefined && (
                            <div className="text-text-muted">Triggered Rules Count: {t.triggered_rules_count}</div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>


                {/* Metadata Grid */}
                <div className="grid grid-cols-2 gap-3 text-[12px]">
                  <div className="p-2.5 rounded-lg bg-bg-card-secondary/60 border border-border-subtle/60">
                    <span className="text-text-muted block text-[11px] mb-0.5">Transaction ID</span>
                    <span className="font-mono font-medium text-text-primary truncate block" title={result.transaction_id}>
                      {result.transaction_id}
                    </span>
                  </div>

                  <div className="p-2.5 rounded-lg bg-bg-card-secondary/60 border border-border-subtle/60">
                    <span className="text-text-muted block text-[11px] mb-0.5">Scored At (UTC)</span>
                    <span className="font-mono font-medium text-text-primary truncate block">
                      {new Date(result.scored_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                    </span>
                  </div>

                  <div className="p-2.5 rounded-lg bg-bg-card-secondary/60 border border-border-subtle/60">
                    <span className="text-text-muted block text-[11px] mb-0.5">Model Stack</span>
                    <span className="font-medium text-text-primary">
                      {result.model_track} ({result.model_version})
                    </span>
                  </div>

                  <div className="p-2.5 rounded-lg bg-bg-card-secondary/60 border border-border-subtle/60">
                    <span className="text-text-muted block text-[11px] mb-0.5">Calibrator</span>
                    <span className="font-medium text-emerald-400 capitalize">
                      {result.calibrator} Calibration
                    </span>
                  </div>
                </div>

                {/* Collapsible 15-Features Breakdown */}
                <div className="border border-border-subtle/70 rounded-xl overflow-hidden bg-bg-card-secondary/30">
                  <button
                    type="button"
                    onClick={() => setShowFeaturesTable((p) => !p)}
                    className="w-full px-3.5 py-2.5 flex items-center justify-between text-[12.5px] font-medium text-text-secondary hover:text-text-primary transition-colors"
                  >
                    <span>Inspect 15 Features Evaluated</span>
                    {showFeaturesTable ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
                  </button>

                  {showFeaturesTable && (
                    <div className="p-3 border-t border-border-subtle/70 max-h-[260px] overflow-y-auto">
                      <div className="space-y-1.5 font-mono text-[11.5px]">
                        {Object.entries(result.features_used).map(([key, val]) => (
                          <div
                            key={key}
                            className="flex items-center justify-between py-1 px-2 rounded bg-bg-main/50 border border-border-subtle/30"
                          >
                            <span className="text-text-muted">{key}</span>
                            <span className="text-text-primary font-semibold">
                              {typeof val === 'number' ? (Number.isInteger(val) ? val : val.toFixed(4)) : String(val)}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>

                {/* Score Another Transaction Action */}
                <div className="pt-2">
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={handleReset}
                    className="w-full py-2.5 flex items-center justify-center gap-2 text-[13px]"
                  >
                    <RotateCcw size={14} />
                    Score Another Transaction
                  </Button>
                </div>
              </div>
            </Card>
          )}

          {/* Initial / Empty State */}
          {!loading && !result && !apiError && (
            <Card className="text-center py-10 px-6 border-dashed border-border-subtle/80">
              <div className="w-12 h-12 rounded-full bg-brand/10 border border-brand/25 flex items-center justify-center mx-auto mb-3.5 text-brand-bright">
                <Activity size={22} />
              </div>
              <h3 className="text-[16px] font-semibold text-text-primary mb-1.5">
                Ready to Score
              </h3>
              <p className="text-[12.5px] text-text-muted max-w-[340px] mx-auto leading-relaxed mb-6">
                Fill in the transaction details on the left and click <strong>Score Transaction</strong> to generate real-time probability estimates.
              </p>

              <div className="p-3.5 rounded-xl bg-bg-card-secondary/60 border border-border-subtle text-left text-[12px] space-y-2 text-text-secondary">
                <div className="font-semibold text-text-primary text-[12.5px]">
                  Model Specification:
                </div>
                <div className="flex items-center gap-2">
                  <CheckCircle2 size={13} className="text-emerald-400 shrink-0" />
                  <span>Authoritative 15-Feature Contract</span>
                </div>
                <div className="flex items-center gap-2">
                  <CheckCircle2 size={13} className="text-emerald-400 shrink-0" />
                  <span>Frozen XGBoost (`XGBClassifier`) Inference</span>
                </div>
                <div className="flex items-center gap-2">
                  <CheckCircle2 size={13} className="text-emerald-400 shrink-0" />
                  <span>Isotonic Calibration (Brier: 0.0307)</span>
                </div>
              </div>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
