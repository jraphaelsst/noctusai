/**
 * `<CreateConnectionDialog/>` — label + WAHA API key form.
 *
 * Mirrors social-wiring's create flow: the backend derives `base_url` /
 * `session_name` / `webhook_url` server-side, so the form asks for only
 * the two user-supplied fields (`WhatsAppConnectionCreate` on the backend).
 */
import * as React from 'react';
import { Loader2 } from 'lucide-react';

import { Button } from '../../design-system/ui/Button';
import { Dialog, DialogBody, DialogFooter, DialogHeader } from '../../design-system/ui/Dialog';
import { Input } from '../../design-system/ui/Input';
import { ApiError } from '../../api';
import type { WhatsAppConnectionLine, WhatsAppConnectionsHooks } from '../../whatsapp';

export interface CreateConnectionDialogProps {
  open: boolean;
  onClose: () => void;
  mutations: ReturnType<WhatsAppConnectionsHooks['useConnectionMutations']>;
  onCreated?: (line: WhatsAppConnectionLine) => void;
}

export function CreateConnectionDialog({
  open,
  onClose,
  mutations,
  onCreated,
}: CreateConnectionDialogProps) {
  const [label, setLabel] = React.useState('');
  const [apiKey, setApiKey] = React.useState('');
  const { create } = mutations;

  React.useEffect(() => {
    if (!open) {
      setLabel('');
      setApiKey('');
      create.reset();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!label.trim() || !apiKey.trim()) return;
    try {
      const line = await create.mutateAsync({ label: label.trim(), api_key: apiKey.trim() });
      onCreated?.(line);
      onClose();
    } catch {
      // Error is surfaced inline below via create.error.
    }
  };

  return (
    <Dialog open={open} onClose={onClose} title="Nova conexão WhatsApp">
      <form onSubmit={handleSubmit}>
        <DialogHeader>
          <h3 className="text-sm font-semibold">Nova conexão WhatsApp</h3>
        </DialogHeader>
        <DialogBody className="grid gap-3">
          <div className="grid gap-1.5">
            <label htmlFor="wa-connection-label" className="text-xs font-medium text-muted-foreground">
              Nome
            </label>
            <Input
              id="wa-connection-label"
              placeholder="Ex.: Atendimento comercial"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              disabled={create.isPending}
              autoFocus
            />
          </div>
          <div className="grid gap-1.5">
            <label htmlFor="wa-connection-api-key" className="text-xs font-medium text-muted-foreground">
              Chave de API WAHA
            </label>
            <Input
              id="wa-connection-api-key"
              type="password"
              placeholder="Chave do servidor WAHA"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              disabled={create.isPending}
            />
          </div>
          {create.isError && (
            <p role="alert" className="text-xs text-destructive" data-testid="wa-create-error">
              {create.error instanceof ApiError && create.error.status === 503
                ? 'WhatsApp (WAHA) não configurado neste servidor.'
                : create.error instanceof Error
                  ? create.error.message
                  : 'Falha ao criar a conexão.'}
            </p>
          )}
        </DialogBody>
        <DialogFooter className="gap-2">
          <Button type="button" variant="outline" onClick={onClose} disabled={create.isPending}>
            Cancelar
          </Button>
          <Button type="submit" disabled={create.isPending || !label.trim() || !apiKey.trim()}>
            {create.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : 'Criar conexão'}
          </Button>
        </DialogFooter>
      </form>
    </Dialog>
  );
}
