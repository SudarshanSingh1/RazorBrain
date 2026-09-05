import { safeFormatDate } from '../utils/date';
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { 
  getSummary, getTransactions, getTrends 
} from '../api';
import { 
  Shield, Clock, CheckCircle, 
  BarChart2, Activity, Hexagon, Cpu, Zap, List, Search, TrendingUp
} from 'lucide-react';
import { 
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
  PieChart, Pie, Cell
} from 'recharts';
import { Card, CardHeader, CardTitle, DataTable, Badge, Button, SearchInput, LinkText } from '../components/ui';
import type { Column } from '../components/ui';

export default function Overview() {
  const navigate = useNavigate();
  const [summary, setSummary] = useState<any>(null);
  const [transactions, setTransactions] = useState<any[]>([]);
  const [trends, setTrends] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      getSummary().catch(() => ({ data: { total_assessments: 0, decisions: { ALLOW: 0, REVIEW: 0, BLOCK: 0 } } })),
      getTransactions({ limit: 5 }).catch(() => ({ data: { data: [] } })),
      getTrends().catch(() => ({ data: [] }))
    ]).then(([summaryRes, txnRes, trendsRes]) => {
      setSummary(summaryRes.data);
      setTransactions(txnRes.data.data);
      setTrends(trendsRes.data);
      setLoading(false);
    });
  }, []);

  if (loading) {
    return (
      <div className="flex h-[calc(100vh-12rem)] items-center justify-center space-x-2">
        <div className="w-4 h-4 bg-brand rounded-full animate-bounce"></div>
        <div className="w-4 h-4 bg-brand rounded-full animate-bounce delay-75"></div>
        <div className="w-4 h-4 bg-brand rounded-full animate-bounce delay-150"></div>
      </div>
    );
  }

  const { total_assessments, decisions } = summary || { total_assessments: 0, decisions: { ALLOW: 0, REVIEW: 0, BLOCK: 0 } };
  const allowed = decisions.ALLOW || 0;
  const review = decisions.REVIEW || 0;
  const blocked = decisions.BLOCK || 0;
  
  const pctAllowed = total_assessments ? ((allowed / total_assessments) * 100).toFixed(1) : '0.0';
  const pctReview = total_assessments ? ((review / total_assessments) * 100).toFixed(1) : '0.0';
  const pctBlocked = total_assessments ? ((blocked / total_assessments) * 100).toFixed(1) : '0.0';

  const pieData = [
    { name: 'Allowed', value: allowed, color: '#10b981' },
    { name: 'Under Review', value: review, color: '#f59e0b' },
    { name: 'Blocked', value: blocked, color: '#f43f5e' }
  ];

  const columns: Column<any>[] = [
    {
      header: 'TIMESTAMP',
      cell: (row) => (
        <span className="font-mono text-text-secondary text-[11px]">
          {safeFormatDate(row.timestamp)}
        </span>
      )
    },
    {
      header: 'PAYMENT ID',
      cell: (row) => (
        <LinkText className="text-[11px]" onClick={() => navigate(`/transactions/${row.assessment_id}`)}>
          {row.transaction_id}
        </LinkText>
      )
    },
    {
      header: 'ORDER ID',
      cell: (row) => {
        let orderId = '-';
        if (row.context_data) {
          try {
             const ctx = typeof row.context_data === 'string' ? JSON.parse(row.context_data) : row.context_data;
             orderId = ctx.order_id || '-';
          } catch {
             orderId = '-';
          }
        }
        return <span className="font-mono text-text-secondary text-[11px] truncate max-w-[150px] block">{orderId}</span>;
      }
    },
    {
      header: 'AMOUNT',
      cell: (row) => <span className="font-mono text-[11px]">₹{row.amount?.toFixed(2)}</span>
    },
    {
      header: 'RISK',
      cell: (row) => (
        <span className="font-mono font-medium text-[11px]">
          {row.primary_risk_probability !== null ? (row.primary_risk_probability * 100).toFixed(2) + '%' : '—'}
        </span>
      )
    },
    {
      header: 'DECISION',
      cell: (row) => {
        switch(row.decision) {
          case 'ALLOW': return <Badge variant="success">ALLOW</Badge>;
          case 'REVIEW': return <Badge variant="warning">REVIEW</Badge>;
          case 'BLOCK': return <Badge variant="danger">BLOCK</Badge>;
          default: return null;
        }
      }
    },
    {
      header: 'STATUS',
      cell: (row) => {
        let conf = row.confidence_in_probability;
        return <Badge variant={conf === 'HIGH' ? 'default' : 'secondary'} className={conf === 'HIGH' ? 'bg-brand/15 text-brand-bright border-brand/30' : ''}>{conf}</Badge>;
      }
    },
    {
      header: 'ACTION',
      className: 'text-right',
      cell: (row) => (
        <Button 
          variant="secondary"
          size="sm"
          className="text-[11px] h-7 px-3 bg-brand/10 text-brand-bright border-brand/30 hover:bg-brand/20 hover:border-brand/50"
          onClick={() => navigate(`/transactions/${row.assessment_id}`)}
        >
          Inspect
        </Button>
      )
    }
  ];

  

  return (
    <div className="space-y-4 md:space-y-6 animate-in fade-in duration-500">
      
      {/* Top row cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 md:gap-6">
        
        {/* Total Transactions */}
        <div className="bg-brand/10 border border-brand/40 p-4 md:p-5 rounded-[12px] flex flex-col justify-between h-[120px] shadow-[0_0_20px_rgba(47,128,237,0.1)] relative overflow-hidden group">
          <div className="absolute top-0 right-0 w-32 h-32 bg-brand/20 rounded-full blur-[40px] -mr-10 -mt-10 pointer-events-none group-hover:bg-brand/30 transition-all"></div>
          <div className="flex items-center gap-2 text-text-primary z-10">
            <div className="w-8 h-8 rounded-full bg-brand flex items-center justify-center shadow-lg">
              <Activity size={16} className="text-white" />
            </div>
            <span className="text-[13px] font-medium text-text-secondary">Total Transactions</span>
          </div>
          <div className="z-10 mt-auto">
            <div className="flex items-baseline gap-3">
              <span className="text-[32px] font-bold text-text-primary leading-none">{total_assessments}</span>
              <div className="text-[11px] flex flex-col">
                <span className="text-accent-green font-medium flex items-center"><TrendingUp size={12} className="mr-0.5" /> +100%</span>
                <span className="text-text-muted">vs previous period</span>
              </div>
            </div>
          </div>
        </div>

        {/* Allowed */}
        <div className="bg-bg-card border border-accent-green/30 p-4 md:p-5 rounded-[12px] flex flex-col justify-between h-[120px] shadow-sm relative overflow-hidden group">
          <div className="absolute top-0 right-0 w-24 h-24 bg-accent-green/10 rounded-full blur-[30px] -mr-8 -mt-8 pointer-events-none group-hover:bg-accent-green/20 transition-all"></div>
          <div className="flex items-center gap-2 text-text-primary z-10">
            <div className="w-8 h-8 rounded-full bg-accent-green/20 flex items-center justify-center border border-accent-green/30">
              <CheckCircle size={16} className="text-accent-green" />
            </div>
            <span className="text-[13px] font-medium text-text-secondary">Allowed</span>
          </div>
          <div className="z-10 mt-auto">
            <span className="text-[32px] font-bold text-text-primary leading-none block mb-1">{allowed}</span>
            <div className="text-[11px] text-text-muted">
              {pctAllowed}% of total
            </div>
          </div>
        </div>

        {/* Under Review */}
        <div className="bg-bg-card border border-accent-yellow/30 p-4 md:p-5 rounded-[12px] flex flex-col justify-between h-[120px] shadow-sm relative overflow-hidden group">
          <div className="absolute top-0 right-0 w-24 h-24 bg-accent-yellow/10 rounded-full blur-[30px] -mr-8 -mt-8 pointer-events-none group-hover:bg-accent-yellow/20 transition-all"></div>
          <div className="flex items-center gap-2 text-text-primary z-10">
            <div className="w-8 h-8 rounded-full bg-accent-yellow/20 flex items-center justify-center border border-accent-yellow/30">
              <Clock size={16} className="text-accent-yellow" />
            </div>
            <span className="text-[13px] font-medium text-text-secondary">Under Review</span>
          </div>
          <div className="z-10 mt-auto">
            <span className="text-[32px] font-bold text-text-primary leading-none block mb-1">{review}</span>
            <div className="text-[11px] text-text-muted">
              {pctReview}% of total
            </div>
          </div>
        </div>

        {/* Blocked */}
        <div className="bg-bg-card border border-accent-red/30 p-4 md:p-5 rounded-[12px] flex flex-col justify-between h-[120px] shadow-sm relative overflow-hidden group">
          <div className="absolute top-0 right-0 w-24 h-24 bg-accent-red/10 rounded-full blur-[30px] -mr-8 -mt-8 pointer-events-none group-hover:bg-accent-red/20 transition-all"></div>
          <div className="flex items-center gap-2 text-text-primary z-10">
            <div className="w-8 h-8 rounded-full bg-accent-red/20 flex items-center justify-center border border-accent-red/30">
              <Shield size={16} className="text-accent-red" />
            </div>
            <span className="text-[13px] font-medium text-text-secondary">Blocked</span>
          </div>
          <div className="z-10 mt-auto">
            <span className="text-[32px] font-bold text-text-primary leading-none block mb-1">{blocked}</span>
            <div className="text-[11px] text-text-muted">
              {pctBlocked}% of total
            </div>
          </div>
        </div>

      </div>

      {/* Middle row: Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 md:gap-6">
        
        {/* Decision Distribution */}
        <Card className="h-[280px] flex flex-col">
          <CardHeader className="pb-0">
            <CardTitle icon={<Shield size={16} className="text-brand-bright" />}>Decision Distribution</CardTitle>
          </CardHeader>
          <div className="flex-1 flex items-center justify-center">
            <div className="w-1/2 h-full flex items-center justify-center relative">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={pieData}
                    cx="50%"
                    cy="50%"
                    innerRadius={55}
                    outerRadius={75}
                    paddingAngle={2}
                    dataKey="value"
                    stroke="none"
                  >
                    {pieData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} />
                    ))}
                  </Pie>
                </PieChart>
              </ResponsiveContainer>
              <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
                <span className="text-2xl font-bold text-text-primary">{total_assessments}</span>
                <span className="text-[11px] text-text-muted">Total</span>
              </div>
            </div>
            <div className="w-1/2 pl-4 flex flex-col justify-center gap-3">
              {pieData.map(item => (
                <div key={item.name} className="flex items-center justify-between text-[12px]">
                  <div className="flex items-center gap-2">
                    <span className="w-2.5 h-2.5 rounded-sm" style={{ backgroundColor: item.color }}></span>
                    <span className="text-text-secondary">{item.name}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-text-primary">{item.value}</span>
                    <span className="text-text-muted w-12 text-right">({total_assessments ? ((item.value / total_assessments)*100).toFixed(1) : 0}%)</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </Card>

        {/* Transaction Volume */}
        <Card className="h-[280px] flex flex-col">
          <div className="flex items-center justify-between mb-4">
            <CardTitle icon={<BarChart2 size={16} className="text-brand-bright" />}>Transaction Volume</CardTitle>
            <select className="bg-bg-card-secondary border border-border-subtle rounded-[6px] px-2.5 py-1 text-[11px] text-text-secondary focus:outline-none focus:border-brand cursor-pointer hover:bg-[rgba(255,255,255,0.05)]">
              <option>Last 24 Hours</option>
              <option>Last 7 Days</option>
              <option>Last 30 Days</option>
            </select>
          </div>
          <div className="flex-1 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={trends} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
                <XAxis 
                  dataKey="date" 
                  stroke="#6e96d2" 
                  fontSize={10} 
                  tickLine={false} 
                  axisLine={false}
                  tickFormatter={(val) => {
                    const d = new Date(val);
                    return `${d.toLocaleString('en-US', { month: 'short' })} ${d.getDate().toString().padStart(2, '0')}`;
                  }}
                  dy={10}
                />
                <YAxis 
                  stroke="#6e96d2" 
                  fontSize={10} 
                  tickLine={false} 
                  axisLine={false} 
                  dx={-10}
                />
                <Tooltip 
                  cursor={{ fill: 'rgba(255,255,255,0.02)' }}
                  contentStyle={{ backgroundColor: '#09182d', borderColor: 'rgba(120,150,210,0.2)', borderRadius: '8px' }}
                />
                <Bar dataKey="TOTAL" fill="#4ea1ff" radius={[2, 2, 0, 0]} maxBarSize={40} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>

      </div>

      {/* Bottom Table */}
      <Card noPadding className="overflow-hidden flex flex-col h-[400px]">
        <div className="p-4 border-b border-border-subtle flex items-center justify-between bg-bg-card">
          <CardTitle icon={<List size={16} className="text-brand-bright" />}>Recent Transactions</CardTitle>
          <Button variant="secondary" size="sm" className="h-7 text-[11px]" onClick={() => navigate('/transactions')}>View All</Button>
        </div>
        
        <div className="px-4 py-3 border-b border-border-subtle bg-bg-card-secondary/50">
          <SearchInput placeholder="Search by payment ID, order ID, amount, decision..." />
        </div>

        <div className="flex-1 overflow-y-auto custom-scrollbar relative">
          <DataTable
            data={transactions}
            columns={columns}
            keyExtractor={(item) => item.assessment_id}
            onRowClick={(item) => navigate(`/transactions/${item.assessment_id}`)}
          />
        </div>
      </Card>

      {/* Bottom widgets */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 md:gap-6">
        
        {/* System Status */}
        <Card className="h-[220px] flex flex-col">
          <div className="flex items-center justify-between mb-4">
            <CardTitle icon={<Hexagon size={16} className="text-brand-bright" />}>System Status</CardTitle>
            <LinkText className="text-[11px]">View Details →</LinkText>
          </div>
          <div className="flex flex-col gap-3 flex-1 text-[12px]">
            <div className="flex items-center justify-between border-b border-border-subtle/50 pb-2">
              <div className="flex items-center gap-2 text-text-secondary"><span className="w-1.5 h-1.5 rounded-full bg-accent-green"></span> API Server</div>
              <span className="text-accent-green font-medium">Online</span>
            </div>
            <div className="flex items-center justify-between border-b border-border-subtle/50 pb-2">
              <div className="flex items-center gap-2 text-text-secondary"><span className="w-1.5 h-1.5 rounded-full bg-accent-green"></span> Database</div>
              <span className="text-accent-green font-medium">Connected</span>
            </div>
            <div className="flex items-center justify-between border-b border-border-subtle/50 pb-2">
              <div className="flex items-center gap-2 text-text-secondary"><span className="w-1.5 h-1.5 rounded-full bg-accent-green"></span> Razorpay Integration</div>
              <span className="text-accent-green font-medium">Connected</span>
            </div>
            <div className="flex items-center justify-between border-b border-border-subtle/50 pb-2">
              <div className="flex items-center gap-2 text-text-secondary"><span className="w-1.5 h-1.5 rounded-full bg-accent-green"></span> Model Service</div>
              <span className="text-accent-green font-medium">Ready</span>
            </div>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-text-secondary"><span className="w-1.5 h-1.5 rounded-full bg-accent-green"></span> Monitoring</div>
              <span className="text-accent-green font-medium">Active</span>
            </div>
          </div>
        </Card>

        {/* Model Information */}
        <Card className="h-[220px] flex flex-col">
          <div className="flex items-center justify-between mb-4">
            <CardTitle icon={<Cpu size={16} className="text-brand-bright" />}>Model Information</CardTitle>
            <LinkText className="text-[11px]">›</LinkText>
          </div>
          <div className="flex flex-col gap-4 flex-1 text-[12px]">
            <div className="grid grid-cols-[100px_1fr] items-center gap-2 border-b border-border-subtle/50 pb-3">
              <span className="text-text-muted">Model Track</span>
              <span className="text-text-primary text-right font-medium">RAZORPAY_SERVING_MODEL</span>
            </div>
            <div className="grid grid-cols-[100px_1fr] items-center gap-2 border-b border-border-subtle/50 pb-3">
              <span className="text-text-muted">Calibration</span>
              <span className="text-text-primary text-right font-medium">Isotonic Regression</span>
            </div>
            <div className="grid grid-cols-[100px_1fr] items-center gap-2 border-b border-border-subtle/50 pb-3">
              <span className="text-text-muted">Policy Thresholds</span>
              <span className="text-text-primary text-right font-medium">Review: 12.13% <span className="text-border-subtle mx-1">|</span> Block: 20.53%</span>
            </div>
            <div className="grid grid-cols-[100px_1fr] items-center gap-2">
              <span className="text-text-muted">Feature Set</span>
              <span className="text-text-primary text-right font-medium">15 Razorpay-compatible features</span>
            </div>
          </div>
        </Card>

        {/* Quick Actions */}
        <Card className="h-[220px] flex flex-col">
          <div className="flex items-center justify-between mb-4">
            <CardTitle icon={<Zap size={16} className="text-brand-bright" />}>Quick Actions</CardTitle>
            <LinkText className="text-[11px]">›</LinkText>
          </div>
          <div className="flex flex-col gap-3 flex-1">
            <Button 
              variant="secondary" 
              className="justify-start h-10 px-4 bg-bg-card-secondary border-border-subtle hover:bg-[rgba(255,255,255,0.05)] font-medium text-[12px] w-full"
              onClick={() => navigate('/razorpay-test')}
            >
              <div className="w-5 h-5 rounded-full bg-brand/20 flex items-center justify-center mr-3 border border-brand/30">
                <span className="text-brand font-bold text-xs">+</span>
              </div>
              Create Payment Order
            </Button>
            <Button 
              variant="secondary" 
              className="justify-between h-10 px-4 bg-bg-card-secondary border-border-subtle hover:bg-[rgba(255,255,255,0.05)] font-medium text-[12px] w-full"
              onClick={() => navigate('/review-queue')}
            >
              <div className="flex items-center">
                <div className="w-5 h-5 rounded bg-brand flex items-center justify-center mr-3">
                  <List size={12} className="text-white" />
                </div>
                View Review Queue
              </div>
              <div className="w-5 h-5 rounded-full bg-brand flex items-center justify-center text-[10px] font-bold text-white shadow-sm">
                {review}
              </div>
            </Button>
            <Button 
              variant="secondary" 
              className="justify-start h-10 px-4 bg-bg-card-secondary border-border-subtle hover:bg-[rgba(255,255,255,0.05)] font-medium text-[12px] w-full"
              onClick={() => navigate('/transactions')}
            >
              <div className="w-5 h-5 rounded-full flex items-center justify-center mr-3">
                <Search size={14} className="text-brand-bright" />
              </div>
              Explore Transactions
            </Button>
          </div>
        </Card>
      </div>
    </div>
  );
}
