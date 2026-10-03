/**
 * `<BotoesOrdem/>` — the "move up / move down" pair for one row of an ordered
 * list (negociação parcelas, aditivo schedule). The caller owns the move
 * (`moverNaLista` in `parcelaOrdem.ts`) and what persisting it means.
 */
import { ArrowDown, ArrowUp } from "lucide-react";

import { Button } from "@/components/ui/button";

export interface BotoesOrdemProps {
  indice: number;
  total: number;
  onMover: (delta: -1 | 1) => void;
  /** e.g. a reorder request in flight. */
  disabled?: boolean;
  /** Accessible noun — "parcela" ⇒ "Mover parcela para cima". */
  rotulo?: string;
  testIdPrefixo?: string;
  className?: string;
}

export function BotoesOrdem({
  indice,
  total,
  onMover,
  disabled = false,
  rotulo = "parcela",
  testIdPrefixo,
  className = "h-7 w-7 p-0",
}: BotoesOrdemProps) {
  return (
    <>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        className={className}
        disabled={disabled || indice === 0}
        onClick={() => onMover(-1)}
        aria-label={`Mover ${rotulo} para cima`}
        data-testid={testIdPrefixo ? `${testIdPrefixo}-subir` : undefined}
      >
        <ArrowUp className="h-3.5 w-3.5" />
      </Button>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        className={className}
        disabled={disabled || indice === total - 1}
        onClick={() => onMover(1)}
        aria-label={`Mover ${rotulo} para baixo`}
        data-testid={testIdPrefixo ? `${testIdPrefixo}-descer` : undefined}
      >
        <ArrowDown className="h-3.5 w-3.5" />
      </Button>
    </>
  );
}

export default BotoesOrdem;
