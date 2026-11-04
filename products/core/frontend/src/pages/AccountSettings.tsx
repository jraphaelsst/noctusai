import React, { useState, useEffect } from 'react';
import { useAuth } from '../lib/auth-context';
import { api } from '../lib/api';
import { Link, useNavigate } from 'react-router-dom';

export function AccountSettings() {
  const { user, loading, unavailable, refresh, updateUser } = useAuth();
  const navigate = useNavigate();
  const [nome, setNome] = useState('');
  const [avatarUrl, setAvatarUrl] = useState('');
  const [telefone, setTelefone] = useState('');
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');

  useEffect(() => {
    if (user) {
      setNome(user.nome || '');
      setAvatarUrl(user.avatar_url || '');
      setTelefone(user.telefone || '');
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
      // Always sent: an empty string CLEARS the number server-side.
      body.telefone = telefone.trim();
      const saved = await api.patch('/api/auth/profile', body);
      // Cache write: the saved row (telefone already normalized to E.164 by the
      // server) goes straight into the auth context -- no refetch of /me.
      const row = saved?.data;
      if (row) {
        updateUser({ nome: row.nome, avatar_url: row.avatar_url, telefone: row.telefone ?? null });
        setTelefone(row.telefone || '');
      }
      setMessage('Perfil atualizado com sucesso!');
    } catch (err: any) {
      setMessage(err.message || 'Erro ao atualizar perfil');
    } finally {
      setSaving(false);
    }
  }

  if (unavailable && !user) {
    return (
      <div className="mx-auto max-w-xl px-4 py-10" role="alert">
        <p className="text-sm text-destructive">Não foi possível carregar sua conta agora.</p>
        <button onClick={() => void refresh()} className="mt-3 text-sm text-primary hover:underline">
          Tentar novamente
        </button>
      </div>
    );
  }

  if (loading || !user) {
    return (
      <div className="mx-auto max-w-xl px-4 py-10" data-testid="account-skeleton" aria-busy="true">
        <div className="mb-6 h-8 w-64 animate-pulse rounded bg-muted" />
        <div className="space-y-4">
          {[0, 1, 2, 3].map(i => <div key={i} className="h-10 w-full animate-pulse rounded bg-muted" />)}
        </div>
      </div>
    );
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

        <div>
          <label htmlFor="telefone" className="mb-1 block text-sm font-medium text-foreground">
            WhatsApp
          </label>
          <input
            id="telefone"
            type="tel"
            inputMode="tel"
            autoComplete="tel"
            value={telefone}
            onChange={e => setTelefone(e.target.value)}
            placeholder="+55 11 99999-9999"
            className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
          />
          <p className="mt-1 text-xs text-muted-foreground">
            Usado para receber relatórios e alertas dos agentes (ex.: Julia).
          </p>
        </div>

        {message && (
          <p className={`rounded-md px-3 py-2 text-sm ${
            message.includes('sucesso')
              ? 'bg-success-light text-success'
              : 'bg-danger-light text-destructive'
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

      <section className="mt-8 border-t border-border pt-6">
        <h2 className="text-base font-semibold text-foreground">Segurança</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Verificação em duas etapas com aplicativo autenticador.
        </p>
        <Link to="/security" className="mt-2 inline-block text-sm text-primary hover:underline">
          Gerenciar verificação em duas etapas &rarr;
        </Link>
      </section>
    </div>
  );
}
