/**
 * `<ConnectionDetailDialog/>` — per-connection manage modal: live status,
 * QR pairing panel, start/restart/logout, the recovery ladder, and the
 * webhook URL (read-only + "reenviar configuração").
 *
 * QR panel lifted from social-wiring's `ConnectionDetailDialog.tsx:114-122`.
 */
import * as React from 'react';
import { CheckCircle2, CircleAlert, Loader2, RefreshCw } from 'lucide-react';

import { Badge } from '../../design-system/ui/Badge';
import { Button } from '../../design-system/ui/Button';
import { Dialog, DialogBody, DialogFooter, DialogHeader } from '../../design-system/ui/Dialog';
import type { WhatsAppConnectionLine, WhatsAppConnectionsHooks } from '../../whatsapp';

function StatusBadge({ status, paired }: { status: string | null | undefined; paired: boolean | undefined }) {
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

/**
 * QR panel — polls while the dialog is open and the line is not yet
 * paired; shows the scannable image or a "gerando/aguardando" placeholder.
 */
function QrPanel({ hooks, connectionId, enabled }: { hooks: WhatsAppConnectionsHooks; connectionId: string; enabled: boolean }) {
  const { data: qr } = hooks.useConnectionQr(connectionId, enabled);
  return (
    <div
      className="flex flex-col items-center gap-2 rounded-md border bg-muted/10 p-4"
      data-testid="wa-qr-panel"
    >
      {qr?.scannable && qr.png_base64 ? (
        <>
          <img
            src={`data:image/png;base64,${qr.png_base64}`}
            alt="QR code para parear o WhatsApp"
            className="h-52 w-52 rounded-md border bg-white p-2"
            data-testid="wa-qr-image"
          />
          <p className="text-center text-xs text-muted-foreground">
            WhatsApp → Aparelhos conectados → Conectar aparelho. Atualiza sozinho.
          </p>
        </>
      ) : (
        <div
          className="flex h-52 w-52 flex-col items-center justify-center gap-2 text-sm text-muted-foreground"
          data-testid="wa-qr-loading"
        >
          <Loader2 className="h-5 w-5 animate-spin" />
          {qr?.status ? `Aguardando QR (${qr.status})` : 'Gerando QR...'}
        </div>
      )}
    </div>
  );
}

export interface ConnectionDetailDialogProps {
  open: boolean;
  onClose: () => void;
  line: WhatsAppConnectionLine;
  hooks: WhatsAppConnectionsHooks;
}

export function ConnectionDetailDialog({ open, onClose, line, hooks }: ConnectionDetailDialogProps) {
  const { data: status } = hooks.useConnectionStatus(line.id, open);
  const actions = hooks.useConnectionActions();
  const recover = hooks.useRecoverConnection();
  const configureWebhook = hooks.useConfigureConnectionWebhook();

  const paired = !!status?.paired;
  const anyActionPending =
    actions.start.isPending || actions.restart.isPending || actions.logout.isPending || recover.isPending;

  return (
    <Dialog open={open} onClose={onClose} title={line.label} className="max-w-lg">
      <DialogHeader>
        <div>
          <h3 className="text-sm font-semibold">{line.label}</h3>
          <div className="mt-1">
            <StatusBadge status={status?.status} paired={status?.paired} />
          </div>
        </div>
      </DialogHeader>
      <DialogBody className="grid gap-4">
        {!paired && <QrPanel hooks={hooks} connectionId={line.id} enabled={open} />}

        {status?.error && (
          <p role="alert" className="text-xs text-destructive" data-testid="wa-status-error">
            {status.error}
          </p>
        )}

        <div className="grid gap-1">
          <span className="text-xs font-medium text-muted-foreground">Webhook</span>
          <code className="break-all rounded-md border bg-muted/30 px-2.5 py-1.5 text-xs" data-testid="wa-webhook-url">
            {line.webhook_url ?? '—'}
          </code>
          {line.webhook_url && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="w-fit"
              disabled={configureWebhook.isPending}
              onClick={() =>
                configureWebhook.mutate({ id: line.id, body: { url: line.webhook_url! } })
              }
            >
              {configureWebhook.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : 'Reenviar configuração'}
            </Button>
          )}
        </div>

        <div className="flex flex-wrap gap-2">
          <Button type="button" variant="outline" size="sm" disabled={anyActionPending} onClick={() => actions.start.mutate(line.id)}>
            {actions.start.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : 'Iniciar'}
          </Button>
          <Button type="button" variant="outline" size="sm" disabled={anyActionPending} onClick={() => actions.restart.mutate(line.id)}>
            {actions.restart.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : 'Reiniciar'}
          </Button>
          <Button type="button" variant="outline" size="sm" disabled={anyActionPending} onClick={() => actions.logout.mutate(line.id)}>
            {actions.logout.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : 'Desconectar'}
          </Button>
          <Button
            type="button"
            variant="primary"
            size="sm"
            disabled={anyActionPending}
            onClick={() => recover.mutate(line.id)}
          >
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
      </DialogBody>
      <DialogFooter>
        <Button type="button" variant="outline" onClick={onClose}>
          Fechar
        </Button>
      </DialogFooter>
    </Dialog>
  );
}
