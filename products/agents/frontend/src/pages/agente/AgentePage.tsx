/**
 * The agent page — `/agentes/:key` (agents-unified CONTRACT §7). ONE page for every agent: the header comes from
 * the painel (`GET /api/agents/{key}/painel`), the section nav is `painel.secoes` (the sections THIS caller may open
 * on THIS agent, decided by the server) titled by the model (`GET /api/studio/modelo`), and each section renders
 * through the registry below. The content-area renderers are the Studio tab components, unchanged.
 *
 * The section is URL-driven (`?tab=<id>`, the pre-unification Studio tab id), so every existing deep link —
 * `/studio/:key?tab=prompt&secao=…` redirects here with its query — keeps opening the same place.
 */
import { lazy, Suspense, type ComponentType, type LazyExoticComponent } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { ArrowLeft, Bot, Lock } from "lucide-react";
import { Badge } from "@noctusai/lib/design-system";
import type { AgentePainel } from "@/api/agentes/types";
import { StudioError, StudioLoading } from "@/components/studio/StudioStates";
import { useAgenteInterno, useAgenteModelo, useAgentePainel } from "@/hooks/useAgentesPainel";
import { ApiError } from "@/lib/errors";
import { cn } from "@/lib/utils";
import { AgenteSwitch, ORIGEM_LABEL, papelLabel } from "@/pages/Agentes";
import type { SecaoProps } from "./secaoTypes";

type Secao = LazyExoticComponent<ComponentType<SecaoProps>>;

/** A Studio tab renderer takes only `agentKey`; adapt it to the section props. */
const studioTab = (load: () => Promise<{ default: ComponentType<{ agentKey: string }> }>): Secao =>
  lazy(async () => {
    const { default: Tab } = await load();
    return { default: ({ agentKey }: SecaoProps) => <Tab agentKey={agentKey} /> };
  });

/** section id -> renderer. A content area renders with the Studio tab of the same id. */
const SECOES: Record<string, Secao> = {
  "visao-geral": lazy(() => import("./secoes/VisaoGeralSecao")),
  persona: lazy(() => import("./secoes/PersonaSecao")),
  prompt: studioTab(() => import("@/pages/studio/tabs/PromptTab")),
  skills: studioTab(() => import("@/pages/studio/tabs/SkillsTab")),
  configuracoes: studioTab(() => import("@/pages/studio/tabs/SettingsTab")),
  conhecimento: studioTab(() => import("@/pages/studio/tabs/KnowledgeTab")),
  avaliacoes: studioTab(() => import("@/pages/studio/tabs/EvalsTab")),
  clientes: studioTab(() => import("@/pages/studio/tabs/ClientsTab")),
  canais: studioTab(() => import("@/pages/studio/tabs/ChannelsTab")),
  aprendizados: studioTab(() => import("@/pages/studio/tabs/LearningsTab")),
  versoes: studioTab(() => import("@/pages/studio/tabs/VersionsTab")),
  textos: studioTab(() => import("@/pages/studio/tabs/TextosTab")),
  ferramentas: studioTab(() => import("@/pages/studio/tabs/FerramentasTab")),
  decisoes: studioTab(() => import("@/pages/studio/tabs/DecisoesTab")),
  qualificacao: studioTab(() => import("@/pages/studio/tabs/QualificacaoTab")),
  biblioteca: studioTab(() => import("@/pages/studio/tabs/BibliotecaTab")),
  especificacoes: studioTab(() => import("@/pages/studio/tabs/EspecificacoesTab")),
  "especificacoes-org": studioTab(() => import("@/pages/studio/tabs/EspecificacoesOrgTab")),
  controles: studioTab(() => import("@/pages/studio/tabs/ControlesTab")),
  conversas: studioTab(() => import("@/pages/studio/tabs/ConversasTab")),
  conformidade: studioTab(() => import("@/pages/studio/tabs/ConformidadeTab")),
};
/** Sections whose renderer depends on the agent's ORIGIN (data), not its key. */
const CONVERSAR_LEGADO: Secao = lazy(() => import("./secoes/ConversarLegadoSecao"));
const CONVERSAR_STUDIO: Secao = studioTab(() => import("@/pages/studio/tabs/ChatTab"));
const COMPILADO_ORG: Secao = studioTab(() => import("@/pages/studio/tabs/CompiledTab"));
const COMPILADO_PLATAFORMA: Secao = studioTab(() => import("@/pages/studio/tabs/CompiladoJuliaTab"));

export function secaoRenderer(id: string, agente: AgentePainel): Secao | null {
  if (id === "conversar") return agente.origem === "legado" ? CONVERSAR_LEGADO : CONVERSAR_STUDIO;
  if (id === "compilado") return agente.origem === "org" ? COMPILADO_ORG : COMPILADO_PLATAFORMA;
  return SECOES[id] ?? null;
}

