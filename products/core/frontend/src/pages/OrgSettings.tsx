import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../lib/api';

interface OrgSetting {
  id: string;
  org_id: string;
  key: string;
  value: string;
  is_secret: boolean;
  updated_at: string;
}

export function OrgSettings() {
  const navigate = useNavigate();
  const [settings, setSettings] = useState<OrgSetting[]>([]);
  const [loading, setLoading] = useState(true);
  const [editKey, setEditKey] = useState('');
  const [editValue, setEditValue] = useState('');
  const [editIsSecret, setEditIsSecret] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');
  const [revealed, setRevealed] = useState<Record<string, boolean>>({});

  async function fetchSettings() {
    try {
      const res = await api.get('/api/settings/org');
      setSettings(res.data || []);
    } catch (err) {
      console.error('Error:', err);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { fetchSettings(); }, []);

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setMessage('');
    try {
      await api.put(`/api/settings/org/${editKey}`, {
        value: editValue,
        is_secret: editIsSecret,
      });
      setMessage('Configuração salva com sucesso!');
      setEditKey('');
      setEditValue('');
      setEditIsSecret(false);
      fetchSettings();
    } catch (err: any) {
      setMessage(err.message || 'Erro ao salvar');
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(key: string) {
    if (!confirm(`Remover configuração "${key}"?`)) return;
    try {
      await api.delete(`/api/settings/org/${key}`);
      fetchSettings();
    } catch (err: any) {
      alert(err.message);
    }
  }

  function toggleReveal(key: string) {
    setRevealed(prev => ({ ...prev, [key]: !prev[key] }));
  }

  function startEdit(setting: OrgSetting) {
    setEditKey(setting.key);
    setEditValue(setting.is_secret ? '' : setting.value);
    setEditIsSecret(setting.is_secret);
    setMessage('');
  }

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <p className="text-muted-foreground">Carregando...</p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl px-4 sm:px-6 lg:px-8 py-6 sm:py-8 lg:py-10">
      <button
        onClick={() => navigate('/')}
        className="mb-5 text-sm text-primary hover:underline"
      >
        &larr; Voltar ao Dashboard
      </button>
      <h1 className="mb-2 text-2xl font-bold text-foreground">
        Configurações da Organização
      </h1>
      <p className="mb-8 text-sm text-muted-foreground">
        Gerencie chaves de API e preferências da sua organização.
      </p>

      {/* Existing settings */}
      {settings.length > 0 && (
        <div className="mb-8 space-y-2">
          {settings.map(s => (
            <div
              key={s.id}
              className="flex items-center justify-between rounded-lg border border-border bg-card px-4 py-3.5"
            >
              <div>
                <strong className="font-mono text-sm text-foreground">{s.key}</strong>
                <div className="mt-0.5 text-xs text-muted-foreground">
                  {s.is_secret
                    ? (revealed[s.key] ? s.value : '********')
                    : s.value
                  }
                </div>
              </div>
              <div className="flex gap-2">
                {s.is_secret && (
                  <button
                    onClick={() => toggleReveal(s.key)}
                    className="rounded-md border border-border bg-background px-2.5 py-1 text-xs text-foreground hover:bg-muted"
                  >
                    {revealed[s.key] ? 'Ocultar' : 'Revelar'}
                  </button>
                )}
                <button
                  onClick={() => startEdit(s)}
                  className="rounded-md border border-border bg-background px-2.5 py-1 text-xs text-foreground hover:bg-muted"
                >
                  Editar
                </button>
                <button
                  onClick={() => handleDelete(s.key)}
                  className="rounded-md border border-red-200 bg-red-50 px-2.5 py-1 text-xs text-red-700 hover:bg-red-100"
                >
                  Remover
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Add/Edit form */}
      <div className="rounded-lg border border-border bg-muted/30 p-5">
        <h3 className="mb-4 text-base font-semibold text-foreground">
          {editKey && settings.some(s => s.key === editKey) ? 'Editar Configuração' : 'Adicionar Configuração'}
        </h3>
        <form onSubmit={handleSave} className="space-y-3">
          <div>
            <label className="mb-1 block text-sm font-medium text-foreground">Chave</label>
            <input
              type="text"
              value={editKey}
              onChange={e => setEditKey(e.target.value)}
              placeholder="ex: openai_api_key"
              required
              className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-foreground">Valor</label>
            <input
              type={editIsSecret ? 'password' : 'text'}
              value={editValue}
              onChange={e => setEditValue(e.target.value)}
              placeholder="Valor da configuração"
              required
              className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </div>
          <div>
            <label className="flex items-center gap-2 text-sm text-foreground">
              <input
                type="checkbox"
                checked={editIsSecret}
                onChange={e => setEditIsSecret(e.target.checked)}
                className="h-4 w-4 rounded border-border"
              />
              Valor secreto
            </label>
          </div>

          {message && (
            <p className={`rounded-md px-3 py-2 text-sm ${
              message.includes('sucesso')
                ? 'bg-green-50 text-green-800'
                : 'bg-red-50 text-red-800'
            }`}>
              {message}
            </p>
          )}

          <button
            type="submit"
            disabled={saving}
            className="rounded-md bg-primary px-6 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-70"
          >
            {saving ? 'Salvando...' : 'Salvar'}
          </button>
        </form>
      </div>
    </div>
  );
}
