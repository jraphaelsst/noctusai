/**
 * Agent Studio — "Compilado" of a platform-defined agent (Julia v2 CONTRACT §2.3, §2.6): the "no
 * mysteries" view. Shows EVERYTHING the model receives for a version — the compiled system prompt
 * with its cache breakpoint, plus every content row that reaches the model outside it (system texts,
 * tool descriptions, decisions), each attributed to its row — and the same definition compiled FOR
 * this organisation (`{{org.x}}` replaced). Platform admin only; every read is audited server-side.
 */
import { useRef } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Badge, EmptyState } from "@noctusai/lib/design-system";
import type { PayloadAviso, PayloadManifestEntry } from "@/api/studio/types-julia";
import type { ManifestSection } from "@/api/studio/types";
import { CompiledPromptView, type CompiledPromptViewHandle } from "@/components/studio/CompiledPromptView";
import { CopyTextButton } from "@/components/studio/CopyTextButton";
import { RestrictedNotice } from "@/components/studio/ConteudoChrome";
import { StudioLoading } from "@/components/studio/StudioStates";
import { shortHash } from "@/components/studio/compiledSegments";
import { useCompiladoOrg, usePayload } from "@/hooks/studio/useConteudo";
import { useStudioAgent } from "@/hooks/studio/useStudioAgents";
import { useAgentVersionRefs } from "@/hooks/studio/useVersions";
import { studioTabHref, studioTier, type StudioTabId } from "../studioTabs";

const FORA_ROTULO: Record<string, { rotulo: string; tab: StudioTabId }> = {
  texto: { rotulo: "Texto do sistema", tab: "textos" },
  ferramenta: { rotulo: "Descrição de ferramenta", tab: "ferramentas" },
  decisao: { rotulo: "Decisão", tab: "decisoes" },
};

/** Entries outside the system prompt carry `inicio`/`fim` = null (CONTRACT §2.3 items 3-6). */
export function splitManifest(manifest: PayloadManifestEntry[]) {
  const dentro = manifest.filter((m) => m.inicio !== null && m.fim !== null) as Array<PayloadManifestEntry & { inicio: number; fim: number }>;
  const fora = manifest.filter((m) => m.inicio === null || m.fim === null);
  // The cache breakpoint is the end of the static prefix: every block except the client-in-focus layer.
  const estaticos = dentro.filter((m) => !(m.origem.tipo === "auto" && m.origem.campo === "cliente"));
  const pontoCache = estaticos.length > 0 ? Math.max(...estaticos.map((m) => m.fim)) : null;
  return { dentro: dentro as unknown as ManifestSection[], fora, pontoCache };
}

function Avisos({ avisos }: { avisos: PayloadAviso[] }) {
  if (avisos.length === 0) return null;
  return (
    <ul className="space-y-1" data-testid="compilado-avisos">
      {avisos.map((a, i) => (
        <li key={`${a.codigo}-${i}`} className={a.bloqueante ? "text-sm text-destructive" : "text-sm text-amber-700"}>
          {a.bloqueante ? "Bloqueante: " : "Aviso: "}{a.mensagem}
        </li>
      ))}
    </ul>
  );
}

