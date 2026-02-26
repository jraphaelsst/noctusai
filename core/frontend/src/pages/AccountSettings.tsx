import React, { useState, useEffect } from 'react';
import { useAuth } from '../lib/auth-context';
import { api } from '../lib/api';
import { useNavigate } from 'react-router-dom';

export function AccountSettings() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [nome, setNome] = useState('');
  const [avatarUrl, setAvatarUrl] = useState('');
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');

  useEffect(() => {
    if (user) {
      setNome(user.nome || '');
      setAvatarUrl(user.avatar_url || '');
    }
  }, [user]);

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setMessage('');
    try {
      const body: Record<string, string> = {};
      if (nome.trim()) body.nome = nome.trim();
      if (avatarUrl.trim()) body.avatar_url = avatarUrl.trim();
      await api.patch('/api/auth/profile', body);
      setMessage('Perfil atualizado com sucesso!');
    } catch (err: any) {
      setMessage(err.message || 'Erro ao atualizar perfil');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div style={{ maxWidth: 600, margin: '40px auto', padding: '0 20px' }}>
      <button
        onClick={() => navigate('/')}
        style={{
          background: 'none', border: 'none', cursor: 'pointer',
          color: '#2563eb', marginBottom: 20, fontSize: 14,
        }}
      >
        &larr; Voltar ao Dashboard
      </button>
      <h1 style={{ fontSize: 24, fontWeight: 'bold', marginBottom: 24 }}>
        Configurações da Conta
      </h1>

      <form onSubmit={handleSave}>
        <div style={{ marginBottom: 16 }}>
          <label style={{ display: 'block', fontWeight: 500, marginBottom: 4 }}>
            E-mail
          </label>
          <input
            type="email"
            value={user?.email || ''}
            disabled
            style={{
              width: '100%', padding: '8px 12px', borderRadius: 6,
              border: '1px solid #d1d5db', background: '#f9fafb', color: '#6b7280',
            }}
          />
          <small style={{ color: '#9ca3af' }}>O e-mail não pode ser alterado por aqui.</small>
        </div>

        <div style={{ marginBottom: 16 }}>
          <label style={{ display: 'block', fontWeight: 500, marginBottom: 4 }}>
            Nome
          </label>
          <input
            type="text"
            value={nome}
            onChange={e => setNome(e.target.value)}
            style={{
              width: '100%', padding: '8px 12px', borderRadius: 6,
              border: '1px solid #d1d5db',
            }}
          />
        </div>

        <div style={{ marginBottom: 24 }}>
          <label style={{ display: 'block', fontWeight: 500, marginBottom: 4 }}>
            URL do Avatar
          </label>
          <input
            type="url"
            value={avatarUrl}
            onChange={e => setAvatarUrl(e.target.value)}
            placeholder="https://..."
            style={{
              width: '100%', padding: '8px 12px', borderRadius: 6,
              border: '1px solid #d1d5db',
            }}
          />
        </div>

        {message && (
          <p style={{
            marginBottom: 16, padding: '8px 12px', borderRadius: 6,
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
          {saving ? 'Salvando...' : 'Salvar Alterações'}
        </button>
      </form>
    </div>
  );
}
