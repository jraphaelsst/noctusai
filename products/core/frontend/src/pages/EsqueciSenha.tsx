/**
 * Core "forgot password" (contract: products/core/CONTRACTS/sso-entry.md). The only place that
 * asks for credentials-recovery; products link here (`?produto=&next=`) so the reset can end
 * inside the product the user came from.
 */
import React, { useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useCountdown } from '../hooks/useCountdown';
import { entryQuery, readSsoEntry } from '../lib/sso-entry';
import {
  createRecoveryClient,
  EMAIL_RATE_LIMIT_SECONDS,
  isEmailRateLimit,
  recoveryRedirectTo,
} from '../lib/recovery-supabase';

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function EsqueciSenha() {
  const [params] = useSearchParams();
  const entry = useMemo(() => readSsoEntry(params), [params]);
  const query = entryQuery(entry);
  const [email, setEmail] = useState('');
  const [fieldError, setFieldError] = useState('');
  const [error, setError] = useState('');
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);
  const { secondsLeft, start } = useCountdown();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    if (!EMAIL_RE.test(email.trim())) {
      setFieldError('Informe um email válido, como voce@empresa.com.');
      return;
    }
    setFieldError('');
    setSending(true);
    try {
      const { error: err } = await createRecoveryClient().auth.resetPasswordForEmail(email.trim(), {
        redirectTo: recoveryRedirectTo(query),
      });
      if (err) {
        if (isEmailRateLimit(err)) {
          start(EMAIL_RATE_LIMIT_SECONDS);
          setError('Já enviamos um link há pouco. Aguarde para pedir outro.');
        } else {
          setError('Não foi possível enviar o email agora. Verifique sua conexão e tente novamente.');
        }
        return;
      }
      setSent(true);
    } catch {
      setError('Não foi possível enviar o email agora. Verifique sua conexão e tente novamente.');
    } finally {
      setSending(false);
    }
  }

  const blocked = secondsLeft > 0;

  return (
    <div className="min-h-screen bg-background flex flex-col items-center justify-center p-4">
      <div className="w-full max-w-md bg-card rounded-lg border border-border shadow-md p-8">
        <h1 className="text-xl font-bold text-foreground mb-1">Esqueci minha senha</h1>
        {sent ? (
          <div role="status" className="space-y-4 text-sm text-foreground">
            <p>
              Se <strong>{email.trim()}</strong> tiver uma conta, enviamos um link para criar uma nova senha.
              Confira também a caixa de spam.
            </p>
            <button
              type="button"
              className="text-primary underline disabled:opacity-50 disabled:no-underline"
              disabled={blocked}
              onClick={() => setSent(false)}
            >
              Usar outro email
            </button>
          </div>
        ) : (
          <form onSubmit={handleSubmit} noValidate className="space-y-4">
            <p className="text-sm text-muted-foreground">
              Informe o email da sua conta NoctusAI e enviaremos um link para criar uma nova senha.
            </p>
            <div className="space-y-1.5">
              <label htmlFor="esqueci-email" className="text-sm font-medium text-foreground">Email</label>
              <input
                id="esqueci-email"
                type="email"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                aria-invalid={!!fieldError}
                aria-describedby={fieldError ? 'esqueci-email-erro' : undefined}
                className="w-full h-10 rounded-md border border-input bg-background px-3 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary"
              />
              {fieldError && (
                <p id="esqueci-email-erro" className="text-sm text-danger-foreground">{fieldError}</p>
              )}
            </div>
            {error && (
              <div role="alert" className="rounded-md bg-danger-light px-3 py-2 text-sm text-danger-foreground">
                {error}
                {blocked && <span> Tente de novo em {secondsLeft}s.</span>}
              </div>
            )}
            <button
              type="submit"
              disabled={sending || blocked}
              className="w-full h-10 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {sending ? 'Enviando…' : blocked ? `Aguarde ${secondsLeft}s` : 'Enviar link'}
            </button>
          </form>
        )}
        <Link to={`/login${query}`} className="mt-6 block text-center text-sm text-primary hover:text-primary/80">
          Voltar ao login
        </Link>
      </div>
    </div>
  );
}
