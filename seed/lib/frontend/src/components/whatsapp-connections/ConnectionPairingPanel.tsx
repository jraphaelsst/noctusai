/**
 * `<ConnectionPairingPanel/>` — the pairing half of a WhatsApp line: live status, the QR (polled until the
 * line is WORKING), and the start / restart / logout / recover actions. Extracted from
 * `ConnectionDetailDialog` so the dialog and any product card (e.g. social-wiring's Julia line) share ONE
 * implementation. Driven by `createWhatsAppConnectionsHooks(api)`.
 *
 * Server-state contract: no data yet -> skeleton (never a fake "loading" over nothing); read refused with no
 * data -> alert + retry; a refused action -> alert (never silent). Logout always asks first, with the
 * product-supplied consequence text (`onLogoutConfirmText`), because logout drops the whole line.
 * Needs a `<ConfirmProvider/>` ancestor.
 */
import * as React from 'react';
import { CheckCircle2, CircleAlert, Loader2, RefreshCw } from 'lucide-react';

import { Badge } from '../../design-system/ui/Badge';
import { Button } from '../../design-system/ui/Button';
import { Skeleton } from '../../design-system/ui/Skeleton';
import type { WhatsAppConnectionsHooks } from '../../whatsapp';
import { useConfirm } from '../confirm';

export function ConnectionStatusBadge({ status, paired }: { status: string | null | undefined; paired: boolean | undefined }) {
  if (paired) {
    return (
      <Badge variant="default" className="gap-1">
        <CheckCircle2 className="h-3 w-3" />
        {status ?? 'WORKING'}
      </Badge>
    );
  }
  return (
    <Badge variant="muted" className="gap-1">
      <CircleAlert className="h-3 w-3" />
      {status ?? 'desconectado'}
    </Badge>
  );
}

const DEFAULT_LOGOUT_TEXT = 'A linha será desconectada do WhatsApp e precisará ser pareada de novo com um QR.';

export interface ConnectionPairingPanelProps {
  /** The line to pair. `null`/`undefined` = no line yet: the empty state (with `emptyAction`) is drawn. */
  connectionId: string | null | undefined;
  hooks: WhatsAppConnectionsHooks;
  /** Admin-only controls (QR + start/restart/logout/recover). `false` = read-only status. Default `true`. */
  canManage?: boolean;
  /** Consequence shown in the logout confirm dialog (what stops when this line is disconnected). */
  onLogoutConfirmText?: React.ReactNode;
  /** A borrowed session belongs to another app: its owner pairs it, never this app. Controls render disabled. */
  borrowed?: boolean;
  /** Pause every poll (e.g. a closed dialog). Default `true`. */
  enabled?: boolean;
  /** Slot in the empty state (e.g. a "Criar linha" button). */
  emptyAction?: React.ReactNode;
}

function errMsg(e: unknown): string {
  return e instanceof Error && e.message ? e.message : 'Não foi possível concluir a ação.';
}

