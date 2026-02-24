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
    return <div className="loading-screen"><div className="spinner" /><p>Carregando...</p></div>;
  }

  return (
    <div>
      <div className="admin-page-header">
        <div>
          <h1 className="admin-page-title">Chaves API</h1>
          <p className="admin-page-subtitle">{keys.filter(k => k.is_active).length} chaves ativas</p>
        </div>
        <button className="btn-primary admin-btn" onClick={() => { setShowCreate(true); setCreatedKey(null); }}>
          + Nova Chave
        </button>
      </div>

      {/* Newly created key warning */}
      {createdKey && (
        <div className="admin-alert admin-alert-warning">
          <strong>Chave criada!</strong> Copie agora, ela não será exibida novamente:
          <code className="admin-key-display">{createdKey}</code>
          <button className="btn-sm" onClick={() => { navigator.clipboard.writeText(createdKey); }}>
            Copiar
          </button>
        </div>
      )}

      <div className="admin-table-wrapper">
        <table className="admin-table">
          <thead>
            <tr>
              <th>Nome</th>
              <th>Organização</th>
              <th>Prefixo</th>
              <th>Escopos</th>
              <th>Status</th>
              <th>Criada em</th>
              <th>Ações</th>
            </tr>
          </thead>
          <tbody>
            {keys.map(key => (
              <tr key={key.id} className={!key.is_active ? 'admin-row-inactive' : ''}>
                <td className="admin-table-primary">{key.name}</td>
                <td>{key.organizations?.nome || key.org_id}</td>
                <td><code>{key.key_prefix}...</code></td>
                <td>{(key.scopes || []).map(s => <span key={s} className="badge badge-sm">{s}</span>)}</td>
                <td>
                  <span className={`badge ${key.is_active ? 'badge-active' : 'badge-danger'}`}>
                    {key.is_active ? 'Ativa' : 'Revogada'}
                  </span>
                </td>
                <td>{new Date(key.created_at).toLocaleDateString('pt-BR')}</td>
                <td>
                  {key.is_active && (
                    <button className="btn-sm btn-danger" onClick={() => handleRevoke(key.id)}>
                      Revogar
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {keys.length === 0 && (
              <tr><td colSpan={7} className="admin-table-empty">Nenhuma chave API encontrada</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Create Modal */}
      {showCreate && !createdKey && (
        <div className="modal-overlay" onClick={() => setShowCreate(false)}>
          <div className="modal-content" onClick={e => e.stopPropagation()}>
            <h2>Nova Chave API</h2>
            <form onSubmit={handleCreate}>
              <div className="field">
                <label>Nome</label>
                <input
                  type="text"
                  value={newKeyName}
                  onChange={e => setNewKeyName(e.target.value)}
                  placeholder="Ex: Integração Zapier"
                  required
                />
              </div>
              <div className="field">
                <label>Escopos</label>
                <div className="admin-scopes">
                  {['read', 'write', 'admin'].map(scope => (
                    <label key={scope} className="admin-scope-option">
                      <input
                        type="checkbox"
                        checked={newKeyScopes.includes(scope)}
                        onChange={() => toggleScope(scope)}
                      />
                      {scope}
                    </label>
                  ))}
                </div>
              </div>
              <div className="modal-actions">
                <button type="button" className="btn-secondary" onClick={() => setShowCreate(false)}>Cancelar</button>
                <button type="submit" className="btn-primary admin-btn">Criar Chave</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
