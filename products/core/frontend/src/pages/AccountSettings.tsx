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
    <div className="mx-auto max-w-xl px-4 sm:px-6 lg:px-8 py-6 sm:py-8 lg:py-10">
      <button
        onClick={() => navigate('/')}
        className="mb-5 text-sm text-primary hover:underline"
      >
        &larr; Voltar ao Dashboard
      </button>
      <h1 className="mb-6 text-2xl font-bold text-foreground">
        Configurações da Conta
      </h1>

      <form onSubmit={handleSave} className="space-y-4">
        <div>
          <label className="mb-1 block text-sm font-medium text-foreground">
            E-mail
          </label>
          <input
            type="email"
            value={user?.email || ''}
            disabled
            className="h-10 w-full rounded-md border border-input bg-muted px-3 text-sm text-muted-foreground"
          />
          <p className="mt-1 text-xs text-muted-foreground">
            O e-mail não pode ser alterado por aqui.
          </p>
        </div>

        <div>
          <label className="mb-1 block text-sm font-medium text-foreground">
            Nome
          </label>
          <input
            type="text"
            value={nome}
            onChange={e => setNome(e.target.value)}
            className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
          />
        </div>

        <div>
          <label className="mb-1 block text-sm font-medium text-foreground">
            URL do Avatar
          </label>
          <input
            type="url"
            value={avatarUrl}
            onChange={e => setAvatarUrl(e.target.value)}
            placeholder="https://..."
            className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
          />
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
          {saving ? 'Salvando...' : 'Salvar Alterações'}
        </button>
      </form>
    </div>
  );
}
