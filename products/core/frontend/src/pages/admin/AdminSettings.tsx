import React, { useEffect, useState } from 'react';
import { api } from '../../lib/api';
import { StatusPaginaPanel } from '@noctusai/lib';

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
    if (!confirm(`Remover configuracao "${key}"?`)) return;
    try {
      await api.delete(`/api/settings/platform/${key}`);
      fetchSettings();
    } catch (err: any) {
      alert(err.message);
    }
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
          <h1 className="text-2xl font-bold text-foreground">Configuracoes da Plataforma</h1>
          <p className="text-muted-foreground mt-1">{settings.length} configuracoes</p>
        </div>
        <button
          className="bg-primary text-primary-foreground rounded-md px-4 py-2 text-sm font-medium hover:bg-primary/90 transition-colors"
          onClick={openCreate}
        >
          + Nova Configuracao
        </button>
      </div>

      <div className="bg-card rounded-lg border border-border shadow-sm overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-muted/50">
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Chave</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Valor</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Descricao</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Atualizado em</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Acoes</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {settings.map(s => (
              <tr key={s.key} className="hover:bg-muted/50 transition-colors">
                <td className="px-4 py-3 font-medium text-foreground">
                  <code className="text-sm bg-muted px-1.5 py-0.5 rounded">{s.key}</code>
                </td>
                <td className="px-4 py-3">
                  {s.is_secret
                    ? <span className="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium bg-muted text-muted-foreground">secreto</span>
                    : <code className="text-sm bg-muted px-1.5 py-0.5 rounded">{s.value}</code>
                  }
                </td>
                <td className="px-4 py-3 text-muted-foreground">{s.description || '-'}</td>
                <td className="px-4 py-3 text-muted-foreground">{s.updated_at ? new Date(s.updated_at).toLocaleDateString('pt-BR') : '-'}</td>
                <td className="px-4 py-3">
                  <div className="flex gap-2">
                    <button
                      className="text-xs border border-border bg-card text-foreground rounded-md px-3 py-1.5 hover:bg-accent transition-colors"
                      onClick={() => openEdit(s)}
                    >
                      Editar
                    </button>
                    <button
                      className="text-xs bg-danger/10 text-danger rounded-md px-3 py-1.5 hover:bg-danger/20 transition-colors"
                      onClick={() => handleDelete(s.key)}
                    >
                      Remover
                    </button>
                  </div>
                </td>
              </tr>
            ))}
            {settings.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-muted-foreground">
                  Nenhuma configuracao encontrada
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {showModal && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={() => setShowModal(false)}>
          <div className="bg-card rounded-lg border border-border shadow-lg w-full max-w-md p-6" onClick={e => e.stopPropagation()}>
            <h2 className="text-lg font-semibold text-foreground mb-4">
              {editKey && settings.some(s => s.key === editKey) ? 'Editar Configuracao' : 'Nova Configuracao'}
            </h2>
            <form onSubmit={handleSave} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">Chave</label>
                {settings.some(s => s.key === editKey) ? (
                  <input
                    type="text"
                    value={editKey}
                    disabled
                    className="w-full h-10 rounded-md border border-border bg-muted px-3 text-sm text-muted-foreground"
                  />
                ) : (
                  <>
                    <input
                      type="text"
                      value={editKey}
                      onChange={e => setEditKey(e.target.value)}
                      placeholder="ex: openai_api_key"
                      required
                      list="suggested-keys"
                      className="w-full h-10 rounded-md border border-border bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
                    />
                    <datalist id="suggested-keys">
                      {SUGGESTED_KEYS.filter(k => !settings.some(s => s.key === k)).map(k => (
                        <option key={k} value={k} />
                      ))}
                    </datalist>
                  </>
                )}
              </div>
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">Valor</label>
                <input
                  type={editIsSecret ? 'password' : 'text'}
                  value={editValue}
                  onChange={e => setEditValue(e.target.value)}
                  placeholder={editIsSecret ? 'Digite o novo valor...' : 'Valor da configuracao'}
                  required
                  className="w-full h-10 rounded-md border border-border bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">Descricao (opcional)</label>
                <input
                  type="text"
                  value={editDescription}
                  onChange={e => setEditDescription(e.target.value)}
                  placeholder="Descricao da configuracao"
                  className="w-full h-10 rounded-md border border-border bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
                />
              </div>
              <div>
                <label className="flex items-center gap-2 text-sm text-foreground cursor-pointer">
                  <input
                    type="checkbox"
                    checked={editIsSecret}
                    onChange={e => setEditIsSecret(e.target.checked)}
                    className="rounded border-border"
                  />
                  Valor secreto (sera mascarado na listagem)
                </label>
              </div>
              <div className="flex justify-end gap-3 pt-2">
                <button
                  type="button"
                  className="border border-border bg-card text-foreground rounded-md px-4 py-2 text-sm hover:bg-accent transition-colors"
                  onClick={() => setShowModal(false)}
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  className="bg-primary text-primary-foreground rounded-md px-4 py-2 text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
                  disabled={saving}
                >
                  {saving ? 'Salvando...' : 'Salvar'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Page-visibility control — the status_pagina write-side organ (seed lib).
          This /admin/* route group is already admin-gated by CoreLayout
          (redirects non-admins before this component ever renders). */}
      <div className="mt-6">
        <StatusPaginaPanel api={api} enabled />
      </div>
    </div>
  );
}
