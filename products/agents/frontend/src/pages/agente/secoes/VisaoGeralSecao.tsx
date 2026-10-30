/**
 * "Visão geral" section (agents-unified CONTRACT §3/§7): what any org member may know about the agent — its
 * public description, capabilities and state — then the tier-specific overview the SERVER opened for this caller:
 * an org admin on a platform instance gets the instance readiness (`InstanciaOverviewTab`), a superadmin on a
 * definition gets the version overview (`OverviewTab`). Which one is decided by `painel.secoes`, never by a role
 * string or an agent key.
 */
import { lazy, Suspense } from "react";
import { StudioLoading } from "@/components/studio/StudioStates";
import { AgenteResumo } from "@/pages/Agentes";
import type { SecaoProps } from "../secaoTypes";

const InstanciaOverviewTab = lazy(() => import("@/pages/studio/tabs/InstanciaOverviewTab"));
const OverviewTab = lazy(() => import("@/pages/studio/tabs/OverviewTab"));

export default function VisaoGeralSecao({ agentKey, agente }: SecaoProps) {
  const Detalhe = agente.secoes.includes("controles")
    ? InstanciaOverviewTab
    : agente.secoes.includes("versoes")
      ? OverviewTab
      : null;
  return (
    <div className="space-y-4" data-testid="secao-visao-geral">
      <div className="space-y-3 rounded-lg border border-border bg-card p-4">
        <AgenteResumo agente={agente} />
        {agente.capacidades.length > 0 && (
          <div>
            <p className="mb-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">Capacidades</p>
            <ul className="flex flex-wrap gap-1.5">
              {agente.capacidades.map((c) => (
                <li key={c} className="rounded-full border border-border bg-background px-2.5 py-0.5 text-xs text-foreground">
                  {c}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
      {Detalhe && (
        <Suspense fallback={<StudioLoading rows={2} testId="visao-geral-detalhe-loading" />}>
          <Detalhe agentKey={agentKey} />
        </Suspense>
      )}
    </div>
  );
}
