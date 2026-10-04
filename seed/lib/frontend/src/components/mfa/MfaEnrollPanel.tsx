/**
 * `<MfaEnrollPanel/>` — manage the second verification step (authenticator app).
 *
 * Shows the registered devices, lets the admin add one (name → QR code or manual
 * key → confirm with a 6-digit code) and remove one. Talks to the seed `mfa`
 * router through the `api` client it is given (`/api/auth/mfa/*`).
 *
 * Usage:
 *   <MfaEnrollPanel api={api} onVerified={(r) => storeTokens(r)} />
 */
import * as React from 'react';
import { AlertCircle, Copy, Loader2, ShieldCheck, Trash2 } from 'lucide-react';

import { Badge } from '../../design-system/ui/Badge';
import { Button } from '../../design-system/ui/Button';
import { Input } from '../../design-system/ui/Input';
import { Skeleton } from '../../design-system/ui/Skeleton';
import { CodeInput } from './CodeInput';
import { isSixDigits, mfaErrorMessage } from './errors';
import { MFA_BASE } from './types';
import type { MfaEnrollResult, MfaStatus, MfaTransport, MfaVerifyResult } from './types';

export interface MfaEnrollPanelProps {
  api: MfaTransport;
  /** Called after a code was confirmed; hand `result` tokens (Bearer SPAs) to session storage. */
  onVerified?: (result: MfaVerifyResult) => void | Promise<void>;
  className?: string;
}

type Load = { phase: 'pending' } | { phase: 'error'; message: string } | { phase: 'ready'; data: MfaStatus };

