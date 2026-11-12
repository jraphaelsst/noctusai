/**
 * "Pronto para publicar" checklist: header verdict + items grouped by `grupo` with severity icons and the
 * suggested action. `ProntidaoPanel` reads the server; `ProntidaoLista` renders any `Prontidao` (the
 * publish 409 can carry one). A failed read shows an error, never a silent "pronto".
 */
import { AlertTriangle, CheckCircle2, XCircle } from "lucide-react";
import { Badge } from "@noctusai/lib/design-system";
import { StudioError, StudioLoading } from "@/components/studio/StudioStates";
import { ProntidaoAcao, acaoDoItem } from "@/components/studio/ProntidaoAcao";
import { useProntidao } from "@/hooks/studio/useProntidao";
import {
  PRONTIDAO_GRUPO_LABEL,
  type CamadaBase,
  type Prontidao,
  type ProntidaoGrupo,
  type ProntidaoItem,
  type ProntidaoSeveridade,
} from "@/api/studio/types-prontidao";

const ICON: Record<ProntidaoSeveridade, React.ReactNode> = {
  bloqueante: <XCircle className="h-4 w-4 shrink-0 text-destructive" aria-label="Bloqueante" />,
  aviso: <AlertTriangle className="h-4 w-4 shrink-0 text-amber-600" aria-label="Aviso" />,
  ok: <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-600" aria-label="Ok" />,
};

/** "Base: agente-base ✓ validada (v3)" / "✗ não validada — 2 casos críticos pendentes" for the chain-gate items. */
export function linhaDaBase(c: CamadaBase): string {
  const v = c.versao != null ? ` (v${c.versao})` : "";
  if (c.validada) return `Base: ${c.agent_key} ✓ validada${v}`;
  const porque =
    c.motivo === "sem_versao" ? "sem versão" :
    c.motivo === "sem_casos" ? "sem casos de avaliação" :
    c.motivo === "sem_medicao" ? "não medida" :
    `${c.criticos_pendentes.length} ${c.criticos_pendentes.length === 1 ? "caso crítico pendente" : "casos críticos pendentes"}`;
  return `Base: ${c.agent_key} ✗ não validada — ${porque}`;
}

function camadasDoItem(i: ProntidaoItem): CamadaBase[] {
  const c = i.detalhe?.camadas;
  return i.codigo.startsWith("base_") && Array.isArray(c) ? (c as CamadaBase[]) : [];
}

export function contarBloqueantes(p: Prontidao): number {
  return p.itens.filter((i) => i.severidade === "bloqueante").length;
}

export function ProntidaoLista({ prontidao, agentKey }: { prontidao: Prontidao; agentKey?: string }) {
  const n = contarBloqueantes(prontidao);
  const pronto = prontidao.pronto_para_publicar && n === 0;
  const grupos = new Map<ProntidaoGrupo, ProntidaoItem[]>();
  for (const i of prontidao.itens) grupos.set(i.grupo, [...(grupos.get(i.grupo) ?? []), i]);
  return (
    <div className="space-y-3" data-testid="prontidao-lista">
      <p
        className={`flex items-center gap-2 text-sm font-semibold ${pronto ? "text-emerald-700" : "text-destructive"}`}
        data-testid="prontidao-titulo"
      >
        {pronto ? <CheckCircle2 className="h-4 w-4" /> : <XCircle className="h-4 w-4" />}
        {pronto ? "Pronto para publicar" : `Faltam ${n} ${n === 1 ? "item bloqueante" : "itens bloqueantes"}`}
      </p>
      {prontidao.itens.length === 0 ? (
        <p className="text-xs text-muted-foreground">Nenhum item verificado.</p>
      ) : (
        [...grupos.entries()].map(([grupo, itens]) => (
          <div key={grupo} data-testid={`prontidao-grupo-${grupo}`}>
            <p className="mb-1 flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
              {PRONTIDAO_GRUPO_LABEL[grupo] ?? grupo}
              {itens.some((i) => i.severidade === "bloqueante") && <Badge variant="destructive">bloqueante</Badge>}
            </p>
            <ul className="space-y-1">
              {itens.map((i) => (
                <li key={`${i.codigo}-${i.mensagem}`} className="flex items-start gap-2 text-sm" data-testid={`prontidao-item-${i.codigo}`}>
                  {ICON[i.severidade]}
                  <div>
                    {i.mensagem}
                    {camadasDoItem(i).map((c) => (
                      <span key={c.agent_key} className="block text-xs text-muted-foreground" data-testid={`prontidao-base-${c.agent_key}`}>
                        {linhaDaBase(c)}
                      </span>
                    ))}
                    {agentKey && acaoDoItem(i.codigo) ? (
                      <ProntidaoAcao codigo={i.codigo} agentKey={agentKey} />
                    ) : (
                      i.acao_sugerida && (
                      <span className="block text-xs text-muted-foreground" data-testid={`prontidao-acao-${i.codigo}`}>
                        {i.acao_sugerida}
                      </span>
                      )
                    )}
                  </div>
                </li>
              ))}
            </ul>
          </div>
        ))
      )}
    </div>
  );
}

export function ProntidaoPanel({ agentKey, override }: { agentKey: string; override?: Prontidao | null }) {
  const q = useProntidao(agentKey);
  const prontidao = override ?? q.data;
  return (
    <section className="space-y-2 rounded-lg border border-border bg-card p-4" data-testid="prontidao-panel">
      <div className="flex items-center gap-2">
        <h2 className="text-sm font-semibold">Prontidão para publicar</h2>
        {q.isRefreshing && <span className="text-xs text-muted-foreground">Atualizando…</span>}
      </div>
      {!override && q.showSkeleton ? (
        <StudioLoading rows={3} testId="prontidao-skeleton" />
      ) : !prontidao && q.isError ? (
        <StudioError error={q.error} onRetry={q.refetch} />
      ) : prontidao ? (
        <>
          <ProntidaoLista prontidao={prontidao} agentKey={agentKey} />
          {q.isError && <p className="text-xs text-destructive">Não foi possível atualizar a checklist.</p>}
        </>
      ) : null}
    </section>
  );
}