function PayloadView({
  agentKey,
  hash,
  texto,
  tokens,
  manifest,
  avisos,
  faltando,
}: {
  agentKey: string;
  hash: string;
  texto: string;
  tokens: number;
  manifest: PayloadManifestEntry[];
  avisos: PayloadAviso[];
  faltando?: string[];
}) {
  const navigate = useNavigate();
  const ref = useRef<CompiledPromptViewHandle>(null);
  const { dentro, fora, pontoCache } = splitManifest(manifest);
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <Badge variant="outline" data-testid="compilado-hash">{shortHash(hash)}</Badge>
        <span className="tabular-nums text-muted-foreground">~{tokens.toLocaleString("pt-BR")} tokens</span>
        <CopyTextButton text={texto} label="Copiar prompt" />
        {faltando && faltando.length > 0 && <Badge variant="outline">Faltam especificações: {faltando.join(", ")}</Badge>}
      </div>
      <Avisos avisos={avisos} />
      <CompiledPromptView
        ref={ref}
        texto={texto}
        manifest={dentro}
        cacheBreakpoint={pontoCache}
        onOpenSource={(t) => navigate(studioTabHref(agentKey, t.tab, t.params))}
      />
      <section className="space-y-2 rounded-lg border border-border bg-card p-3" data-testid="compilado-fora">
        <h3 className="text-sm font-semibold">Chega ao modelo fora do prompt</h3>
        {fora.length === 0 ? (
          <p className="text-xs text-muted-foreground">Nenhum conteúdo adicional.</p>
        ) : (
          <ul className="divide-y divide-border text-sm">
            {fora.map((m) => {
              const meta = FORA_ROTULO[m.origem.tipo];
              return (
                <li key={m.chave} className="flex flex-wrap items-center gap-2 py-1.5" data-testid={`fora-${m.chave}`}>
                  <Badge variant="muted">{meta?.rotulo ?? m.origem.tipo}</Badge>
                  <span className="font-mono text-xs">{m.titulo}</span>
                  <span className="text-[11px] tabular-nums text-muted-foreground">{m.chars.toLocaleString("pt-BR")} caracteres · ~{m.tokens} tokens</span>
                  {meta && (
                    <Link className="ml-auto text-[11px] text-primary hover:underline" to={studioTabHref(agentKey, meta.tab)}>
                      Abrir origem
                    </Link>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </div>
  );
}

function PorVersao({ agentKey }: { agentKey: string }) {
  const refs = useAgentVersionRefs(agentKey);
  const [params, setParams] = useSearchParams();
  const versoes = refs.data?.versoes ?? [];
  const pedida = params.get("versao");
  const alvo = versoes.find((v) => v.id === pedida) ?? refs.draft ?? refs.ativa ?? versoes[0] ?? null;
  const payload = usePayload(agentKey, alvo?.id);

  if (refs.showSkeleton) return <StudioLoading rows={3} />;
  if (!alvo) return <EmptyState message="Este agente ainda não tem versões para compilar." />;
  return (
    <section className="space-y-3" data-testid="compilado-versao">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-sm font-semibold">Definição</h2>
        <select
          aria-label="Versão"
          className="h-9 rounded-md border border-input bg-background px-2 text-sm"
          value={alvo.id}
          onChange={(e) => setParams({ tab: "compilado", versao: e.target.value })}
        >
          {versoes.map((v) => <option key={v.id} value={v.id}>v{v.versao} · {v.status}</option>)}
        </select>
        <Badge variant={alvo.status === "rascunho" ? "default" : "muted"}>{alvo.status === "rascunho" ? "Rascunho" : alvo.status === "ativa" ? "Publicada em uso" : "Substituída"}</Badge>
        {payload.isRefreshing && <span className="text-xs text-muted-foreground">Atualizando…</span>}
      </div>
      {payload.showSkeleton ? (
        <StudioLoading rows={3} />
      ) : payload.isError ? (
        <RestrictedNotice error={payload.error} />
      ) : payload.data ? (
        <PayloadView
          agentKey={agentKey}
          hash={payload.data.hash}
          texto={payload.data.texto}
          tokens={payload.data.tokens_estimados}
          manifest={payload.data.manifest}
          avisos={payload.data.avisos}
        />
      ) : null}
    </section>
  );
}

function ParaAOrg({ agentKey, podeRascunho }: { agentKey: string; podeRascunho: boolean }) {
  const [params, setParams] = useSearchParams();
  const versao = podeRascunho && params.get("orgv") === "rascunho" ? "rascunho" : "ativa";
  const q = useCompiladoOrg(agentKey, versao);
  return (
    <section className="space-y-3" data-testid="compilado-org">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-sm font-semibold">Compilado para esta organização</h2>
        {podeRascunho && (
          <select
            aria-label="Versão para a organização"
            className="h-9 rounded-md border border-input bg-background px-2 text-sm"
            value={versao}
            onChange={(e) => setParams({ tab: "compilado", orgv: e.target.value })}
          >
            <option value="ativa">Publicada</option>
            <option value="rascunho">Rascunho</option>
          </select>
        )}
        {q.data && <Badge variant="outline">v{q.data.versao}</Badge>}
        {q.data && !q.data.completo && <Badge variant="outline">Incompleto</Badge>}
        {q.isRefreshing && <span className="text-xs text-muted-foreground">Atualizando…</span>}
      </div>
      {q.showSkeleton ? (
        <StudioLoading rows={3} />
      ) : q.isError ? (
        <RestrictedNotice error={q.error} />
      ) : q.data ? (
        <PayloadView
          agentKey={agentKey}
          hash={q.data.hash}
          texto={q.data.texto}
          tokens={q.data.tokens_estimados}
          manifest={q.data.manifest}
          avisos={q.data.avisos}
          faltando={q.data.specs_faltando}
        />
      ) : null}
    </section>
  );
}

export default function CompiladoJuliaTab({ agentKey }: { agentKey: string }) {
  const agent = useStudioAgent(agentKey);
  const tier = studioTier(agent.data);
  return (
    <div className="space-y-8" data-testid="compilado-julia-tab">
      {tier === "plataforma" && <PorVersao agentKey={agentKey} />}
      <ParaAOrg agentKey={agentKey} podeRascunho={tier === "plataforma"} />
    </div>
  );
}
