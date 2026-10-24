/**
 * UploadErro — the on-screen half of the upload-refusal organ
 * (`../upload-refusal`): renders a refused upload as `"x.pdf" não foi
 * enviado: <motivo>` until the next attempt or the user dismisses it.
 *
 *     const envio = useUploadDocumento((file) => upload.mutateAsync({ file }));
 *     <UploadErro erro={envio.erro} onDismiss={envio.limpar} />
 *
 * `chave` filters a hook shared by many rows: a row passes its own key and
 * shows only its own refusal (`envio.enviarEm(chave, file)`).
 *
 * Renders nothing when there is no refusal (or it belongs to another row), so
 * it is always safe to mount. `role="alert"` announces it.
 * KB § PATTERNS/frontend/silent-refusal.md.
 */
import { X } from 'lucide-react';

import { textoDaRecusa, type UploadRecusa } from '../upload-refusal';
import { cn } from '../utils';

export interface UploadErroProps {
  erro: UploadRecusa | null | undefined;
  /** Show only a refusal tagged with this key (per-row rendering). */
  chave?: string;
  /** Adds a dismiss (×) button. */
  onDismiss?: () => void;
  className?: string;
  'data-testid'?: string;
}

export function UploadErro({ erro, chave, onDismiss, className, 'data-testid': testId = 'upload-erro' }: UploadErroProps) {
  if (!erro) return null;
  if (chave !== undefined && erro.chave !== chave) return null;
  return (
    <div
      role="alert"
      data-testid={testId}
      className={cn('flex items-start gap-1.5 text-xs text-destructive', className)}
    >
      <p className="min-w-0 flex-1 break-words">{textoDaRecusa(erro)}</p>
      {onDismiss && (
        <button
          type="button"
          onClick={onDismiss}
          aria-label="Dispensar aviso"
          className="shrink-0 rounded p-0.5 hover:bg-destructive/10"
          data-testid={`${testId}-dispensar`}
        >
          <X className="h-3 w-3" aria-hidden="true" />
        </button>
      )}
    </div>
  );
}
