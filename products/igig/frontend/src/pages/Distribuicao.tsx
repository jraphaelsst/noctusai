/**
 * Distribuição e Métricas — Módulo 5.
 *
 * Two halves: the publishing queue, and the BI de eficiência.
 *
 * The BI table is where the care went, because these are numbers the agency
 * bills against:
 *   - `alertas` render as a visible warning row, never a tooltip. When some
 *     hours could not be costed the total is UNDERSTATED, and a reader who
 *     misses that draws the wrong conclusion about margin.
 *   - a failed publication shows its `erro` inline rather than a generic
 *     "falhou", so the operator knows whether to retry or fix credentials.
 */
import { Fragment } from "react";
import { Badge, Button, Skeleton } from "@noctusai/lib/design-system";
import type { BadgeVariant } from "@noctusai/lib/design-system";
import { AlertTriangle, Ban, Send } from "lucide-react";

import {
  useCancelarPublicacao,
  useEficiencia,
  useExecutarPublicacao,
  usePublicacoes,
  type StatusPublicacao,
} from "@/hooks/useDistribuicao";

const STATUS_VARIANT: Record<StatusPublicacao, BadgeVariant> = {
  agendada: "muted",
  publicando: "muted",
  publicada: "default",
  falhou: "destructive",
  cancelada: "outline",
};

const BRL = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });

export default function Distribuicao() {
  const { publicacoes, loading: carregandoPubs } = usePublicacoes();
  const { linhas, loading: carregandoBI } = useEficiencia();
  const executar = useExecutarPublicacao();
  const cancelar = useCancelarPublicacao();

  return (
    <div className="space-y-6 p-6">
      <header>
        <h1 className="text-2xl font-semibold text-foreground">Distribuição e Métricas</h1>
        <p className="text-sm text-muted-foreground">
          Fila de publicação e eficiência por cliente.
        </p>
      </header>

      {/* ── BI de eficiência ───────────────────────────────────────── */}
      <section className="rounded-lg border border-border bg-card p-4">
        <h2 className="mb-3 text-sm font-semibold text-foreground">BI de Eficiência</h2>
        {carregandoBI ? (
          <Skeleton className="h-24 w-full" />
        ) : linhas.length === 0 ? (
          <p className="text-sm text-muted-foreground">Nenhum cliente ainda.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wide text-muted-foreground">
                  <th className="py-2">Cliente</th>
                  <th className="py-2 text-right">Tarefas</th>
                  <th className="py-2 text-right">Refações</th>
                  <th className="py-2 text-right">Taxa</th>
                  <th className="py-2 text-right">Horas</th>
                  <th className="py-2 text-right">Custo real</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {linhas.map((linha) => (
                  // Fragment carries the key — a bare <> inside .map() leaves
                  // React without a stable identity for the row pair.
                  <Fragment key={linha.cliente_id}>
                    <tr>
                      <td className="py-2 text-foreground">{linha.cliente_nome}</td>
                      <td className="py-2 text-right text-foreground">{linha.tarefas}</td>
                      <td className="py-2 text-right text-foreground">{linha.refacoes}</td>
                      <td className="py-2 text-right text-foreground">
                        {linha.taxa_refacao.toFixed(2)}
                      </td>
                      <td className="py-2 text-right text-foreground">{linha.horas}</td>
                      <td className="py-2 text-right text-foreground">
                        {BRL.format(linha.custo_reais)}
                      </td>
                    </tr>
                    {/* A visible row, not a tooltip — an understated cost that
                        looks precise is worse than one that says so. */}
                    {linha.alertas.length > 0 && (
                      <tr>
                        <td colSpan={6} className="pb-2 text-xs text-destructive">
                          <AlertTriangle className="mr-1 inline h-3 w-3" />
                          {linha.alertas.join(" · ")}
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* ── Fila de publicação ─────────────────────────────────────── */}
      <section className="rounded-lg border border-border bg-card p-4">
        <h2 className="mb-3 text-sm font-semibold text-foreground">Publicações</h2>
        {carregandoPubs ? (
          <Skeleton className="h-24 w-full" />
        ) : publicacoes.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Nenhuma publicação agendada. Agende a partir de uma pauta no calendário.
          </p>
        ) : (
          <ul className="divide-y divide-border">
            {publicacoes.map((pub) => (
              <li key={pub.id} className="flex flex-wrap items-center gap-3 py-3">
                <Badge variant={STATUS_VARIANT[pub.status]}>{pub.status}</Badge>
                <span className="text-sm text-foreground">{pub.canal}</span>
                <span className="min-w-0 flex-1 truncate text-xs text-muted-foreground">
                  {pub.publicada_em
                    ? `publicada em ${new Date(pub.publicada_em).toLocaleString("pt-BR")}`
                    : pub.agendada_para
                      ? `agendada para ${new Date(pub.agendada_para).toLocaleString("pt-BR")}`
                      : "sem data"}
                  {pub.erro && (
                    <span className="ml-2 text-destructive">
                      {pub.erro} (tentativas: {pub.tentativas})
                    </span>
                  )}
                </span>

                {pub.status !== "publicada" && pub.status !== "cancelada" && (
                  <>
                    <Button
                      size="sm"
                      disabled={executar.isPending}
                      onClick={() => executar.mutate(pub.id)}
                    >
                      <Send className="mr-2 h-3 w-3" />
                      Publicar
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      aria-label="Cancelar publicação"
                      onClick={() => cancelar.mutate(pub.id)}
                    >
                      <Ban className="h-4 w-4" />
                    </Button>
                  </>
                )}

                {pub.permalink && (
                  <a
                    href={pub.permalink}
                    target="_blank"
                    rel="noreferrer"
                    className="text-xs text-foreground underline"
                  >
                    ver post
                  </a>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
