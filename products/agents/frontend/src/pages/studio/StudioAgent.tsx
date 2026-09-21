/**
 * Agent Studio — `/studio/:key` (CONTRACT §G): the agent shell. Tabs are
 * URL-driven (`?tab=`), and each tab is its own lazily-imported file under
 * `./tabs/` (§J2.4 — FE-KE replaces the four KE tab files wholesale).
 */
import { lazy, Suspense, type ComponentType, type LazyExoticComponent } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { ArrowLeft, Boxes } from "lucide-react";
import { Badge } from "@noctusai/lib/design-system";
import { StudioError, StudioLoading } from "@/components/studio/StudioStates";
import { useStudioAgent } from "@/hooks/studio/useStudioAgents";
import { ApiError } from "@/lib/errors";
import { cn } from "@/lib/utils";
import { DEFAULT_TAB, STUDIO_TABS, isStudioTab, type StudioTabId } from "./studioTabs";

type TabComponent = LazyExoticComponent<ComponentType<{ agentKey: string }>>;

const TAB_COMPONENTS: Record<StudioTabId, TabComponent> = {
  "visao-geral": lazy(() => import("./tabs/OverviewTab")),
  prompt: lazy(() => import("./tabs/PromptTab")),
  skills: lazy(() => import("./tabs/SkillsTab")),
  configuracoes: lazy(() => import("./tabs/SettingsTab")),
  conhecimento: lazy(() => import("./tabs/KnowledgeTab")),
  avaliacoes: lazy(() => import("./tabs/EvalsTab")),
  clientes: lazy(() => import("./tabs/ClientsTab")),
  versoes: lazy(() => import("./tabs/VersionsTab")),
  compilado: lazy(() => import("./tabs/CompiledTab")),
  conversar: lazy(() => import("./tabs/ChatTab")),
};

function shellErrorMessage(error: unknown): string | undefined {
  if (error instanceof ApiError) {
    if (error.code === "not_studio_agent") {
      return "Este agente usa a definição legada (no código) e não é editável no Agent Studio.";
    }
    if (error.status === 404) return "Agente não encontrado nesta organização.";
  }
  return undefined;
}

export default function StudioAgent() {
  const { key = "" } = useParams<{ key: string }>();
  const [params, setParams] = useSearchParams();
  const raw = params.get("tab");
  const tab: StudioTabId = isStudioTab(raw) ? raw : DEFAULT_TAB;
  const { data: agent, showSkeleton, isRefreshing, isError, error, refetch } = useStudioAgent(key);

  function selectTab(next: StudioTabId) {
    // Deep-link params (secao/chave/skill/versao/cliente) belong to one tab;
    // switching tabs by hand drops them.
    setParams({ tab: next });
  }

  const TabContent = TAB_COMPONENTS[tab];

  return (
    <div className="space-y-4">
      <Link to="/studio" className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
        <ArrowLeft className="h-3.5 w-3.5" /> Agent Studio
      </Link>

      {showSkeleton ? (
        <StudioLoading rows={2} testId="studio-agent-skeleton" />
      ) : isError ? (
        <StudioError error={error} mensagem={shellErrorMessage(error)} onRetry={refetch} />
      ) : agent ? (
        <>
          <div className="flex flex-wrap items-center gap-3">
            <Boxes className="h-6 w-6 text-primary" />
            <div>
              <h1 className="text-2xl font-bold text-foreground" data-testid="studio-agent-nome">
                {agent.nome}
              </h1>
              <p className="font-mono text-xs text-muted-foreground">{agent.key}</p>
            </div>
            <Badge variant={agent.ativo ? "default" : "muted"}>{agent.ativo ? "Ativo" : "Inativo"}</Badge>
            <Badge variant="outline">{agent.versao_ativa !== null ? `Versão ativa v${agent.versao_ativa}` : "Sem versão ativa"}</Badge>
            {agent.tem_rascunho && <Badge variant="outline">Rascunho em edição</Badge>}
            {isRefreshing && <span className="text-xs text-muted-foreground">Atualizando…</span>}
          </div>

          <nav className="flex gap-1 overflow-x-auto border-b border-border" role="tablist" aria-label="Seções do agente">
            {STUDIO_TABS.map((t) => (
              <button
                key={t.id}
                type="button"
                role="tab"
                aria-selected={tab === t.id}
                data-testid={`studio-tab-${t.id}`}
                onClick={() => selectTab(t.id)}
                className={cn(
                  "whitespace-nowrap border-b-2 px-3 py-2 text-sm transition-colors",
                  tab === t.id
                    ? "border-primary font-medium text-foreground"
                    : "border-transparent text-muted-foreground hover:text-foreground",
                )}
              >
                {t.label}
              </button>
            ))}
          </nav>

          <div role="tabpanel">
            <Suspense fallback={<StudioLoading rows={3} testId="studio-tab-loading" />}>
              <TabContent agentKey={agent.key} />
            </Suspense>
          </div>
        </>
      ) : null}
    </div>
  );
}
