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
    return <div style={{ textAlign: 'center', padding: 60 }}>Carregando...</div>;
  }

  return (
    <div style={{ maxWidth: 700, margin: '40px auto', padding: '0 20px' }}>
      <button
        onClick={() => navigate('/')}
        style={{
          background: 'none', border: 'none', cursor: 'pointer',
          color: '#2563eb', marginBottom: 20, fontSize: 14,
        }}
      >
        &larr; Voltar ao Dashboard
      </button>
      <h1 style={{ fontSize: 24, fontWeight: 'bold', marginBottom: 8 }}>
        Configurações da Organização
      </h1>
      <p style={{ color: '#6b7280', marginBottom: 32 }}>
        Gerencie chaves de API e preferências da sua organização.
      </p>

      {/* Existing settings */}
      {settings.length > 0 && (
        <div style={{ marginBottom: 32 }}>
          {settings.map(s => (
            <div
              key={s.id}
              style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                padding: '14px 16px', marginBottom: 8, borderRadius: 8,
                border: '1px solid #e5e7eb', background: '#fff',
              }}
            >
              <div>
                <strong style={{ fontFamily: 'monospace' }}>{s.key}</strong>
                <div style={{ color: '#6b7280', fontSize: 13, marginTop: 2 }}>
                  {s.is_secret
                    ? (revealed[s.key] ? s.value : '********')
                    : s.value
                  }
                </div>
              </div>
              <div style={{ display: 'flex', gap: 8 }}>
                {s.is_secret && (
                  <button
                    onClick={() => toggleReveal(s.key)}
                    style={{
                      padding: '4px 10px', borderRadius: 4, border: '1px solid #d1d5db',
                      background: 'white', cursor: 'pointer', fontSize: 12,
                    }}
                  >
                    {revealed[s.key] ? 'Ocultar' : 'Revelar'}
                  </button>
                )}
                <button
                  onClick={() => startEdit(s)}
                  style={{
                    padding: '4px 10px', borderRadius: 4, border: '1px solid #d1d5db',
                    background: 'white', cursor: 'pointer', fontSize: 12,
                  }}
                >
                  Editar
                </button>
                <button
                  onClick={() => handleDelete(s.key)}
                  style={{
                    padding: '4px 10px', borderRadius: 4, border: '1px solid #fca5a5',
                    background: '#fef2f2', color: '#991b1b', cursor: 'pointer', fontSize: 12,
                  }}
                >
                  Remover
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Add/Edit form */}
      <div style={{
        padding: 20, borderRadius: 8, border: '1px solid #e5e7eb', background: '#f9fafb',
      }}>
        <h3 style={{ marginBottom: 16, fontSize: 16 }}>
          {editKey && settings.some(s => s.key === editKey) ? 'Editar Configuração' : 'Adicionar Configuração'}
        </h3>
        <form onSubmit={handleSave}>
          <div style={{ marginBottom: 12 }}>
            <label style={{ display: 'block', fontWeight: 500, marginBottom: 4 }}>Chave</label>
            <input
              type="text"
              value={editKey}
              onChange={e => setEditKey(e.target.value)}
              placeholder="ex: openai_api_key"
              required
              style={{
                width: '100%', padding: '8px 12px', borderRadius: 6,
                border: '1px solid #d1d5db',
              }}
            />
          </div>
          <div style={{ marginBottom: 12 }}>
            <label style={{ display: 'block', fontWeight: 500, marginBottom: 4 }}>Valor</label>
            <input
              type={editIsSecret ? 'password' : 'text'}
              value={editValue}
              onChange={e => setEditValue(e.target.value)}
              placeholder="Valor da configuração"
              required
              style={{
                width: '100%', padding: '8px 12px', borderRadius: 6,
                border: '1px solid #d1d5db',
              }}
            />
          </div>
          <div style={{ marginBottom: 16 }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <input
                type="checkbox"
                checked={editIsSecret}
                onChange={e => setEditIsSecret(e.target.checked)}
              />
              Valor secreto
            </label>
          </div>

          {message && (
            <p style={{
              marginBottom: 12, padding: '8px 12px', borderRadius: 6,
              background: message.includes('sucesso') ? '#dcfce7' : '#fef2f2',
              color: message.includes('sucesso') ? '#166534' : '#991b1b',
            }}>
              {message}
            </p>
          )}

          <button
            type="submit"
            disabled={saving}
            style={{
              padding: '10px 24px', borderRadius: 6, border: 'none',
              background: '#2563eb', color: 'white', fontWeight: 500,
              cursor: saving ? 'not-allowed' : 'pointer',
              opacity: saving ? 0.7 : 1,
            }}
          >
            {saving ? 'Salvando...' : 'Salvar'}
          </button>
        </form>
      </div>
    </div>
  );
}
