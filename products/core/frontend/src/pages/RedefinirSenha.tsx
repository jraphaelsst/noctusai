/**
 * Core "set a new password" -- the landing of the recovery email
 * (`CORE_URL/redefinir-senha?produto=&next=#access_token=..&refresh_token=..&type=recovery`).
 * After the reset the user signs in with the new password through core's normal login (so a
 * second factor is never skipped) and continues into the product they came from.
 */
import React, { useMemo, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { api, setRefreshToken, setToken } from '../lib/api';
import { useAuth } from '../lib/auth-context';
import { createRecoveryClient } from '../lib/recovery-supabase';
import { entryQuery, launchProduct, readSsoEntry } from '../lib/sso-entry';

const MIN_LEN = 8; // mirrors POST /api/auth/change-password

interface RecoveryTokens { access: string; refresh: string }

function readRecoveryTokens(): RecoveryTokens | null {
  const h = new URLSearchParams(window.location.hash.replace(/^#/, ''));
  const access = h.get('access_token');
  const refresh = h.get('refresh_token');
  if (h.get('type') !== 'recovery' || !access || !refresh) return null;
  return { access, refresh };
}

export function RedefinirSenha() {
  const [params] = useSearchParams();
  const entry = useMemo(() => readSsoEntry(params), [params]);
  const query = entryQuery(entry);
  const navigate = useNavigate();
  const { refresh } = useAuth();
  // Read once and take the tokens out of the address bar / history right away.
  const [tokens] = useState<RecoveryTokens | null>(() => {
    const t = readRecoveryTokens();
    if (t) window.history.replaceState(null, '', window.location.pathname + window.location.search);
    return t;
  });
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [errors, setErrors] = useState<{ password?: string; confirm?: string }>({});
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  if (!tokens) {
    return (
      <Shell>
        <div role="alert" className="space-y-4 text-sm text-foreground">
          <p className="font-semibold">Link inválido ou expirado</p>
          <p className="text-muted-foreground">
            O link de redefinição só funciona uma vez e por pouco tempo. Peça um novo para continuar.
          </p>
          <Link to={`/esqueci-senha${query}`} className="inline-block text-primary underline">
            Pedir novo link
          </Link>
        </div>
      </Shell>
    );
  }

  function validate() {
    const next: typeof errors = {};
    if (password.length < MIN_LEN) next.password = `A senha precisa ter ao menos ${MIN_LEN} caracteres.`;
    if (confirm !== password) next.confirm = 'As senhas não são iguais.';
    setErrors(next);
    return Object.keys(next).length === 0;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    if (!validate()) return;
    setBusy(true);
    let email = '';
    try {
      const supabase = createRecoveryClient();
      const set = await supabase.auth.setSession({ access_token: tokens!.access, refresh_token: tokens!.refresh });
      if (set.error) {
        setError('Este link expirou. Peça um novo link para redefinir a senha.');
        return;
      }
      const upd = await supabase.auth.updateUser({ password });
      if (upd.error) {
        const code = (upd.error as { code?: string }).code;
        if (code === 'same_password') setErrors({ password: 'A nova senha precisa ser diferente da atual.' });
        else if (code === 'weak_password') setErrors({ password: 'Senha fraca demais. Use letras, números e símbolos.' });
        else setError('Não foi possível salvar a nova senha. Tente novamente ou peça um novo link.');
        return;
      }
      email = upd.data.user?.email ?? '';
    } catch {
      setError('Não foi possível salvar a nova senha. Verifique sua conexão e tente novamente.');
      return;
    } finally {
      setBusy(false);
    }

    // Password changed. Sign in through core's own login (MFA-aware), then continue.
    try {
      const res = await api.post('/api/auth/login', { email, password });
      if (res.mfa_required) {
        navigate(`/login${query}`, { replace: true });
        return;
      }
      setToken(res.access_token);
      if (res.refresh_token) setRefreshToken(res.refresh_token);
      await refresh();
      if (entry) {
        await launchProduct(entry);
      } else {
        navigate('/', { replace: true });
      }
    } catch (err: any) {
      // The password IS changed: say so, and never leave the visitor guessing.
      setError(
        entry
          ? `Senha alterada, mas não foi possível abrir o produto: ${err?.message ?? 'erro desconhecido'}. Entre novamente.`
          : 'Senha alterada, mas não foi possível entrar automaticamente. Entre com a nova senha.',
      );
    }
  }

  return (
    <Shell>
      <form onSubmit={handleSubmit} noValidate className="space-y-4">
        <p className="text-sm text-muted-foreground">Escolha a nova senha da sua conta NoctusAI.</p>
        <Field id="redefinir-senha" label="Nova senha" value={password} onChange={setPassword} error={errors.password} />
        <Field id="redefinir-confirmar" label="Confirmar nova senha" value={confirm} onChange={setConfirm} error={errors.confirm} />
        {error && (
          <div role="alert" className="rounded-md bg-danger-light px-3 py-2 text-sm text-danger-foreground">
            {error}{' '}
            <Link to={`/login${query}`} className="underline">Ir para o login</Link>
          </div>
        )}
        <button
          type="submit"
          disabled={busy}
          className="w-full h-10 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {busy ? 'Salvando…' : 'Salvar nova senha'}
        </button>
      </form>
    </Shell>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-background flex flex-col items-center justify-center p-4">
      <div className="w-full max-w-md bg-card rounded-lg border border-border shadow-md p-8 space-y-4">
        <h1 className="text-xl font-bold text-foreground">Redefinir senha</h1>
        {children}
      </div>
    </div>
  );
}

function Field({ id, label, value, onChange, error }: {
  id: string; label: string; value: string; onChange: (v: string) => void; error?: string;
}) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="text-sm font-medium text-foreground">{label}</label>
      <input
        id={id}
        type="password"
        autoComplete="new-password"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        aria-invalid={!!error}
        aria-describedby={error ? `${id}-erro` : undefined}
        className="w-full h-10 rounded-md border border-input bg-background px-3 text-sm text-foreground focus:outline-hidden focus:ring-2 focus:ring-primary/20 focus:border-primary"
      />
      {error && <p id={`${id}-erro`} className="text-sm text-danger-foreground">{error}</p>}
    </div>
  );
}
