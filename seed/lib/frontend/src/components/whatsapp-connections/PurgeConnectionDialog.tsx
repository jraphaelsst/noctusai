/**
 * `<PurgeConnectionDialog/>` — testing-phase erasure of one line's conversation data.
 *
 * Irreversible, so the admin types the connection label back before the button arms (the same guard as
 * deleting a repository). The server enforces the rest: the app must be OFF for the line, and the label must
 * match. Counts of what was erased are shown after it ran.
 */
import * as React from 'react';
import { Loader2 } from 'lucide-react';

import { Button } from '../../design-system/ui/Button';
import { Dialog, DialogBody, DialogFooter, DialogHeader } from '../../design-system/ui/Dialog';
import { Input } from '../../design-system/ui/Input';
import { ApiError } from '../../api';
import type { WhatsAppConnectionLine, WhatsAppConnectionsHooks } from '../../whatsapp';

export interface PurgeConnectionDialogProps {
  open: boolean;
  onClose: () => void;
  line: WhatsAppConnectionLine;
  hooks: WhatsAppConnectionsHooks;
}

export function PurgeConnectionDialog({ open, onClose, line, hooks }: PurgeConnectionDialogProps) {
  const purge = hooks.usePurgeConnection();
  const [typed, setTyped] = React.useState('');

  React.useEffect(() => {
    if (!open) {
      setTyped('');
      purge.reset();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const armed = typed.trim() === line.label && line.app_enabled === false;
  const done = purge.data;

  return (
    <Dialog open={open} onClose={onClose} title="Apagar dados de teste">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (armed) purge.mutate({ id: line.id, confirm: typed.trim() });
        }}
      >
        <DialogHeader>
          <h3 className="text-sm font-semibold">Apagar dados de teste</h3>
        </DialogHeader>
        <DialogBody className="grid gap-3">
          {done ? (
            <p className="text-sm" data-testid="wa-purge-done">
              Pronto: {done.chats_deleted} conversas e {done.messages_deleted} mensagens apagadas
              {typeof done.extra.leads_deleted === 'number' ? `, ${done.extra.leads_deleted} leads removidos` : ''}
              {done.extra.leads_detached ? ` e ${done.extra.leads_detached} leads mantidos sem vínculo com a conversa` : ''}.
            </p>
          ) : (
            <>
              <p className="text-sm text-muted-foreground">
                Isto apaga, de forma definitiva, todas as conversas e mensagens desta conexão neste app, e os leads
                criados automaticamente que ninguém editou. Leads que alguém editou são mantidos, sem o vínculo com a
                conversa. A conexão em si continua existindo.
              </p>
              <div className="grid gap-1.5">
                <label htmlFor="wa-purge-confirm" className="text-xs font-medium text-muted-foreground">
                  Digite <strong>{line.label}</strong> para confirmar
                </label>
                <Input
                  id="wa-purge-confirm"
                  value={typed}
                  onChange={(e) => setTyped(e.target.value)}
                  disabled={purge.isPending}
                  autoComplete="off"
                />
              </div>
              {purge.isError && (
                <p role="alert" className="text-xs text-destructive" data-testid="wa-purge-error">
                  {purge.error instanceof ApiError && purge.error.status === 409
                    ? 'Desligue o app para esta conexão antes de apagar os dados.'
                    : purge.error instanceof Error
                      ? purge.error.message
                      : 'Falha ao apagar os dados.'}
                </p>
              )}
            </>
          )}
        </DialogBody>
        <DialogFooter className="gap-2">
          <Button type="button" variant="outline" onClick={onClose} disabled={purge.isPending}>
            {done ? 'Fechar' : 'Cancelar'}
          </Button>
          {!done && (
            <Button type="submit" variant="destructive" disabled={!armed || purge.isPending}>
              {purge.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : 'Apagar dados'}
            </Button>
          )}
        </DialogFooter>
      </form>
    </Dialog>
  );
}
