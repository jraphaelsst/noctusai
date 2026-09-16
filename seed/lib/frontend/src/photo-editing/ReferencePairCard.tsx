/**
 * `<ReferencePairCard/>` — one before/after pair from the global reference
 * pool (contract §5 `/referencias`, platform scope).
 *
 * Deliberately renders the pair as two static side-by-side thumbnails rather
 * than embedding `BeforeAfterCompare` — the pool is a management GRID (many
 * cards on screen at once, quick visual scan), where a compare slider per
 * card adds interaction cost without adding information; the interactive
 * compare belongs on the review flow (`PhotoReviewGrid`'s expanded state),
 * where there is exactly one photo in focus.
 *
 * Archive is a two-step inline confirm (no modal) — "delete" here is a soft
 * archive (contract §5: kept for history, no longer counts toward the pool
 * limit), so the destructive-looking action deliberately reads as reversible.
 */
import { useState } from 'react';
import { Badge } from '../design-system/ui/Badge';
import { Button } from '../design-system/ui/Button';
import { cn } from '../utils';
import type { ReferenciaPar } from './hooks';

export interface ReferencePairCardProps {
  referencia: ReferenciaPar;
  /** Omit to render the card read-only (no archive control) — e.g. for a non-curator viewer. */
  onArquivar?: (id: string) => void;
  isArquivando?: boolean;
  /** Display label for the room literal (e.g. `area_externa` → "Área externa"). Default: the raw value. */
  formatComodo?: (comodo: string) => string;
  /** Display label for an edit-type literal. Default: the raw value. */
  formatTipoEdicao?: (tipo: string) => string;
  className?: string;
}

const identity = (value: string) => value;

export function ReferencePairCard({
  referencia,
  onArquivar,
  isArquivando = false,
  formatComodo = identity,
  formatTipoEdicao = identity,
  className,
}: ReferencePairCardProps) {
  const [confirmando, setConfirmando] = useState(false);
  const arquivada = !!referencia.arquivada_em;

  return (
    <div
      className={cn(
        'flex flex-col gap-3 rounded-lg border border-border bg-background p-3',
        arquivada && 'opacity-60',
        className,
      )}
    >
      <div className="grid grid-cols-2 gap-2">
        <figure className="flex flex-col gap-1">
          <img
            src={referencia.antes_url}
            alt="Antes"
            className="aspect-square w-full rounded-md object-cover"
          />
          <figcaption className="text-center text-xs text-muted-foreground">Antes</figcaption>
        </figure>
        <figure className="flex flex-col gap-1">
          <img
            src={referencia.depois_url}
            alt="Depois"
            className="aspect-square w-full rounded-md object-cover"
          />
          <figcaption className="text-center text-xs text-muted-foreground">Depois</figcaption>
        </figure>
      </div>

      <div className="flex flex-wrap items-center gap-1.5">
        <Badge variant="outline">{formatComodo(referencia.comodo)}</Badge>
        {referencia.tipos_edicao.map((tipo) => (
          <Badge key={tipo} variant="muted">
            {formatTipoEdicao(tipo)}
          </Badge>
        ))}
        {arquivada && <Badge variant="destructive">Arquivada</Badge>}
      </div>

      {referencia.nota && <p className="text-sm text-muted-foreground">{referencia.nota}</p>}

      {onArquivar && !arquivada && (
        <div className="flex justify-end gap-2">
          {confirmando ? (
            <>
              <span className="mr-auto self-center text-xs text-muted-foreground">
                Arquivar este par?
              </span>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setConfirmando(false)}
                disabled={isArquivando}
              >
                Cancelar
              </Button>
              <Button
                variant="destructive"
                size="sm"
                onClick={() => {
                  onArquivar(referencia.id);
                  setConfirmando(false);
                }}
                disabled={isArquivando}
              >
                {isArquivando ? 'Arquivando…' : 'Confirmar'}
              </Button>
            </>
          ) : (
            <Button variant="outline" size="sm" onClick={() => setConfirmando(true)}>
              Arquivar
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
