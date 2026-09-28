/**
 * `<StageRolePanel/>` — a collapsible "Papéis das etapas" control: one
 * dropdown per system role, picking a stage reassigns that role to it.
 *
 * The seed's generic `PipelineStagesManager` (the "Configurar etapas" panel
 * `PipelineBoard` renders) edits label/cor/posição/ativo but has NO control
 * for a stage's semantic `papel` — it can only tell you a role is blocking a
 * delete ("Atribua o papel a outra etapa primeiro"), never let you actually
 * do that (comercial achado #14). This is board-agnostic: a caller supplies
 * its own role labels, current stages and an `onAssign` writer, so BOTH the
 * Comercial funnel (`fechado`) and the Esteira board (`aprovacao_cliente` /
 * `agendado`, `EsteiraBoard.tsx`) render the same control instead of each
 * hand-rolling it — Esteira's own private copy (`PapeisEtapas`) was migrated
 * onto this organ, byte-for-byte behaviour, labels and refusals preserved.
 *
 * Both consumers are within igig — no OTHER product has a stage-role picker
 * yet (checked 2026-09: erp-imobiliario/social-wiring's pipelines have no
 * `roleLabels=` usage), so this stays an igig-local organ rather than a
 * `@noctusai/lib` lift. Revisit once a second PRODUCT needs it.
 */
import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@noctusai/lib";

export interface StageRolePanelStage {
  id: string;
  label: string;
  papel: string | null;
}

export interface StageRolePanelProps {
  /** Collapsible header text. Default: "Papéis das etapas". */
  title?: string;
  /** `papel` slug → pt-BR label, one row per entry. */
  roleLabels: Record<string, string>;
  /** The board's current stages (id/label/papel) to populate each `<select>`. */
  stages: StageRolePanelStage[];
  /** Fired when the user picks a NEW stage for a role — the caller's mutation. */
  onAssign: (etapaId: string, papel: string) => void;
  /** Disables every `<select>` while a reassignment is in flight. */
  isPending?: boolean;
  className?: string;
}

export function StageRolePanel({
  title = "Papéis das etapas",
  roleLabels,
  stages,
  onAssign,
  isPending,
  className,
}: StageRolePanelProps) {
  const [aberto, setAberto] = useState(false);

  function etapaComPapel(papel: string): string {
    return stages.find((e) => e.papel === papel)?.id ?? "";
  }

  return (
    <div className={cn("rounded-lg border border-border", className)} data-testid="stage-role-panel">
      <button
        type="button"
        className="flex w-full items-center justify-between p-2 text-left text-sm font-medium text-foreground"
        onClick={() => setAberto((v) => !v)}
        aria-expanded={aberto}
      >
        {title}
        <ChevronDown className={cn("h-4 w-4 transition-transform", aberto && "rotate-180")} />
      </button>
      {aberto && (
        <div className="space-y-2 border-t border-border p-3">
          {Object.entries(roleLabels).map(([papel, rotulo]) => (
            <label key={papel} className="flex items-center justify-between gap-2 text-sm">
              <span className="text-muted-foreground">{rotulo}</span>
              <select
                aria-label={`Etapa com o papel ${rotulo}`}
                className="h-9 min-w-0 max-w-[60%] rounded-md border border-border bg-background px-2 text-sm text-foreground"
                value={etapaComPapel(papel)}
                disabled={isPending}
                onChange={(e) => onAssign(e.target.value, papel)}
              >
                <option value="" disabled>
                  Escolha uma etapa…
                </option>
                {stages.map((e) => (
                  <option key={e.id} value={e.id}>
                    {e.label}
                  </option>
                ))}
              </select>
            </label>
          ))}
        </div>
      )}
    </div>
  );
}
