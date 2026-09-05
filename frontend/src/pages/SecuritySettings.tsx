import { safeFormatDate } from '../utils/date';
import { useState, useEffect } from 'react';
import { Card, CardHeader, CardTitle } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { Shield, Key, RefreshCw, XCircle } from 'lucide-react';
import { getSecurityKeys, createSecurityKey, revokeSecurityKey, rotateSecurityKey } from '../services/api';

export default function SecuritySettings() {
  const [keys, setKeys] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [newSecret, setNewSecret] = useState<string | null>(null);

  const loadKeys = async () => {
    try {
      const res = await getSecurityKeys();
      setKeys(res.data?.keys || []);
    } catch (e) {
      console.error('Failed to load security keys:', e);
    }
  };

  useEffect(() => {
    loadKeys();
  }, []);

  const handleCreate = async () => {
    const name = prompt("Enter a name for the new API Key:");
    if (!name) return;
    setLoading(true);
    try {
      const res = await createSecurityKey({ name, role: 'SCORER' });
      setNewSecret(res.data?.raw_secret);
      await loadKeys();
    } catch (e) {
      alert("Failed to create key");
    }
    setLoading(false);
  };

  const handleRevoke = async (id: string) => {
    if (!window.confirm("Are you sure you want to revoke this key? This action cannot be undone.")) return;
    setLoading(true);
    try {
      await revokeSecurityKey(id);
      await loadKeys();
    } catch (e) {
      alert("Failed to revoke key");
    }
    setLoading(false);
  };

  const handleRotate = async (id: string) => {
    if (!window.confirm("Are you sure you want to rotate this key? A new key will be generated.")) return;
    const name = prompt("Enter a name for the rotated key:", "Rotated Key");
    if (!name) return;
    setLoading(true);
    try {
      const res = await rotateSecurityKey(id, { new_name: name, role: 'SCORER' });
      setNewSecret(res.data?.new_raw_secret);
      await loadKeys();
    } catch (e) {
      alert("Failed to rotate key");
    }
    setLoading(false);
  };

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold text-primary mb-2">Security Settings</h1>
          <p className="text-secondary">Manage API access keys and security tokens.</p>
        </div>
        <Button onClick={handleCreate} disabled={loading} className="flex items-center gap-2">
          <Key size={16} /> Generate New Key
        </Button>
      </div>

      {newSecret && (
        <Card className="bg-brand/10 border-brand mb-6">
          <div className="p-4">
            <h3 className="text-lg font-bold text-brand mb-2 flex items-center gap-2">
              <Shield size={20} /> Save your new API Key
            </h3>
            <p className="text-secondary text-sm mb-4">
              This is the <strong>only time</strong> we will show you this secret. Please copy it and store it securely.
            </p>
            <div className="bg-bg-main p-3 rounded font-mono text-primary text-lg border border-brand/30">
              {newSecret}
            </div>
            <Button onClick={() => setNewSecret(null)} variant="secondary" className="mt-4">
              I have saved this key
            </Button>
          </div>
        </Card>
      )}

      <Card className="bg-bg-card border-border-subtle">
        <CardHeader>
          <CardTitle className="text-primary flex items-center gap-2">
            <Key size={18}/> Active API Keys
          </CardTitle>
        </CardHeader>
        <div className="p-4 space-y-4">
          {keys.map(k => (
            <div key={k.id} className="p-4 rounded-lg border border-border-subtle bg-bg-card-secondary flex justify-between items-center">
              <div>
                <div className="flex items-center gap-3 mb-1">
                  <h3 className="font-semibold text-primary">{k.name}</h3>
                  <Badge variant={k.status === 'ACTIVE' ? 'success' : 'default'}>{k.status}</Badge>
                  <Badge variant="secondary">{k.role}</Badge>
                </div>
                <div className="font-mono text-sm text-secondary mb-1">Prefix: {k.prefix}</div>
                <div className="text-xs text-muted">
                  Created: {safeFormatDate(k.created_at)} | 
                  Last Used: {k.last_used_at ? safeFormatDate(k.last_used_at) : 'Never'}
                </div>
              </div>
              <div className="flex gap-2">
                {k.status === 'ACTIVE' && (
                  <>
                    <Button size="sm" variant="secondary" onClick={() => handleRotate(k.id)} disabled={loading} title="Rotate Key">
                      <RefreshCw size={14} />
                    </Button>
                    <Button size="sm" variant="secondary" onClick={() => handleRevoke(k.id)} disabled={loading} className="text-danger hover:text-danger-hover border-danger/50 hover:bg-danger/10" title="Revoke Key">
                      <XCircle size={14} />
                    </Button>
                  </>
                )}
              </div>
            </div>
          ))}
          {keys.length === 0 && (
            <div className="text-center p-8 text-secondary border border-dashed border-border-subtle rounded">
              No API keys found.
            </div>
          )}
        </div>
      </Card>
    </div>
  );
}