function paginaErro(error: unknown): string | undefined {
  if (error instanceof ApiError && error.status === 404) return "Agente não encontrado nesta organização.";
  return undefined;
}

export default function AgentePage() {
  const { key = "" } = useParams<{ key: string }>();
  const [params, setParams] = useSearchParams();
  const painel = useAgentePainel(key);
  const modelo = useAgenteModelo();
  const agente = painel.data;
  const titulos = new Map((modelo.data?.secoes ?? []).map((s) => [s.id, s]));
  const secoes = agente?.secoes ?? [];
  // Internals are asked for only when the server already opened an internal section to this caller.
  const temInterna = secoes.some((id) => titulos.get(id)?.tier === "plataforma");
  const interno = useAgenteInterno(key, temInterna);
  const pedida = params.get("tab");
  const atual = pedida && secoes.includes(pedida) ? pedida : (secoes[0] ?? null);

  function selecionar(id: string) {
    // Deep-link params (secao/chave/skill/versao/cliente) belong to one section; switching drops them.
    setParams({ tab: id });
  }

  const showSkeleton = painel.showSkeleton || modelo.showSkeleton;
  const erro = painel.isError ? painel.error : modelo.isError ? modelo.error : null;
  const Conteudo = agente && atual ? secaoRenderer(atual, agente) : null;

  return (
    <div className="space-y-4">
      <Link to="/agentes" className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
        <ArrowLeft className="h-3.5 w-3.5" /> Agentes
      </Link>

      {showSkeleton ? (
        <StudioLoading rows={2} testId="agente-skeleton" />
      ) : erro ? (
        <StudioError
          error={erro}
          mensagem={painel.isError ? paginaErro(painel.error) : undefined}
          onRetry={() => (painel.isError ? painel.refetch() : modelo.refetch())}
        />
      ) : agente ? (
        <>
          <div className="flex flex-wrap items-center gap-3">
            <Bot className="h-6 w-6 text-primary" />
            <div>
              <h1 className="text-2xl font-bold text-foreground" data-testid="agente-nome">
                {agente.nome}
              </h1>
              <p className="font-mono text-xs text-muted-foreground">{agente.key}</p>
            </div>
            {agente.papel && <Badge variant="default">{papelLabel(agente.papel)}</Badge>}
            <Badge variant="outline" data-testid="agente-origem">
              {ORIGEM_LABEL[agente.origem]}
            </Badge>
            <AgenteSwitch agente={agente} />
            {interno.data && (
              <Badge variant="outline" data-testid="agente-versao">
                {interno.data.versao_ativa !== null ? `Versão ativa v${interno.data.versao_ativa}` : "Sem versão ativa"}
                {interno.data.tem_rascunho ? " · rascunho em edição" : ""}
              </Badge>
            )}
            {(painel.isRefreshing || modelo.isRefreshing) && <span className="text-xs text-muted-foreground">Atualizando…</span>}
          </div>

          {secoes.length > 1 && (
            <nav className="flex gap-1 overflow-x-auto border-b border-border" role="tablist" aria-label="Seções do agente">
              {secoes.map((id) => (
                <button
                  key={id}
                  type="button"
                  role="tab"
                  aria-selected={atual === id}
                  data-testid={`agente-secao-${id}`}
                  onClick={() => selecionar(id)}
                  className={cn(
                    "whitespace-nowrap border-b-2 px-3 py-2 text-sm transition-colors",
                    atual === id ? "border-primary font-medium text-foreground" : "border-transparent text-muted-foreground hover:text-foreground",
                  )}
                >
                  {titulos.get(id)?.titulo ?? id}
                </button>
              ))}
            </nav>
          )}

          {!atual ? (
            <div className="flex items-center gap-2 rounded-lg border border-dashed border-border bg-card p-6 text-sm text-muted-foreground" data-testid="agente-sem-secoes">
              <Lock className="h-4 w-4" /> Nada deste agente está disponível para o seu acesso.
            </div>
          ) : !Conteudo ? (
            <div className="rounded-lg border border-dashed border-border bg-card p-6 text-sm text-muted-foreground" role="alert" data-testid="agente-secao-desconhecida">
              A seção “{titulos.get(atual)?.titulo ?? atual}” ainda não está disponível nesta versão do aplicativo. Recarregue a página.
            </div>
          ) : (
            <div role="tabpanel">
              <Suspense fallback={<StudioLoading rows={3} testId="agente-secao-loading" />}>
                <Conteudo agentKey={agente.key} agente={agente} />
              </Suspense>
            </div>
          )}
        </>
      ) : null}
    </div>
  );
}
