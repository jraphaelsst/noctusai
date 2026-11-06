/** One conversation's cost / speed / size: its summary and its turns (oldest first). Platform admin only. */
import { X } from "lucide-react";
import { Button, EmptyState } from "@noctusai/lib/design-system";
import { StudioError, StudioLoading } from "@/components/studio/StudioStates";
import { RestrictedNotice } from "@/components/studio/ConteudoChrome";
import { useMetricasThread } from "@/hooks/studio/useMetricas";
import type { MetricasOrigem } from "@/api/studio/types-metricas";
import { fmtBytes, fmtInt, fmtMs, fmtShare, fmtUsd, media } from "@/lib/metricasFormat";
import { TurnosTabela, idCurto } from "./MetricasTurnos";

export default function MetricasThread({
  agentKey,
  threadId,
  origem,
  onFechar,
}: {
  agentKey: string;
  threadId: string;
  origem: MetricasOrigem;
  onFechar: () => void;
}) {
  const q = useMetricasThread(agentKey, threadId, origem);
  const r = q.data?.resumo;
  return (
    <section className="space-y-3 rounded-lg border border-border bg-card p-4" data-testid="metricas-thread" aria-label={`Conversa ${idCurto(threadId)}`}>
      <div className="flex items-center gap-3">
        <h2 className="text-sm font-semibold">
          Conversa <span className="font-mono">{idCurto(threadId)}</span>
        </h2>
        {q.isRefreshing && <span className="text-xs text-muted-foreground">Atualizando…</span>}
        <Button size="sm" variant="outline" className="ml-auto" onClick={onFechar}>
          <X className="mr-1 h-3.5 w-3.5" /> Fechar
        </Button>
      </div>
      {q.showSkeleton ? (
        <StudioLoading rows={2} testId="metricas-thread-loading" />
      ) : q.isError ? (
        (q.error as { status?: number }).status === 403 ? <RestrictedNotice error={q.error} /> : <StudioError error={q.error} onRetry={q.refetch} />
      ) : q.data && r ? (
        <>
          {q.data.truncado && (
            <p className="text-xs text-muted-foreground" role="status" data-testid="metricas-thread-truncado">
              Há mais turnos do que o limite de leitura; os números cobrem apenas os mais recentes.
            </p>
          )}
          {q.data.turnos.length === 0 ? (
            <EmptyState message="Nenhum turno medido nesta conversa." />
          ) : (
            <>
              <dl className="grid grid-cols-2 gap-x-6 gap-y-1 text-sm sm:grid-cols-4" data-testid="metricas-thread-resumo">
                <Item k="Turnos" v={fmtInt(r.turnos)} />
                <Item k="Custo total" v={fmtUsd(r.custo_usd)} />
                <Item k="Custo por turno" v={fmtUsd(r.custo_por_turno_usd, 4)} />
                <Item k="Cache lido" v={fmtShare(r.cache_leitura_share)} />
                <Item k="Turno p50 / p95" v={`${fmtMs(r.turno_ms_p50)} / ${fmtMs(r.turno_ms_p95)}`} />
                <Item k="LLM p50 / p95" v={`${fmtMs(r.llm_ms_p50)} / ${fmtMs(r.llm_ms_p95)}`} />
                <Item k="Bytes recebidos / resposta" v={`${fmtBytes(r.inbound_bytes)} / ${fmtBytes(r.reply_bytes)}`} />
                <Item k="Tokens médios ent./saí." v={`${fmtInt(media(r.tokens_entrada, r.turnos))} / ${fmtInt(media(r.tokens_saida, r.turnos))}`} />
              </dl>
              <TurnosTabela turnos={q.data.turnos} detalhes testId="metricas-thread-turnos" />
            </>
          )}
        </>
      ) : null}
    </section>
  );
}

function Item({ k, v }: { k: string; v: string }) {
  return (
    <div>
      <dt className="text-xs text-muted-foreground">{k}</dt>
      <dd className="tabular-nums">{v}</dd>
    </div>
  );
}
