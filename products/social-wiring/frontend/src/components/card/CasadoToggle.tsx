/**
 * `<CasadoToggle/>` — the "Casado(a)" control that gates every marriage-only
 * block on a party's panel: the cônjuge qualification (already server-gated
 * inside `QualificacaoCompletudePanel`), the certidão-de-casamento slot
 * (`CertidaoCasamentoSlot`), and the `regime_bens`/`data_casamento`
 * fields/suggestions (`DadosPessoaisForm`, `DocumentoChecklistSection`).
 *
 * 🔴 NO NEW COLUMN, AND THAT IS DELIBERATE. `clientes.estado_civil`
 * (migration 097) already carries the one fact this control is about —
 * `estadoCivilExigeConjuge` (CC art. 1.647) is the SAME predicate every
 * marriage-only block above gates on — so a second, independently-persisted
 * boolean would be a second place that fact could disagree with the first.
 * "Durable, not component-local" is satisfied by writing through the exact
 * column every other reader already keys off, not by inventing a column of
 * its own.
 *
 * VISIBLE ONLY once the record already reads a married state — set via
 * `DadosPessoaisForm`'s own "Estado civil" `<Select>`, or an extraction
 * confirmation. This control's own job is a one-click UNDO of that fact
 * (e.g. it was set in error, or a suggestion was confirmed too eagerly),
 * not a second way to SET it: turning it on has no meaning this control
 * could express better than picking the actual civil status. Turning it
 * OFF clears `estado_civil` through the caller's OWN save path — the same
 * one `DadosPessoaisForm`/`ChecklistItemRow` already write through — so
 * every block keyed off that column reacts identically on the next read,
 * with nothing held in this component's own state.
 *
 * Presentational (`card/**`): the checked value is not tracked here at all
 * — a mounted `<CasadoToggle/>` IS the "checked" state (see `estaCasado`),
 * matching the visible-only-when-married contract above.
 */
import { TokenCheckbox } from "@noctusai/lib/components";

export interface CasadoToggleProps {
  /** Clears the marriage state on the record. Never called with `true` —
   *  see the file docblock for why this control offers no "on" action. */
  onDesmarcar: () => void;
  salvando?: boolean;
  /** Disambiguates testids when several parties' toggles are on screen. */
  testId?: string;
}

export function CasadoToggle({
  onDesmarcar,
  salvando,
  testId = "casado-toggle",
}: CasadoToggleProps) {
  return (
    <div className="mb-3 flex items-center gap-2" data-testid={testId}>
      <TokenCheckbox
        checked
        disabled={salvando}
        onCheckedChange={(checked) => {
          if (!checked) onDesmarcar();
        }}
        label="Casado(a)"
        testId={`${testId}-checkbox`}
      />
      <span className="text-xs font-medium text-muted-foreground">Casado(a)</span>
    </div>
  );
}
