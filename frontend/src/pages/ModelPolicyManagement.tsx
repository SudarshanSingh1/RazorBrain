import { useState, useEffect } from 'react';
import { Card, CardHeader, CardTitle } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { getModels, getPolicies, activateModel, activatePolicy } from '../services/api';
import { Database, Shield } from 'lucide-react';

export default function ModelPolicyManagement() {
  const [models, setModels] = useState<any[]>([]);
  const [policies, setPolicies] = useState<any[]>([]);
  const [activeTab, setActiveTab] = useState<'models'|'policies'>('models');
  const [loading, setLoading] = useState(false);

  const loadData = async () => {
    try {
      const [mRes, pRes] = await Promise.all([getModels(), getPolicies()]);
      setModels(mRes.data.models || []);
      setPolicies(pRes.data.policies || []);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleActivateModel = async (id: string) => {
    if (!window.confirm("Are you sure you want to activate this model?")) return;
    setLoading(true);
    try {
      await activateModel(id);
      await loadData();
    } catch (e) {
      alert("Activation failed");
    }
    setLoading(false);
  };

  const handleActivatePolicy = async (id: string) => {
    if (!window.confirm("Are you sure you want to activate this policy?")) return;
    setLoading(true);
    try {
      await activatePolicy(id);
      await loadData();
    } catch (e) {
      alert("Activation failed");
    }
    setLoading(false);
  };

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold text-primary mb-2">Production Registry</h1>
          <p className="text-secondary">Manage ML models and decision policies.</p>
        </div>
      </div>

      <div className="flex gap-4 border-b border-border-subtle pb-2">
        <button 
          onClick={() => setActiveTab('models')}
          className={`flex items-center gap-2 font-medium px-4 py-2 rounded-t-lg ${activeTab === 'models' ? 'text-brand border-b-2 border-brand' : 'text-secondary hover:text-primary'}`}>
          <Database size={18}/> Models
        </button>
        <button 
          onClick={() => setActiveTab('policies')}
          className={`flex items-center gap-2 font-medium px-4 py-2 rounded-t-lg ${activeTab === 'policies' ? 'text-brand border-b-2 border-brand' : 'text-secondary hover:text-primary'}`}>
          <Shield size={18}/> Policies
        </button>
      </div>

      {activeTab === 'models' && (
        <Card className="bg-bg-card border-border-subtle">
          <CardHeader>
            <CardTitle className="text-primary flex items-center gap-2">
              Model Registry
            </CardTitle>
          </CardHeader>
          
            <div className="space-y-4">
              {models.map(m => (
                <div key={m.id} className={`p-4 rounded-lg border ${m.status === 'ACTIVE' ? 'border-brand bg-brand/5' : 'border-border-subtle bg-bg-card-secondary'}`}>
                  <div className="flex justify-between items-start mb-2">
                    <div>
                      <div className="flex items-center gap-3 mb-1">
                        <h3 className="text-lg font-semibold text-primary">{m.model_name}</h3>
                        <Badge variant={m.status === 'ACTIVE' ? 'success' : 'default'}>{m.status}</Badge>
                      </div>
                      <p className="text-sm text-secondary font-mono">Version: {m.model_version} | Contract: {m.feature_contract_version}</p>
                    </div>
                    {m.status !== 'ACTIVE' && (
                      <Button onClick={() => handleActivateModel(m.id)} disabled={loading} variant="primary" size="sm">
                        Activate
                      </Button>
                    )}
                  </div>
                  <div className="text-xs text-muted font-mono mt-2 pt-2 border-t border-border-subtle">
                    Path: {m.artifact_path} | Type: {m.model_type}
                  </div>
                </div>
              ))}
            </div>
          
        </Card>
      )}

      {activeTab === 'policies' && (
        <Card className="bg-bg-card border-border-subtle">
          <CardHeader>
            <CardTitle className="text-primary flex items-center gap-2">
              Policy Registry
            </CardTitle>
          </CardHeader>
          
            <div className="space-y-4">
              {policies.map(p => (
                <div key={p.id} className={`p-4 rounded-lg border ${p.status === 'ACTIVE' ? 'border-brand bg-brand/5' : 'border-border-subtle bg-bg-card-secondary'}`}>
                  <div className="flex justify-between items-start mb-2">
                    <div>
                      <div className="flex items-center gap-3 mb-1">
                        <h3 className="text-lg font-semibold text-primary">{p.policy_name}</h3>
                        <Badge variant={p.status === 'ACTIVE' ? 'success' : 'default'}>{p.status}</Badge>
                      </div>
                      <p className="text-sm text-secondary font-mono">Version: {p.policy_version}</p>
                    </div>
                    {p.status !== 'ACTIVE' && (
                      <Button onClick={() => handleActivatePolicy(p.id)} disabled={loading} variant="primary" size="sm">
                        Activate
                      </Button>
                    )}
                  </div>
                  <pre className="text-xs text-muted font-mono mt-2 p-2 bg-bg-main rounded border border-border-subtle overflow-auto max-h-32">
                    {p.configuration}
                  </pre>
                </div>
              ))}
            </div>
          
        </Card>
      )}
    </div>
  );
}
