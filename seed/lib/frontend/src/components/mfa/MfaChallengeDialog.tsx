/**
 * `<MfaChallengeDialog/>` — asks an admin for the 6-digit code of their
 * authenticator app. Raised by the api client on `403 mfa_required` (through
 * `<MfaChallengeHost/>`), or usable directly.
 *
 * - `enrolled === false`: explains that enrolment is required and embeds the
 *   `MfaEnrollPanel`.
 * - otherwise: loads the verified factors and asks for the code.
 */
import * as React from 'react';
import { Loader2, ShieldCheck } from 'lucide-react';

import { Button } from '../../design-system/ui/Button';
import { Dialog, DialogBody, DialogFooter, DialogHeader } from '../../design-system/ui/Dialog';
import { Skeleton } from '../../design-system/ui/Skeleton';
import { CodeInput } from './CodeInput';
import { isSixDigits, mfaErrorMessage } from './errors';
import { MfaEnrollPanel } from './MfaEnrollPanel';
import { MFA_BASE } from './types';
import type { MfaFactor, MfaStatus, MfaTransport, MfaVerifyResult } from './types';

export interface MfaChallengeDialogProps {
  open: boolean;
  /** From the 403 body. `false` ⇒ the admin has no device yet. */
  enrolled: boolean | null;
  api: MfaTransport;
  /** Code accepted (tokens, if any, in `result`). The dialog does not close itself. */
  onVerified: (result: MfaVerifyResult) => void | Promise<void>;
  onCancel: () => void;
}

type Factors = { phase: 'pending' } | { phase: 'error'; message: string } | { phase: 'ready'; data: MfaStatus };

const FOCUSABLE = 'button:not([disabled]), input:not([disabled]), select:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])';

export function MfaChallengeDialog({ open, enrolled, api, onVerified, onCancel }: MfaChallengeDialogProps) {
  const [factors, setFactors] = React.useState<Factors>({ phase: 'pending' });
  const [factorId, setFactorId] = React.useState('');
  const [code, setCode] = React.useState('');
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [showEnroll, setShowEnroll] = React.useState(false);
  const panelRef = React.useRef<HTMLDivElement>(null);

  const needsEnroll = enrolled === false || showEnroll;

  const loadFactors = React.useCallback(async () => {
    try {
      const data = await api.get<MfaStatus>(`${MFA_BASE}/status`);
      setFactors({ phase: 'ready', data });
      const verified = data.factors.filter((f) => f.status === 'verified');
      setFactorId((cur) => (verified.some((f) => f.id === cur) ? cur : verified[0]?.id ?? ''));
      if (verified.length === 0) setShowEnroll(true);
    } catch (err) {
      setFactors({ phase: 'error', message: mfaErrorMessage(err) });
    }
  }, [api]);

  React.useEffect(() => {
    if (!open || enrolled === false) return;
    setFactors({ phase: 'pending' });
    setCode('');
    setError(null);
    void loadFactors();
  }, [open, enrolled, loadFactors]);

  // Focus trap: Tab/Shift+Tab cycle inside the panel; focus the first control on open.
  React.useEffect(() => {
    if (!open) return;
    const root = panelRef.current;
    if (!root) return;
    const list = () => Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE));
    if (!root.contains(document.activeElement)) list()[0]?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Tab') return;
      const items = list();
      if (items.length === 0) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  });

  if (!open) return null;

  const data = factors.phase === 'ready' ? factors.data : undefined;
  const showSkeleton = factors.phase === 'pending' && !data;
  const verified: MfaFactor[] = data?.factors.filter((f) => f.status === 'verified') ?? [];

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!factorId || !isSixDigits(code)) return;
    setBusy(true);
    setError(null);
    try {
      const result = await api.post<MfaVerifyResult>(`${MFA_BASE}/verify`, { factor_id: factorId, code });
      await onVerified(result);
    } catch (err) {
      setError(mfaErrorMessage(err));
      setCode('');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onClose={onCancel} title="Confirme que é você" className="max-w-lg">
      <div ref={panelRef}>
        <DialogHeader>
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-5 w-5 text-primary" aria-hidden />
            <h2 className="text-base font-semibold text-foreground">Confirme que é você</h2>
          </div>
        </DialogHeader>

        {needsEnroll ? (
          <>
            <DialogBody className="space-y-4">
              <p className="text-sm text-foreground" data-testid="mfa-enroll-required">
                Esta ação exige a verificação em duas etapas, e sua conta ainda não tem um dispositivo cadastrado.
                Cadastre um aplicativo autenticador agora; leva cerca de um minuto.
              </p>
              <MfaEnrollPanel
                api={api}
                onVerified={async (result) => {
                  await onVerified(result);
                }}
              />
            </DialogBody>
            <DialogFooter>
              <Button type="button" variant="ghost" onClick={onCancel}>
                Cancelar
              </Button>
            </DialogFooter>
          </>
        ) : (
          <form onSubmit={submit}>
            <DialogBody className="space-y-4">
              {showSkeleton && (
                <div className="space-y-2" data-testid="mfa-challenge-skeleton">
                  <Skeleton className="h-4 w-2/3" />
                  <Skeleton className="h-10 w-full" />
                </div>
              )}
              {factors.phase === 'error' && !data && (
                <div role="alert" className="space-y-2 text-sm text-destructive">
                  <p>{factors.message}</p>
                  <Button type="button" size="sm" variant="outline" onClick={() => void loadFactors()}>
                    Tentar de novo
                  </Button>
                </div>
              )}
              {data && (
                <>
                  <p className="text-sm text-foreground">
                    Para continuar, digite o código de 6 números que aparece no seu aplicativo autenticador.
                  </p>
                  {verified.length > 1 && (
                    <div className="space-y-1">
                      <label htmlFor="mfa-factor" className="text-sm font-medium text-foreground">
                        Dispositivo
                      </label>
                      <select
                        id="mfa-factor"
                        className="h-9 w-full rounded-md border border-input bg-background px-2.5 text-sm"
                        value={factorId}
                        disabled={busy}
                        onChange={(e) => setFactorId(e.target.value)}
                      >
                        {verified.map((f) => (
                          <option key={f.id} value={f.id}>
                            {f.friendly_name}
                          </option>
                        ))}
                      </select>
                    </div>
                  )}
                  <div className="space-y-1">
                    <label htmlFor="mfa-code" className="text-sm font-medium text-foreground">
                      Código de 6 números
                    </label>
                    <CodeInput
                      id="mfa-code"
                      value={code}
                      onChange={setCode}
                      disabled={busy}
                      invalid={!!error}
                      describedBy={error ? 'mfa-challenge-error' : undefined}
                      autoFocus
                    />
                  </div>
                  {error && (
                    <p id="mfa-challenge-error" role="alert" className="text-sm text-destructive">
                      {error}
                    </p>
                  )}
                </>
              )}
            </DialogBody>
            <DialogFooter className="gap-2">
              <Button type="button" variant="ghost" disabled={busy} onClick={onCancel}>
                Cancelar
              </Button>
              <Button type="submit" disabled={busy || !data || !factorId || !isSixDigits(code)}>
                {busy ? <Loader2 className="h-4 w-4 animate-spin" aria-label="Verificando" /> : 'Confirmar'}
              </Button>
            </DialogFooter>
          </form>
        )}
      </div>
    </Dialog>
  );
}
