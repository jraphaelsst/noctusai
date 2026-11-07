/**
 * `LostReasonDialog` — "why was it lost?": a CODED reason from `meta.lost_reasons`, and free text
 * that is REQUIRED only for a reason that asks for it ("Outro"). The server twin refuses a missing
 * reason with 422 `motivo_obrigatorio`; that refusal is shown here, inline, never swallowed.
 */
import * as React from 'react';

import { Button } from '../../../design-system/ui/Button';
import {
  Dialog as RadixDialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '../../../design-system/ui/radix-dialog';
import { Textarea } from '../../../design-system/ui/textarea';
import type { FunnelLostReason } from './types';

export interface LostReasonDialogProps {
  open: boolean;
  /** `meta.lost_reasons`. */
  reasons: FunnelLostReason[];
  /** The card's name, for the title. */
  cardTitle: string;
  busy?: boolean;
  /** A server refusal to show inline (pt-BR). */
  error?: string | null;
  onConfirm: (value: { motivo_codigo: string; motivo_texto?: string }) => void;
  onCancel: () => void;
}

export function LostReasonDialog({ open, reasons, cardTitle, busy = false, error, onConfirm, onCancel }: LostReasonDialogProps) {
  const [codigo, setCodigo] = React.useState('');
  const [texto, setTexto] = React.useState('');
  const [tentou, setTentou] = React.useState(false);

  // A fresh form per opening: a reason typed for another card must never ride along.
  React.useEffect(() => {
    if (open) {
      setCodigo('');
      setTexto('');
      setTentou(false);
    }
  }, [open]);

  const reason = reasons.find((r) => r.codigo === codigo);
  const faltaMotivo = !reason;
  const faltaTexto = !!reason?.exige_texto && !texto.trim();
  const textoInvalido = tentou && faltaTexto;

  function confirmar() {
    setTentou(true);
    if (faltaMotivo || faltaTexto) return;
    onConfirm({ motivo_codigo: codigo, ...(texto.trim() ? { motivo_texto: texto.trim() } : {}) });
  }

  return (
    <RadixDialog open={open} onOpenChange={(next) => { if (!next) onCancel(); }}>
      <DialogContent className="max-sm:h-[100dvh] max-sm:w-screen max-sm:max-w-none max-sm:content-start max-sm:overflow-y-auto max-sm:rounded-none max-sm:border-0">
        <DialogHeader>
          <DialogTitle>Marcar como perdido</DialogTitle>
          <DialogDescription>
            Por que {cardTitle} foi perdido? O motivo alimenta o relatório de perdas.
          </DialogDescription>
        </DialogHeader>

        <fieldset className="space-y-2" disabled={busy}>
          <legend className="mb-1 text-sm font-medium">Motivo</legend>
          {reasons.map((r) => (
            <label key={r.codigo} className="flex cursor-pointer items-center gap-2 text-sm">
              <input
                type="radio"
                name="motivo_perda"
                value={r.codigo}
                checked={codigo === r.codigo}
                onChange={() => setCodigo(r.codigo)}
              />
              {r.label}
            </label>
          ))}
          {tentou && faltaMotivo && (
            <p role="alert" className="text-sm text-destructive">Escolha um motivo.</p>
          )}
        </fieldset>

        {reason && (
          <div className="space-y-1">
            <label htmlFor="funnel-lost-text" className="text-sm font-medium">
              Detalhes{reason.exige_texto ? '' : ' (opcional)'}
            </label>
            <Textarea
              id="funnel-lost-text"
              value={texto}
              onChange={(e) => setTexto(e.target.value)}
              rows={3}
              disabled={busy}
              required={reason.exige_texto}
              aria-invalid={textoInvalido || undefined}
              aria-describedby={textoInvalido ? 'funnel-lost-text-error' : undefined}
            />
            {textoInvalido && (
              <p id="funnel-lost-text-error" role="alert" className="text-sm text-destructive">
                Descreva o motivo: para “{reason.label}” o texto é obrigatório.
              </p>
            )}
          </div>
        )}

        {error && (
          <p role="alert" className="text-sm text-destructive">{error}</p>
        )}

        <DialogFooter>
          <Button variant="ghost" onClick={onCancel} disabled={busy}>Cancelar</Button>
          <Button variant="destructive" onClick={confirmar} disabled={busy}>
            Marcar como perdido
          </Button>
        </DialogFooter>
      </DialogContent>
    </RadixDialog>
  );
}
LostReasonDialog.displayName = 'LostReasonDialog';
