/**
 * Agent Studio — "Prompt compilado", the inspector (CONTRACT §G, §C, §A4).
 *
 * Shows EXACTLY what the runtime sends: the server-compiled `texto`, cut into
 * labelled blocks by the manifest offsets (each block links to the tab that
 * edits its source), with the hash, token totals, per-section token bar,
 * compile warnings, the just-in-time "Camada sob demanda", a
 * "Comparar com publicada" diff (the §D1 diff endpoint) and copy-to-clipboard.
 *
 * Selectors live in the URL: `?versao=<vid>` (default: draft, else ativa) and
 * `?cliente=<client id>` (optional client brain → `# Cliente em foco`).
 */
import { useRef } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { AlertTriangle, Layers } from "lucide-react";
import { Badge, EmptyState } from "@noctusai/lib/design-system";
import type { OnDemandItem } from "@/api/studio/types";
import { CompiledPromptView, type CompiledPromptViewHandle } from "@/components/studio/CompiledPromptView";
import { CopyTextButton } from "@/components/studio/CopyTextButton";
import { SectionTokenBar } from "@/components/studio/SectionTokenBar";
import { StudioError, StudioLoading } from "@/components/studio/StudioStates";
import { VersionDiffSummary } from "@/components/studio/VersionDiffSummary";
import { shortHash, type SourceTarget } from "@/components/studio/compiledSegments";
import { VersionStatusBadge } from "@/components/studio/VersionStatusBadge";
import { useClients } from "@/hooks/studio/useClients";
import { useCompiled } from "@/hooks/studio/useCompiled";
import { useAgentVersionRefs, useVersionDiff } from "@/hooks/studio/useVersions";
import { studioTabHref } from "../studioTabs";

const SELECT_CLASS =
  "h-9 rounded-md border border-input bg-background px-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/50";

const TIPO_LABEL: Record<OnDemandItem["tipo"], string> = {
  skill: "Skill",
  arquivo_skill: "Arquivo de skill",
  colecao: "Coleção",
};

