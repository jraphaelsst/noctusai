/**
 * Agent Studio — "Visão geral" of an org INSTANCE of a platform agent (Julia v2 CONTRACT §2.6).
 * The org sees readiness only (complete or not, which of ITS specs are missing, the mode) — no
 * versions, hashes, notes or prompt: those are the platform's. Locked platform blocks are a label.
 */
import { Link } from "react-router-dom";
import { Lock } from "lucide-react";
import { Badge, EmptyState } from "@noctusai/lib/design-system";
import { StudioError, StudioLoading } from "@/components/studio/StudioStates";
import { useControle } from "@/hooks/studio/useControle";
import { useOrgStatus } from "@/hooks/studio/useConteudo";
import { useStudioAgent } from "@/hooks/studio/useStudioAgents";
import { studioTabHref } from "../studioTabs";

export default function InstanciaOverviewTab({ agentKey }: { agentKey: string }) {
  const agent = useStudioAgent(agentKey);
  const status = useOrgStatus(agentKey);
  const controle = useControle(agentKey);

  if (status.showSkeleton || agent.showSkeleton) return <StudioLoading rows={2} />;
  if (status.isError) return <StudioError error={status.error} onRetry={status.refetch} />;
  const s = status.data;
  if (!s) return <EmptyState message="Sem dados de prontidão." />;
  const pronto = s.completo && !s.sem_versao;

  return (
    <div className="space-y-4" data-testid="instancia-overview">
      <div className="grid gap-4 sm:grid-cols-3">
        <div className="rounded-lg border border-border bg-card p-4" data-testid="instancia-prontidao">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Prontidão</p>
          <div className="mt-2">
            <Badge variant={pronto ? "default" : "outline"}>{pronto ? "Pronto para ligar" : "Incompleto"}</Badge>
          </div>
          {s.sem_versao && <p className="mt-2 text-xs text-muted-foreground">A plataforma ainda não publicou este agente.</p>}
          {s.specs_faltando.length > 0 && (
            <p className="mt-2 text-xs text-muted-foreground">
              Faltam {s.specs_faltando.length} especificação(ões) da sua organização:{" "}
              <span className="font-mono">{s.specs_faltando.join(", ")}</span>.{" "}
              <Link className="text-primary hover:underline" to={studioTabHref(agentKey, "especificacoes-org")}>
                Preencher
              </Link>
            </p>
          )}
        </div>
        <div className="rounded-lg border border-border bg-card p-4" data-testid="instancia-modo">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Modo</p>
          <div className="mt-2">
            {controle.data ? <Badge variant={controle.data.modo === "ligado" ? "default" : "muted"}>{controle.data.modo}</Badge> : <span className="text-sm text-muted-foreground">—</span>}
          </div>
          <p className="mt-2 text-xs text-muted-foreground">
            <Link className="text-primary hover:underline" to={studioTabHref(agentKey, "controles")}>Abrir controles</Link>
          </p>
        </div>
        <div className="rounded-lg border border-border bg-card p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Definição</p>
          <p className="mt-2 flex items-center gap-1 text-sm text-muted-foreground" data-testid="instancia-bloco-plataforma">
            <Lock className="h-3.5 w-3.5" /> Bloco da plataforma · gerenciado pela NoctusAI
          </p>
          {agent.data?.versao_ativa != null && <p className="mt-1 text-xs text-muted-foreground">Versão em uso: v{agent.data.versao_ativa}</p>}
        </div>
      </div>
    </div>
  );
}