export function ConnectionPairingPanel({
  connectionId,
  hooks,
  canManage = true,
  onLogoutConfirmText,
  borrowed = false,
  enabled = true,
  emptyAction,
}: ConnectionPairingPanelProps) {
  const confirm = useConfirm();
  const status = hooks.useConnectionStatus(connectionId ?? null, enabled);
  const actions = hooks.useConnectionActions();
  const recover = hooks.useRecoverConnection();

  const paired = !!status.data?.paired;
  const showQr = canManage && !borrowed && !paired && !!connectionId;
  // Called unconditionally; `enabled` stops its polling once paired / hidden.
  const qr = hooks.useConnectionQr(connectionId ?? null, enabled && showQr);

  if (!connectionId) {
    return (
      <div
        className="flex flex-col items-center gap-2 rounded-md border border-dashed p-4 text-sm text-muted-foreground"
        data-testid="wa-pairing-empty"
      >
        <p>Nenhuma linha de WhatsApp conectada.</p>
        {emptyAction}
      </div>
    );
  }

  const busy =
    borrowed ||
    actions.start.isPending || actions.restart.isPending || actions.logout.isPending || recover.isPending;
  const actionError = actions.start.error ?? actions.restart.error ?? actions.logout.error ?? recover.error;

  const onLogout = async () => {
    const ok = await confirm({
      title: 'Desconectar o WhatsApp?',
      description: onLogoutConfirmText ?? DEFAULT_LOGOUT_TEXT,
      confirmLabel: 'Desconectar',
      tone: 'danger',
    });
    if (ok) actions.logout.mutate(connectionId);
  };

  if (!status.data && status.isError) {
    return (
      <div role="alert" className="grid gap-2 text-sm text-destructive" data-testid="wa-pairing-error">
        <p>Não foi possível ler o estado da linha.</p>
        <Button type="button" variant="outline" size="sm" className="w-fit" onClick={() => void status.refetch()}>
          Tentar de novo
        </Button>
      </div>
    );
  }

  if (!status.data) {
    return <Skeleton className="h-40 w-full" data-testid="wa-pairing-loading" />;
  }

  return (
    <div className="grid gap-4" data-testid="wa-pairing-panel">
      <div>
        <ConnectionStatusBadge status={status.data.status} paired={status.data.paired} />
      </div>

      {showQr && (
        <div className="flex flex-col items-center gap-2 rounded-md border bg-muted/10 p-4" data-testid="wa-qr-panel">
          {qr.data?.scannable && qr.data.png_base64 ? (
            <>
              <img
                src={`data:image/png;base64,${qr.data.png_base64}`}
                alt="QR code para parear o WhatsApp"
                className="h-52 w-52 rounded-md border bg-white p-2"
                data-testid="wa-qr-image"
              />
              <p className="text-center text-xs text-muted-foreground">
                WhatsApp → Aparelhos conectados → Conectar aparelho. Atualiza sozinho.
              </p>
            </>
          ) : qr.isError && !qr.data ? (
            <p role="alert" className="text-sm text-destructive" data-testid="wa-qr-error">
              Não foi possível obter o QR. Tentando de novo...
            </p>
          ) : (
            <div
              className="flex h-52 w-52 flex-col items-center justify-center gap-2 text-sm text-muted-foreground"
              data-testid="wa-qr-loading"
            >
              <Loader2 className="h-5 w-5 animate-spin" />
              {qr.data?.status ? `Aguardando QR (${qr.data.status})` : 'Gerando QR...'}
            </div>
          )}
        </div>
      )}

      {borrowed && (
        <p className="rounded-md border bg-muted/30 p-2 text-xs text-muted-foreground" data-testid="wa-borrowed-note">
          Esta conexão usa a sessão de WhatsApp de outro app. Parear, reiniciar e desconectar são feitos por quem é
          dono da sessão; aqui você só liga ou desliga este app.
        </p>
      )}

      {status.data.error && (
        <p role="alert" className="text-xs text-destructive" data-testid="wa-status-error">
          {status.data.error}
        </p>
      )}

      {actionError && (
        <p role="alert" className="text-xs text-destructive" data-testid="wa-action-error">
          {errMsg(actionError)}
        </p>
      )}

      {(canManage || borrowed) && (
        <div className="flex flex-wrap gap-2" data-testid="wa-pairing-actions">
          <Button type="button" variant="outline" size="sm" disabled={busy} onClick={() => actions.start.mutate(connectionId)}>
            {actions.start.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : 'Iniciar'}
          </Button>
          <Button type="button" variant="outline" size="sm" disabled={busy} onClick={() => actions.restart.mutate(connectionId)}>
            {actions.restart.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : 'Reiniciar'}
          </Button>
          <Button type="button" variant="outline" size="sm" disabled={busy} onClick={() => void onLogout()}>
            {actions.logout.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : 'Desconectar'}
          </Button>
          <Button type="button" variant="primary" size="sm" disabled={busy} onClick={() => recover.mutate(connectionId)}>
            {recover.isPending ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <>
                <RefreshCw className="mr-1 h-3.5 w-3.5" />
                Recuperar conexão
              </>
            )}
          </Button>
        </div>
      )}
    </div>
  );
}
