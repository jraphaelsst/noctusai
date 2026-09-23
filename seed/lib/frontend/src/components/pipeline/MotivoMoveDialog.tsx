/**
 * `<MotivoMoveDialog/>` — ask for a reason before a pipeline move commits.
 *
 * Built to be driven from `PipelineBoard`'s `onBeforeMove`: resolve the
 * intercept's promise with the dialog's outcome rather than treating the
 * dialog as a persistent piece of page state.
 *
 * Mobile-first (R0): a full-screen sheet below the `sm` (640px) breakpoint —
 * `max-sm:` utilities only, so desktop (≥640px) keeps the design-system's
 * default centered `RadixDialog` byte-for-byte (mirrors `CardHubDialog`'s
 * established R0 pattern).
 *
 * Usage:
 * ```tsx
 * const [pending, setPending] = useState<{
 *   resolve: (d: MoveDecision) => void;
 *   ctx: MoveIntentContext<Negociacao>;
 * } | null>(null);
 *
 * <PipelineBoard
 *   hooks={pipeline}
 *   renderCard={...}
 *   onBeforeMove={(ctx) => new Promise<MoveDecision>((resolve) => setPending({ resolve, ctx }))}
 * />
 * {pending && (
 *   <MotivoMoveDialog
 *     open
 *     title={`Mover para ${pending.ctx.toStage.label}?`}
 *     onCancel={() => { pending.resolve(false); setPending(null); }}
 *     onConfirm={(motivo) => { pending.resolve({ motivo }); setPending(null); }}
 *   />
 * )}
 * ```
 */
import * as React from 'react';

import { Button } from '../../design-system/ui/Button';
import { Textarea } from '../../design-system/ui/textarea';
import {
  Dialog as RadixDialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '../../design-system/ui/radix-dialog';

export interface MotivoMoveDialogProps {
  open: boolean;
  /** Column header text, e.g. `"Mover para Fechado?"`. */
  title: string;
  /** Optional supporting copy under the title. */
  description?: React.ReactNode;
  /** Placeholder for the reason textarea. */
  placeholder?: string;
  /** Reason is required to confirm. Default `false` (reason stays optional). */
  required?: boolean;
  confirmLabel?: string;
  cancelLabel?: string;
  /** Disables both controls while the caller's own mutation is in flight. */
  busy?: boolean;
  /** `motivo` is `undefined` when the field was left blank and not required. */
  onConfirm: (motivo: string | undefined) => void;
  onCancel: () => void;
}

export function MotivoMoveDialog({
  open,
  title,
  description,
  placeholder = 'Explique o motivo (opcional)',
  required = false,
  confirmLabel = 'Confirmar',
  cancelLabel = 'Cancelar',
  busy = false,
  onConfirm,
  onCancel,
}: MotivoMoveDialogProps) {
  const [motivo, setMotivo] = React.useState('');

  // A fresh field every time the dialog re-opens for a NEW move — a reason
  // typed for a cancelled move must never ride along on the next one.
  React.useEffect(() => {
    if (open) setMotivo('');
  }, [open]);

  const semMotivo = required && !motivo.trim();

  return (
    <RadixDialog open={open} onOpenChange={(next) => { if (!next) onCancel(); }}>
      <DialogContent
        aria-label={title}
        // Mobile-first (R0), `max-sm:` only — see `CardHubDialog.tsx`'s
        // identical pattern. Desktop keeps `radix-dialog.tsx`'s own classes.
        className="max-sm:h-[100dvh] max-sm:w-screen max-sm:max-w-none max-sm:content-start max-sm:overflow-y-auto max-sm:rounded-none max-sm:border-0"
      >
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          {description && <DialogDescription>{description}</DialogDescription>}
        </DialogHeader>
        <Textarea
          autoFocus
          value={motivo}
          onChange={(e) => setMotivo(e.target.value)}
          placeholder={placeholder}
          rows={4}
          aria-label="Motivo"
          disabled={busy}
        />
        <DialogFooter>
          <Button variant="ghost" onClick={onCancel} disabled={busy}>
            {cancelLabel}
          </Button>
          <Button
            variant="primary"
            disabled={busy || semMotivo}
            onClick={() => onConfirm(motivo.trim() || undefined)}
          >
            {confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </RadixDialog>
  );
}
MotivoMoveDialog.displayName = 'MotivoMoveDialog';
