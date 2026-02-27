import React, { useEffect, useState } from 'react';
import { api } from '../../lib/api';

interface PlatformSetting {
  key: string;
  value: string;
  description: string | null;
  is_secret: boolean;
  updated_at: string;
  updated_by: string | null;
}

const SUGGESTED_KEYS = [
  'openai_api_key',
  'stripe_secret_key',
  'sentry_dsn',
  'redis_url',
];

export function AdminSettings() {
  const [settings, setSettings] = useState<PlatformSetting[]>([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [editKey, setEditKey] = useState('');
  const [editValue, setEditValue] = useState('');
  const [editDescription, setEditDescription] = useState('');
  const [editIsSecret, setEditIsSecret] = useState(false);
  const [saving, setSaving] = useState(false);

  async function fetchSettings() {
    try {
      const res = await api.get('/api/settings/platform');
      setSettings(res.data || []);
    } catch (err) {
      console.error('Error fetching settings:', err);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { fetchSettings(); }, []);

  function openCreate() {
    setEditKey('');
    setEditValue('');
    setEditDescription('');
    setEditIsSecret(false);
    setShowModal(true);
  }

  function openEdit(setting: PlatformSetting) {
    setEditKey(setting.key);
    setEditValue(setting.is_secret ? '' : setting.value);
    setEditDescription(setting.description || '');
    setEditIsSecret(setting.is_secret);
    setShowModal(true);
  }

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      await api.put(`/api/settings/platform/${editKey}`, {
        value: editValue,
        description: editDescription || null,
        is_secret: editIsSecret,
      });
      setShowModal(false);
      fetchSettings();
    } catch (err: any) {
      alert(err.message);
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(key: string) {
    if (!confirm(`Remover configuração "${key}"?`)) return;
    try {
      await api.delete(`/api/settings/platform/${key}`);
      fetchSettings();
    } catch (err: any) {
      alert(err.message);
    }
  }

  if (loading) {
    return <div className="loading-screen"><div className="spinner" /><p>Carregando...</p></div>;
  }

  return (
    <div>
      <div className="admin-page-header">
        <div>
          <h1 className="admin-page-title">Configurações da Plataforma</h1>
          <p className="admin-page-subtitle">{settings.length} configurações</p>
        </div>
        <button className="btn-primary admin-btn" onClick={openCreate}>
          + Nova Configuração
        </button>
      </div>

      <div className="admin-table-wrapper">
        <table className="admin-table">
          <thead>
            <tr>
              <th>Chave</th>
              <th>Valor</th>
              <th>Descrição</th>
              <th>Atualizado em</th>
              <th>Ações</th>
            </tr>
          </thead>
          <tbody>
            {settings.map(s => (
              <tr key={s.key}>
                <td className="admin-table-primary"><code>{s.key}</code></td>
                <td>
                  {s.is_secret
                    ? <span className="badge badge-sm">secreto</span>
                    : <code>{s.value}</code>
                  }
                </td>
                <td>{s.description || '-'}</td>
                <td>{s.updated_at ? new Date(s.updated_at).toLocaleDateString('pt-BR') : '-'}</td>
                <td>
                  <button className="btn-sm" onClick={() => openEdit(s)}>Editar</button>
                  {' '}
                  <button className="btn-sm btn-danger" onClick={() => handleDelete(s.key)}>Remover</button>
                </td>
              </tr>
            ))}
            {settings.length === 0 && (
              <tr><td colSpan={5} className="admin-table-empty">Nenhuma configuração encontrada</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {showModal && (
        <div className="modal-overlay" onClick={() => setShowModal(false)}>
          <div className="modal-content" onClick={e => e.stopPropagation()}>
            <h2>{editKey && settings.some(s => s.key === editKey) ? 'Editar Configuração' : 'Nova Configuração'}</h2>
            <form onSubmit={handleSave}>
              <div className="field">
                <label>Chave</label>
                {settings.some(s => s.key === editKey) ? (
                  <input type="text" value={editKey} disabled />
                ) : (
                  <>
                    <input
                      type="text"
                      value={editKey}
                      onChange={e => setEditKey(e.target.value)}
                      placeholder="ex: openai_api_key"
                      required
                      list="suggested-keys"
                    />
                    <datalist id="suggested-keys">
                      {SUGGESTED_KEYS.filter(k => !settings.some(s => s.key === k)).map(k => (
                        <option key={k} value={k} />
                      ))}
                    </datalist>
                  </>
                )}
              </div>
              <div className="field">
                <label>Valor</label>
                <input
                  type={editIsSecret ? 'password' : 'text'}
                  value={editValue}
                  onChange={e => setEditValue(e.target.value)}
                  placeholder={editIsSecret ? 'Digite o novo valor...' : 'Valor da configuração'}
                  required
                />
              </div>
              <div className="field">
                <label>Descrição (opcional)</label>
                <input
                  type="text"
                  value={editDescription}
                  onChange={e => setEditDescription(e.target.value)}
                  placeholder="Descrição da configuração"
                />
              </div>
              <div className="field">
                <label className="admin-scope-option">
                  <input
                    type="checkbox"
                    checked={editIsSecret}
                    onChange={e => setEditIsSecret(e.target.checked)}
                  />
                  Valor secreto (será mascarado na listagem)
                </label>
              </div>
              <div className="modal-actions">
                <button type="button" className="btn-secondary" onClick={() => setShowModal(false)}>Cancelar</button>
                <button type="submit" className="btn-primary admin-btn" disabled={saving}>
                  {saving ? 'Salvando...' : 'Salvar'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
