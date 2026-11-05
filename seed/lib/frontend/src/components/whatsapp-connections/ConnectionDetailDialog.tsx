/**
 * `<ConnectionDetailDialog/>` — per-connection manage modal: live status,
 * the shared `ConnectionPairingPanel` (QR, start/restart/logout, recovery ladder), and the
 * webhook URL (read-only + "reenviar configuração").
 *
 * QR panel lifted from social-wiring's `ConnectionDetailDialog.tsx:114-122`.
 */
import * as React from 'react';
import { Loader2 } from 'lucide-react';

import { Button } from '../../design-system/ui/Button';
import { Dialog, DialogBody, DialogFooter, DialogHeader } from '../../design-system/ui/Dialog';
import type { WhatsAppConnectionLine, WhatsAppConnectionsHooks } from '../../whatsapp';
import { ConnectionPairingPanel } from './ConnectionPairingPanel';
import { PurgeConnectionDialog } from './PurgeConnectionDialog';

export interface ConnectionDetailDialogProps {
  open: boolean;
  onClose: () => void;
  line: WhatsAppConnectionLine;
  hooks: WhatsAppConnectionsHooks;
}

export function ConnectionDetailDialog({ open, onClose, line, hooks }: ConnectionDetailDialogProps) {
  const configureWebhook = hooks.useConfigureConnectionWebhook();

  const [purgeOpen, setPurgeOpen] = React.useState(false);

  // A borrowed session belongs to another app: its owner pairs / restarts / re-registers it, never this app.
  const borrowed = line.session_role === 'borrower';

  return (
    <>
    <Dialog open={open} onClose={onClose} title={line.label} className="max-w-lg">
      <DialogHeader>
        <div>
          <h3 className="text-sm font-semibold">{line.label}</h3>
        </div>
      </DialogHeader>
      <DialogBody className="grid gap-4">
        <ConnectionPairingPanel connectionId={line.id} hooks={hooks} borrowed={borrowed} enabled={open} />

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
              disabled={borrowed || configureWebhook.isPending}
              onClick={() =>
                configureWebhook.mutate({ id: line.id, body: { url: line.webhook_url! } })
              }
            >
              {configureWebhook.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : 'Reenviar configuração'}
            </Button>
          )}
        </div>

        {line.app_enabled === false && (
          <div className="grid gap-1 border-t pt-3">
            <span className="text-xs font-medium text-muted-foreground">Fase de testes</span>
            <Button type="button" variant="destructive" size="sm" className="w-fit" onClick={() => setPurgeOpen(true)}>
              Apagar dados de teste
            </Button>
          </div>
        )}
      </DialogBody>
      <DialogFooter>
        <Button type="button" variant="outline" onClick={onClose}>
          Fechar
        </Button>
      </DialogFooter>
    </Dialog>
    <PurgeConnectionDialog open={purgeOpen} onClose={() => setPurgeOpen(false)} line={line} hooks={hooks} />
    </>
  );
}