export default function CompiledTab({ agentKey }: { agentKey: string }) {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const refs = useAgentVersionRefs(agentKey);
  const clients = useClients(agentKey);
  const viewRef = useRef<CompiledPromptViewHandle>(null);

  const versoes = refs.data?.versoes ?? [];
  const requested = params.get("versao");
  const selected = versoes.find((v) => v.id === requested) ?? refs.draft ?? refs.ativa ?? versoes[0] ?? null;
  const clientId = params.get("cliente") || null;
  const comparar = params.get("comparar") === "1";
  const canCompare = !!refs.ativa && !!selected && selected.id !== refs.ativa.id;

  const compiled = useCompiled(agentKey, selected?.id, clientId);
  const diff = useVersionDiff(agentKey, comparar && canCompare ? refs.ativa!.id : null, comparar && canCompare ? selected!.id : null);

  function setParam(name: string, value: string | null) {
    const next = new URLSearchParams(params);
    if (value) next.set(name, value);
    else next.delete(name);
    setParams(next);
  }

  function openSource(target: SourceTarget) {
    navigate(studioTabHref(agentKey, target.tab, target.params));
  }

  if (refs.showSkeleton) return <StudioLoading rows={4} />;
  if (refs.isError) return <StudioError error={refs.error} onRetry={refs.refetch} />;
  if (!selected) return <EmptyState message="Este agente ainda não tem versões para compilar." />;

  const data = compiled.data;
  const bloqueantes = data?.avisos.filter((a) => a.bloqueante) ?? [];
  const avisos = data?.avisos.filter((a) => !a.bloqueante) ?? [];
  const activeClients = (clients.data ?? []).filter((c) => c.ativo || c.id === clientId);

  return (
    <div className="space-y-4" data-testid="compiled-tab">
      {/* Selectors */}
      <div className="flex flex-wrap items-center gap-2">
        <select
          aria-label="Versão"
          className={SELECT_CLASS}
          value={selected.id}
          onChange={(e) => setParam("versao", e.target.value)}
          data-testid="compiled-version-select"
        >
          {versoes.map((v) => (
            <option key={v.id} value={v.id}>
              v{v.versao} · {v.status}
            </option>
          ))}
        </select>
        <select
          aria-label="Cliente"
          className={SELECT_CLASS}
          value={clientId ?? ""}
          onChange={(e) => setParam("cliente", e.target.value || null)}
          disabled={clients.showSkeleton || clients.isError}
          data-testid="compiled-client-select"
        >
          <option value="">Sem cliente</option>
          {activeClients.map((c) => (
            <option key={c.id} value={c.id}>
              {c.nome}
            </option>
          ))}
        </select>
        {clients.isError && <span className="text-xs text-destructive">Clientes indisponíveis.</span>}
        {canCompare && (
          <label className="flex items-center gap-1.5 text-sm">
            <input
              type="checkbox"
              checked={comparar}
              onChange={(e) => setParam("comparar", e.target.checked ? "1" : null)}
              data-testid="compiled-compare-toggle"
            />
            Comparar com publicada (v{refs.ativa!.versao})
          </label>
        )}
        {compiled.isRefreshing && <span className="text-xs text-muted-foreground">Recompilando…</span>}
        {data && (
          <div className="ml-auto">
            <CopyTextButton text={data.texto} label="Copiar prompt" />
          </div>
        )}
      </div>

      {compiled.showSkeleton ? (
        <StudioLoading rows={5} testId="compiled-skeleton" />
      ) : compiled.isError ? (
        <StudioError error={compiled.error} onRetry={compiled.refetch} />
      ) : !data ? null : (
        <>
          {/* Header */}
          <div className="space-y-3 rounded-lg border border-border bg-card p-4" data-testid="compiled-header">
            <div className="flex flex-wrap items-center gap-3">
              <VersionStatusBadge status={selected.status} />
              <span className="text-sm font-semibold">v{selected.versao}</span>
              <span className="font-mono text-xs" title={data.hash} data-testid="compiled-hash">
                {shortHash(data.hash, 16)}
              </span>
              <span className="text-sm tabular-nums" data-testid="compiled-tokens">
                ~{data.tokens_estimados.toLocaleString("pt-BR")} tokens
              </span>
              <span className="text-xs tabular-nums text-muted-foreground">
                {data.texto.length.toLocaleString("pt-BR")} caracteres · {data.manifest.length} blocos
              </span>
              {data.client_id && <Badge variant="outline">Com cliente em foco</Badge>}
            </div>
            <SectionTokenBar manifest={data.manifest} onSelect={(i) => viewRef.current?.scrollToSection(i)} />
          </div>

          {/* Warnings */}
          {(bloqueantes.length > 0 || avisos.length > 0) && (
            <div className="space-y-1 rounded-lg border border-amber-500/40 bg-amber-500/5 p-3" data-testid="compiled-avisos">
              <p className="flex items-center gap-1 text-sm font-medium">
                <AlertTriangle className="h-4 w-4 text-amber-600" /> Avisos de compilação
              </p>
              <ul className="space-y-1 text-xs">
                {[...bloqueantes, ...avisos].map((a, i) => (
                  <li key={`${a.codigo}-${i}`} className="flex items-start gap-2">
                    <Badge variant={a.bloqueante ? "destructive" : "outline"}>{a.bloqueante ? "bloqueia publicação" : "aviso"}</Badge>
                    <span>{a.mensagem}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Compare with published */}
          {comparar && canCompare && (
            <section className="rounded-lg border border-border bg-card p-4" data-testid="compiled-compare">
              <h3 className="mb-2 text-sm font-semibold">
                Publicada v{refs.ativa!.versao} → v{selected.versao}
                {clientId && <span className="ml-2 text-xs font-normal text-muted-foreground">(comparação sem cliente)</span>}
              </h3>
              {diff.showSkeleton ? (
                <StudioLoading rows={2} />
              ) : diff.isError ? (
                <StudioError error={diff.error} onRetry={diff.refetch} />
              ) : diff.data ? (
                <VersionDiffSummary diff={diff.data} rotuloA={`v${refs.ativa!.versao} (ativa)`} rotuloB={`v${selected.versao}`} />
              ) : null}
            </section>
          )}

          <div className="grid gap-4 xl:grid-cols-[1fr_320px]">
            <CompiledPromptView
              ref={viewRef}
              texto={data.texto}
              manifest={data.manifest}
              clientId={data.client_id}
              onOpenSource={openSource}
            />

            {/* On-demand layer */}
            <aside className="space-y-2" data-testid="compiled-sob-demanda">
              <h3 className="flex items-center gap-1.5 text-sm font-semibold">
                <Layers className="h-4 w-4 text-primary" /> Camada sob demanda
              </h3>
              <p className="text-xs text-muted-foreground">
                Não entra no prompt: o agente carrega estes itens pelas ferramentas quando precisa.
              </p>
              {data.sob_demanda.length === 0 ? (
                <p className="text-xs text-muted-foreground">Nada sob demanda nesta versão.</p>
              ) : (
                <ul className="divide-y divide-border rounded-lg border border-border bg-card">
                  {data.sob_demanda.map((item, i) => (
                    <li key={`${item.tipo}-${item.nome}-${item.caminho ?? ""}-${i}`} className="space-y-0.5 px-3 py-2" data-testid="sob-demanda-item">
                      <div className="flex items-center gap-2">
                        <Badge variant="muted">{TIPO_LABEL[item.tipo] ?? item.tipo}</Badge>
                        <span className="font-mono text-xs">{item.nome}</span>
                      </div>
                      {item.caminho && <p className="font-mono text-[11px] text-muted-foreground">{item.caminho}</p>}
                      <p className="text-[11px] text-muted-foreground">
                        {item.chars.toLocaleString("pt-BR")} caracteres · ~{item.tokens.toLocaleString("pt-BR")} tokens
                      </p>
                      <p className="text-[11px]">
                        Gatilho: <span className="font-mono">{item.gatilho}</span>
                      </p>
                    </li>
                  ))}
                </ul>
              )}
            </aside>
          </div>
        </>
      )}
    </div>
  );
}
