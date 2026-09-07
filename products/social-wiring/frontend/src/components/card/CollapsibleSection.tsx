/**
 * CollapsibleSection — one titled, foldable block of card body.
 *
 * Lifted out of `ClienteCardDialog.PessoaDocumentosSection` when the card grew
 * a SECOND thing worth folding away (the Dados obrigatórios / Outros dados
 * pair). Two hand-rolled copies of a chevron header would have been two places
 * for the open/closed keyboard semantics to drift, and the second copy is the
 * one that quietly ships without `aria-expanded`.
 *
 * 🔴 CHILDREN ARE A THUNK, NOT A NODE — AND THAT IS LOAD-BEARING
 * --------------------------------------------------------------
 * JSX children are evaluated by the CALLER before this component ever runs, so
 * `{open && children}` would still have built every collapsed section's
 * subtree. That is merely wasteful for a static block and actively wrong for
 * the one this was extracted from: each comprador's panel opens its own
 * queries against its own `cliente_id`, so three collapsed parties would fire
 * six fetches nobody asked for. Taking a function means a closed section costs
 * literally nothing, and OPENING is what asks for the data.
 *
 * Keep the thunk when adding callers. It is the difference between a fold that
 * hides work and a fold that only hides pixels.
 *
 * Presentational only (`card/**`): props in, callbacks out.
 */
import { useState, type ReactNode } from "react";

import { ChevronDown, ChevronUp } from "lucide-react";

export interface CollapsibleSectionProps {
  /** The heading. Rendered inside the toggle, so clicking the words folds. */
  titulo: ReactNode;
  defaultOpen?: boolean;
  /**
   * The section's own testid, and the ROOT of its two derived ones:
   * `${testId}-toggle` and `${testId}-corpo`. Taken whole rather than
   * prefixed here, so a caller that already owned a testid keeps it exactly —
   * this component was extracted from one that did.
   */
  testId: string;
  /**
   * Rendered at the right end of the header, INSIDE the toggle — for a
   * readout that must stay legible while the section is closed (a progress
   * count, a refresh spinner). Anything clickable belongs in `acao`.
   */
  resumo?: ReactNode;
  /** Rendered beside the toggle, OUTSIDE it, so clicking it does not fold. */
  acao?: ReactNode;
  children: () => ReactNode;
}

export function CollapsibleSection({
  titulo,
  defaultOpen = false,
  testId,
  resumo,
  acao,
  children,
}: CollapsibleSectionProps) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div className="mb-2 rounded-lg border" data-testid={testId}>
      <div className="flex items-center gap-2 pr-2">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          className="flex min-w-0 flex-1 items-center gap-2 px-3 py-2.5 text-left hover:bg-muted/50"
          data-testid={`${testId}-toggle`}
        >
          {open ? (
            <ChevronUp className="h-4 w-4 shrink-0 text-muted-foreground" />
          ) : (
            <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" />
          )}
          <span className="min-w-0 flex-1">{titulo}</span>
          {resumo}
        </button>
        {acao}
      </div>
      {open && (
        <div className="border-t px-3 pb-3 pt-3" data-testid={`${testId}-corpo`}>
          {children()}
        </div>
      )}
    </div>
  );
}
