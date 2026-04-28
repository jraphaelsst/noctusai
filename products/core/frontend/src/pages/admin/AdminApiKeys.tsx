import React, { useEffect, useState } from 'react';
import { api } from '../../lib/api';

interface ApiKey {
  id: string;
  org_id: string;
  name: string;
  key_prefix: string;
  scopes: string[];
  last_used_at: string | null;
  expires_at: string | null;
  is_active: boolean;
  created_at: string;
  organizations?: { id: string; nome: string };
}

export function AdminApiKeys() {
  const [keys, setKeys] = useState<ApiKey[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [newKeyName, setNewKeyName] = useState('');
  const [newKeyScopes, setNewKeyScopes] = useState<string[]>(['read']);
  const [createdKey, setCreatedKey] = useState<string | null>(null);

  async function fetchKeys() {
    try {
      const res = await api.get('/api/admin/api-keys');
      setKeys(res.data || []);
    } catch (err) {
      console.error('Error:', err);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { fetchKeys(); }, []);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    try {
      const res = await api.post('/api/api-keys', { name: newKeyName, scopes: newKeyScopes });
      setCreatedKey(res.data.raw_key);
      setNewKeyName('');
      setNewKeyScopes(['read']);
      fetchKeys();
    } catch (err: any) {
      alert(err.message);
    }
  }

  async function handleRevoke(id: string) {
    if (!confirm('Revogar esta chave API?')) return;
    try {
      await api.delete(`/api/api-keys/${id}`);
      fetchKeys();
    } catch (err: any) {
      alert(err.message);
    }
  }

  function toggleScope(scope: string) {
    setNewKeyScopes(prev =>
      prev.includes(scope) ? prev.filter(s => s !== scope) : [...prev, scope]
    );
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
        <p className="ml-3 text-muted-foreground">Carregando...</p>
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Chaves API</h1>
          <p className="text-muted-foreground mt-1">{keys.filter(k => k.is_active).length} chaves ativas</p>
        </div>
        <button
          className="bg-primary text-primary-foreground rounded-md px-4 py-2 text-sm font-medium hover:bg-primary/90 transition-colors"
          onClick={() => { setShowCreate(true); setCreatedKey(null); }}
        >
          + Nova Chave
        </button>
      </div>

      {/* Newly created key warning */}
      {createdKey && (
        <div className="mb-4 bg-warning/10 border border-warning/30 rounded-lg p-4 flex flex-wrap items-center gap-3">
          <span className="text-sm font-medium text-foreground">Chave criada! Copie agora, ela nao sera exibida novamente:</span>
          <code className="bg-muted px-3 py-1.5 rounded text-sm font-mono break-all">{createdKey}</code>
          <button
            className="text-xs border border-border bg-card text-foreground rounded-md px-3 py-1.5 hover:bg-accent transition-colors"
            onClick={() => { navigator.clipboard.writeText(createdKey); }}
          >
            Copiar
          </button>
        </div>
      )}

      <div className="bg-card rounded-lg border border-border shadow-sm overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-muted/50">
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Nome</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Organizacao</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Prefixo</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Escopos</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Status</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Criada em</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Acoes</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {keys.map(key => (
              <tr key={key.id} className={`hover:bg-muted/50 transition-colors ${!key.is_active ? 'opacity-50' : ''}`}>
                <td className="px-4 py-3 font-medium text-foreground">{key.name}</td>
                <td className="px-4 py-3 text-foreground">{key.organizations?.nome || key.org_id}</td>
                <td className="px-4 py-3">
                  <code className="text-sm bg-muted px-1.5 py-0.5 rounded">{key.key_prefix}...</code>
                </td>
                <td className="px-4 py-3">
                  <div className="flex flex-wrap gap-1">
                    {(key.scopes || []).map(s => (
                      <span key={s} className="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium bg-muted text-muted-foreground">
                        {s}
                      </span>
                    ))}
                  </div>
                </td>
                <td className="px-4 py-3">
                  <span className={`inline-flex items-center rounded-full px-2 py-1 text-xs font-medium ${
                    key.is_active ? 'bg-success/10 text-success' : 'bg-danger/10 text-danger'
                  }`}>
                    {key.is_active ? 'Ativa' : 'Revogada'}
                  </span>
                </td>
                <td className="px-4 py-3 text-muted-foreground">{new Date(key.created_at).toLocaleDateString('pt-BR')}</td>
                <td className="px-4 py-3">
                  {key.is_active && (
                    <button
                      className="text-xs bg-danger/10 text-danger rounded-md px-3 py-1.5 hover:bg-danger/20 transition-colors"
                      onClick={() => handleRevoke(key.id)}
                    >
                      Revogar
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {keys.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-muted-foreground">
                  Nenhuma chave API encontrada
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Create Modal */}
      {showCreate && !createdKey && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={() => setShowCreate(false)}>
          <div className="bg-card rounded-lg border border-border shadow-lg w-full max-w-md p-6" onClick={e => e.stopPropagation()}>
            <h2 className="text-lg font-semibold text-foreground mb-4">Nova Chave API</h2>
            <form onSubmit={handleCreate} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">Nome</label>
                <input
                  type="text"
                  value={newKeyName}
                  onChange={e => setNewKeyName(e.target.value)}
                  placeholder="Ex: Integracao Zapier"
                  required
                  className="w-full h-10 rounded-md border border-border bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-foreground mb-2">Escopos</label>
                <div className="flex flex-wrap gap-4">
                  {['read', 'write', 'admin'].map(scope => (
                    <label key={scope} className="flex items-center gap-2 text-sm text-foreground cursor-pointer">
                      <input
                        type="checkbox"
                        checked={newKeyScopes.includes(scope)}
                        onChange={() => toggleScope(scope)}
                        className="rounded border-border"
                      />
                      {scope}
                    </label>
                  ))}
                </div>
              </div>
              <div className="flex justify-end gap-3 pt-2">
                <button
                  type="button"
                  className="border border-border bg-card text-foreground rounded-md px-4 py-2 text-sm hover:bg-accent transition-colors"
                  onClick={() => setShowCreate(false)}
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  className="bg-primary text-primary-foreground rounded-md px-4 py-2 text-sm font-medium hover:bg-primary/90 transition-colors"
                >
                  Criar Chave
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