export function MfaEnrollPanel({ api, onVerified, className }: MfaEnrollPanelProps) {
  const [load, setLoad] = React.useState<Load>({ phase: 'pending' });
  const [refreshing, setRefreshing] = React.useState(false);
  const [name, setName] = React.useState('');
  const [enrollment, setEnrollment] = React.useState<MfaEnrollResult | null>(null);
  const [code, setCode] = React.useState('');
  const [busy, setBusy] = React.useState(false);
  const [formError, setFormError] = React.useState<string | null>(null);
  const [copied, setCopied] = React.useState<'ok' | 'fail' | null>(null);
  const [confirmRemove, setConfirmRemove] = React.useState<string | null>(null);

  const refresh = React.useCallback(async () => {
    setRefreshing(true);
    try {
      const data = await api.get<MfaStatus>(`${MFA_BASE}/status`);
      setLoad({ phase: 'ready', data });
    } catch (err) {
      // Keep showing the last good data on a failed refresh.
      setLoad((prev) => (prev.phase === 'ready' ? prev : { phase: 'error', message: mfaErrorMessage(err) }));
    } finally {
      setRefreshing(false);
    }
  }, [api]);

  React.useEffect(() => {
    void refresh();
  }, [refresh]);

  const startEnroll = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setFormError(null);
    try {
      const result = await api.post<MfaEnrollResult>(`${MFA_BASE}/enroll`, {
        friendly_name: name.trim() || 'Meu celular',
      });
      setEnrollment(result);
      setCode('');
    } catch (err) {
      setFormError(mfaErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const confirmEnroll = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!enrollment || !isSixDigits(code)) return;
    setBusy(true);
    setFormError(null);
    try {
      const result = await api.post<MfaVerifyResult>(`${MFA_BASE}/verify`, {
        factor_id: enrollment.factor_id,
        code,
      });
      await onVerified?.(result);
      setEnrollment(null);
      setName('');
      setCode('');
      await refresh();
    } catch (err) {
      setFormError(mfaErrorMessage(err));
      setCode('');
    } finally {
      setBusy(false);
    }
  };

  const cancelEnroll = async () => {
    const pending = enrollment;
    setEnrollment(null);
    setFormError(null);
    setCode('');
    if (pending) {
      // Drop the half-made (unverified) factor so it does not count toward the limit.
      try {
        await api.delete(`${MFA_BASE}/factors/${pending.factor_id}`);
      } catch {
        /* shown as "pendente" in the list; the admin can remove it there */
      }
      await refresh();
    }
  };

  const removeFactor = async (id: string) => {
    setBusy(true);
    setFormError(null);
    try {
      await api.delete(`${MFA_BASE}/factors/${id}`);
      setConfirmRemove(null);
      await refresh();
    } catch (err) {
      setFormError(mfaErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const copyUri = async () => {
    if (!enrollment) return;
    try {
      await navigator.clipboard.writeText(enrollment.uri);
      setCopied('ok');
    } catch {
      setCopied('fail');
    }
  };

  const data = load.phase === 'ready' ? load.data : undefined;
  const showSkeleton = load.phase === 'pending' && !data;
  const isRefreshing = refreshing && !!data;

  return (
    <section className={className} aria-labelledby="mfa-panel-title" aria-busy={showSkeleton || isRefreshing}>
      <header className="mb-4 flex items-center gap-2">
        <ShieldCheck className="h-5 w-5 text-primary" aria-hidden />
        <h2 id="mfa-panel-title" className="text-base font-semibold text-foreground">
          Verificação em duas etapas
        </h2>
        {isRefreshing && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" aria-label="Atualizando" />}
      </header>

      {showSkeleton && (
        <div className="space-y-2" data-testid="mfa-skeleton">
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
        </div>
      )}

      {load.phase === 'error' && !data && (
        <div role="alert" className="flex items-start gap-2 rounded-md border border-destructive/40 p-3 text-sm text-destructive">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
          <div className="space-y-2">
            <p>{load.message}</p>
            <Button type="button" size="sm" variant="outline" onClick={() => void refresh()}>
              Tentar de novo
            </Button>
          </div>
        </div>
      )}

      {data && (
        <div className="space-y-4">
          <p className="text-sm text-muted-foreground">
            {data.enrolled
              ? 'Sua conta está protegida: além da senha, pedimos um código do aplicativo autenticador.'
              : 'Ainda não há nenhum dispositivo cadastrado. Cadastre um aplicativo autenticador (Google Authenticator, Microsoft Authenticator, Authy...) para proteger sua conta.'}
          </p>

          {data.factors.length === 0 ? (
            <p className="text-sm text-muted-foreground">Nenhum dispositivo cadastrado.</p>
          ) : (
            <ul className="divide-y divide-border rounded-md border border-border" aria-label="Dispositivos cadastrados">
              {data.factors.map((f) => (
                <li key={f.id} className="flex items-center justify-between gap-3 px-3 py-2">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-foreground">{f.friendly_name}</p>
                    <p className="text-xs text-muted-foreground">
                      Adicionado em {new Date(f.created_at).toLocaleDateString('pt-BR')}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge variant={f.status === 'verified' ? 'default' : 'muted'}>
                      {f.status === 'verified' ? 'Ativo' : 'Pendente'}
                    </Badge>
                    {confirmRemove === f.id ? (
                      <>
                        <Button type="button" size="sm" variant="destructive" disabled={busy} onClick={() => void removeFactor(f.id)}>
                          Confirmar remoção
                        </Button>
                        <Button type="button" size="sm" variant="ghost" disabled={busy} onClick={() => setConfirmRemove(null)}>
                          Cancelar
                        </Button>
                      </>
                    ) : (
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        aria-label={`Remover ${f.friendly_name}`}
                        onClick={() => setConfirmRemove(f.id)}
                      >
                        <Trash2 className="h-4 w-4" aria-hidden />
                      </Button>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}

          {data.factors.filter((f) => f.status === 'verified').length < 2 && !enrollment && (
            <form onSubmit={startEnroll} className="space-y-2">
              <label htmlFor="mfa-device-name" className="text-sm font-medium text-foreground">
                Nome do dispositivo
              </label>
              <div className="flex gap-2">
                <Input
                  id="mfa-device-name"
                  value={name}
                  maxLength={60}
                  placeholder="Ex.: Celular do trabalho"
                  disabled={busy}
                  onChange={(e) => setName(e.target.value)}
                />
                <Button type="submit" disabled={busy}>
                  {busy ? <Loader2 className="h-4 w-4 animate-spin" aria-label="Aguarde" /> : 'Adicionar dispositivo'}
                </Button>
              </div>
              <p className="text-xs text-muted-foreground">
                Recomendamos cadastrar DOIS dispositivos (por exemplo, dois celulares). Se você perder um,
                o outro permite entrar e recuperar o acesso sem depender de ninguém.
              </p>
            </form>
          )}

          {enrollment && (
            <form onSubmit={confirmEnroll} className="space-y-3 rounded-md border border-border p-4">
              <ol className="list-decimal space-y-1 pl-5 text-sm text-foreground">
                <li>Abra o aplicativo autenticador e escolha adicionar uma conta.</li>
                <li>Aponte a câmera para o código QR abaixo.</li>
                <li>Digite aqui o código de 6 números que o aplicativo mostrar.</li>
              </ol>
              <img src={enrollment.qr_code} alt="Código QR para o aplicativo autenticador" className="mx-auto h-44 w-44 rounded bg-white p-2" />
              <div className="space-y-1">
                <p className="text-xs text-muted-foreground">Não consegue ler o QR? Copie a chave e cole no aplicativo:</p>
                <div className="flex items-center gap-2">
                  <code className="min-w-0 flex-1 break-all rounded bg-muted px-2 py-1 text-xs" data-testid="mfa-uri">
                    {enrollment.uri}
                  </code>
                  <Button type="button" size="sm" variant="outline" onClick={() => void copyUri()}>
                    <Copy className="mr-1 h-3.5 w-3.5" aria-hidden />
                    Copiar
                  </Button>
                </div>
                <p role="status" className="text-xs text-muted-foreground">
                  {copied === 'ok' && 'Chave copiada.'}
                  {copied === 'fail' && 'Não foi possível copiar. Selecione o texto e copie manualmente.'}
                </p>
              </div>
              <div className="space-y-1">
                <label htmlFor="mfa-enroll-code" className="text-sm font-medium text-foreground">
                  Código de 6 números
                </label>
                <CodeInput
                  id="mfa-enroll-code"
                  value={code}
                  onChange={setCode}
                  disabled={busy}
                  invalid={!!formError}
                  describedBy={formError ? 'mfa-panel-error' : undefined}
                />
              </div>
              <div className="flex justify-end gap-2">
                <Button type="button" variant="ghost" disabled={busy} onClick={() => void cancelEnroll()}>
                  Cancelar
                </Button>
                <Button type="submit" disabled={busy || !isSixDigits(code)}>
                  {busy ? <Loader2 className="h-4 w-4 animate-spin" aria-label="Aguarde" /> : 'Confirmar'}
                </Button>
              </div>
            </form>
          )}

          {formError && (
            <p id="mfa-panel-error" role="alert" className="text-sm text-destructive">
              {formError}
            </p>
          )}
        </div>
      )}
    </section>
  );
}
