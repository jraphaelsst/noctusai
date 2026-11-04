/**
 * `<CreateConnectionDialog/>` — label + WAHA API key form.
 *
 * The backend derives `base_url` / `session_name` / `webhook_url` server-side. `askApiKey` (default true) is the seam for
 * where the WAHA key comes from: true = the operator types it (the seed router); false = the backend provisions with its
 * own server key and the form asks for the name only (social-wiring -- a typed key would let a caller bind a line to a
 * WAHA session they do not own).
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
  /** Ask for the WAHA API key (default true). false = server-side key: the form is the name only. */
  askApiKey?: boolean;
}

export function CreateConnectionDialog({
  open,
  onClose,
  mutations,
  onCreated,
  askApiKey = true,
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
    if (!label.trim() || (askApiKey && !apiKey.trim())) return;
    try {
      const line = await create.mutateAsync(askApiKey ? { label: label.trim(), api_key: apiKey.trim() } : { label: label.trim() });
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
          {askApiKey && (
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
          )}
          {create.isError && (
            <p role="alert" className="text-xs text-destructive" data-testid="wa-create-error">
              {create.error instanceof ApiError && create.error.status === 503
                ? 'WhatsApp (WAHA) não configurado neste servidor.'
                : create.error instanceof ApiError && create.error.status === 403
                  ? 'Você não tem permissão para criar linhas de WhatsApp.'
                  : create.error instanceof ApiError && create.error.status === 409
                    ? 'Esta sessão do WhatsApp já está vinculada a uma linha.'
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
          <Button type="submit" disabled={create.isPending || !label.trim() || (askApiKey && !apiKey.trim())}>
            {create.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : 'Criar conexão'}
          </Button>
        </DialogFooter>
      </form>
    </Dialog>
  );
}
