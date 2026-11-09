/**
 * Turn-metrics building blocks used by the "Métricas" tab and its thread view (agents app only,
 * platform admin). A NULL measurement renders "—" with the reason in a tooltip — never 0.
 */
import type { ReactNode } from "react";
import { Badge, Tooltip, TooltipContent, TooltipTrigger } from "@noctusai/lib/design-system";
import type { MetricasTurno } from "@/api/studio/types-metricas";
import { fmtBytes, fmtInt, fmtMs, fmtShare, fmtUsd } from "@/lib/metricasFormat";

export const dataHora = (iso: string) => new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "medium" });
export const idCurto = (id: string) => id.slice(0, 8);

/** "—" that explains itself (keyboard-focusable so the reason is not hover-only). */
export function Nulo({ motivo }: { motivo: string }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span tabIndex={0} aria-label={`Sem valor. ${motivo}`} className="cursor-help text-muted-foreground">
          —
        </span>
      </TooltipTrigger>
      <TooltipContent>{motivo}</TooltipContent>
    </Tooltip>
  );
}

export const TH = ({ children }: { children: ReactNode }) => <th className="whitespace-nowrap px-3 py-2 font-medium">{children}</th>;
export const TD = ({ children, className = "" }: { children: ReactNode; className?: string }) => (
  <td className={`whitespace-nowrap px-3 py-2 tabular-nums ${className}`}>{children}</td>
);

export function StatusBadge({ t }: { t: MetricasTurno }) {
  if (t.status === "erro")
    return <Badge variant="outline" title={t.erro_classe ?? undefined}>Erro{t.erro_classe ? ` · ${t.erro_classe}` : ""}</Badge>;
  return <Badge variant="muted">{t.handoff ? "Handoff" : (t.turno_status ?? "ok")}</Badge>;
}

export function TurnosTabela({
  turnos,
  onAbrirThread,
  detalhes = false,
  testId = "metricas-turnos",
}: {
  turnos: MetricasTurno[];
  onAbrirThread?: (threadId: string) => void;
  /** Thread view: adds the intake wait and the media size columns. */
  detalhes?: boolean;
  testId?: string;
}) {
  return (
    <div className="overflow-x-auto rounded-lg border border-border bg-card">
      <table className="w-full text-sm" data-testid={testId}>
        <thead className="border-b border-border text-left text-xs text-muted-foreground">
          <tr>
            <TH>Quando</TH>
            <TH>Org</TH>
            <TH>Conversa</TH>
            <TH>Status</TH>
            <TH>Custo</TH>
            <TH>Tokens ent./saí.</TH>
            <TH>Cache</TH>
            <TH>Turno</TH>
            <TH>LLM</TH>
            <TH>Tools</TH>
            {detalhes && <TH>Espera na fila</TH>}
            <TH>Bytes ent./saí.</TH>
            {detalhes && <TH>Mídia</TH>}
            <TH>Ferramentas</TH>
          </tr>
        </thead>
        <tbody>
          {turnos.map((t) => (
            <tr key={t.id} className="border-b border-border last:border-0" data-testid={`turno-${t.id}`}>
              <TD>{dataHora(t.criado_em)}</TD>
              <TD>
                <span title={t.org_id} className="font-mono text-xs">{idCurto(t.org_id)}</span>
              </TD>
              <TD>
                {t.thread_id && onAbrirThread ? (
                  <button
                    type="button"
                    className="font-mono text-xs text-primary underline-offset-2 hover:underline focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
                    aria-label={`Abrir conversa ${idCurto(t.thread_id)}`}
                    onClick={() => onAbrirThread(t.thread_id as string)}
                  >
                    {idCurto(t.thread_id)}
                  </button>
                ) : t.thread_id ? (
                  <span className="font-mono text-xs">{idCurto(t.thread_id)}</span>
                ) : (
                  <Nulo motivo="Turno sem conversa de canal (avaliação)." />
                )}
              </TD>
              <TD><StatusBadge t={t} /></TD>
              <TD>{fmtUsd(t.llm.custo_usd, 4)}</TD>
              <TD>{fmtInt(t.llm.tokens_entrada)} / {fmtInt(t.llm.tokens_saida)}</TD>
              <TD>{t.llm.tokens_entrada > 0 ? fmtShare(t.llm.cache_leitura_share) : <Nulo motivo="Nenhum token de entrada neste turno." />}</TD>
              <TD>{fmtMs(t.velocidade.turno_ms)}</TD>
              <TD>{fmtMs(t.velocidade.llm_ms)}</TD>
              <TD>{fmtMs(t.velocidade.tool_ms)}</TD>
              {detalhes && (
                <TD>{t.velocidade.intake_ms == null ? <Nulo motivo="Não aplicável: avaliações não têm lote de entrada." /> : fmtMs(t.velocidade.intake_ms)}</TD>
              )}
              <TD>{fmtBytes(t.tamanho.inbound_bytes)} / {fmtBytes(t.tamanho.reply_bytes)}</TD>
              {detalhes && (
                <TD>{t.tamanho.media_bytes == null ? <Nulo motivo="Mídia não é armazenada no app de agentes." /> : fmtBytes(t.tamanho.media_bytes)}</TD>
              )}
              <TD className="font-mono text-xs">{t.ferramentas.length ? t.ferramentas.join(", ") : <Nulo motivo="Nenhuma ferramenta chamada neste turno." />}</TD>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
