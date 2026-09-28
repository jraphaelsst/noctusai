/**
 * The orçamento's live totals — the SERVER's numbers from
 * `POST /api/orcamentos/calcular`, never recomputed here.
 *
 * Margem estimada is a badge, coloured by how safe the price is: a total that
 * barely covers the team's custo/hora is the calculator's whole point, so the
 * warning sits next to the total, not in a footnote.
 */
import { AlertTriangle, Loader2 } from "lucide-react";
import { cn } from "@noctusai/lib";

import { brl, pct } from "@/lib/format";
import type { Totais } from "@/types/crm";

export type MargemNivel = "baixa" | "media" | "boa" | "indisponivel";

/** < 20% baixa · 20–40% média · ≥ 40% boa · `null` (total zero, ou nenhum
 * profissional com custo/hora) = indisponível — NUNCA lida como "0%" nem
 * "100% saudável" (achado 1/5). */
export function nivelDaMargem(margem: number | null): MargemNivel {
  if (margem == null) return "indisponivel";
  if (margem < 20) return "baixa";
  if (margem < 40) return "media";
  return "boa";
}

const MARGEM_CLASSE: Record<MargemNivel, string> = {
  baixa: "border-destructive/40 bg-destructive/10 text-destructive",
  media: "border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-400",
  boa: "border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400",
  indisponivel: "border-border bg-muted text-muted-foreground",
};

const MARGEM_ROTULO: Record<MargemNivel, string> = {
  baixa: "Margem baixa",
  media: "Margem média",
  boa: "Margem saudável",
  indisponivel: "Margem indisponível",
};

export function MargemBadge({ margem }: { margem: number | null }) {
  const nivel = nivelDaMargem(margem);
  return (
    <span
      data-testid="margem-badge"
      data-nivel={nivel}
      className={cn("inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium", MARGEM_CLASSE[nivel])}
    >
      {MARGEM_ROTULO[nivel]}
      {nivel === "indisponivel" ? "" : ` · ${pct(margem)}`}
    </span>
  );
}

export interface TotaisPanelProps {
  totais: Totais | null;
  /** A newer calculation is in flight over the totals shown. */
  refreshing?: boolean;
  error?: string | null;
  /** No items yet — nothing to calculate. */
  vazio?: boolean;
  /** `/calcular`'s warnings (e.g. "nenhum profissional com custo/hora
   * definido") — only available on the LIVE preview, never on a saved
   * orçamento's stored totals. The screen used to compute this silently
   * (achado 1): a confident "Margem saudável · 100%" with no rates cadastered
   * at all. */
  alertas?: string[];
}

export function TotaisPanel({ totais, refreshing, error, vazio, alertas }: TotaisPanelProps) {
  return (
    <section
      aria-label="Totais do orçamento"
      className="rounded-xl border border-border bg-muted/30 p-4"
      data-testid="totais-panel"
    >
      <div className="mb-3 flex items-center justify-between gap-2">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Totais</h3>
        {refreshing ? (
          <Loader2 aria-label="Recalculando" className="h-3.5 w-3.5 animate-spin text-muted-foreground" />
        ) : null}
      </div>

      {error ? (
        <p role="alert" className="text-sm text-destructive">{error}</p>
      ) : vazio || !totais ? (
        <p className="text-sm text-muted-foreground">
          {vazio ? "Adicione itens para calcular o orçamento." : "Calculando…"}
        </p>
      ) : (
        <>
          <dl className="space-y-1.5 text-sm">
            <Linha rotulo="Criação de conteúdo" valor={brl(totais.subtotal_criacao)} testId="total-criacao" />
            <Linha rotulo="Gestão de conta" valor={brl(totais.subtotal_gestao)} testId="total-gestao" />
            {totais.desconto > 0 ? (
              <Linha rotulo="Desconto" valor={`− ${brl(totais.desconto)}`} testId="total-desconto" />
            ) : null}
          </dl>
          <div className="mt-3 flex flex-wrap items-end justify-between gap-2 border-t border-border pt-3">
            <div>
              <p className="text-xs text-muted-foreground">Total mensal</p>
              <p className="text-2xl font-semibold tabular-nums text-foreground" data-testid="total-mensal">
                {brl(totais.total_mensal)}
              </p>
            </div>
            <MargemBadge margem={totais.margem_estimada} />
          </div>
          <p className="mt-2 text-xs text-muted-foreground" data-testid="total-custo">
            Custo estimado {brl(totais.custo_estimado)} ·{" "}
            {totais.horas_estimadas.toLocaleString("pt-BR", { maximumFractionDigits: 1 })} h/mês
          </p>
          {alertas && alertas.length > 0 ? (
            <ul className="mt-3 space-y-1" data-testid="totais-alertas">
              {alertas.map((a) => (
                <li
                  key={a}
                  role="alert"
                  className="flex items-start gap-1.5 rounded-md border border-amber-500/40 bg-amber-500/10 p-2 text-xs text-amber-800 dark:text-amber-300"
                >
                  <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                  {a}
                </li>
              ))}
            </ul>
          ) : null}
        </>
      )}
    </section>
  );
}

function Linha({ rotulo, valor, testId }: { rotulo: string; valor: string; testId: string }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <dt className="text-muted-foreground">{rotulo}</dt>
      <dd className="tabular-nums text-foreground" data-testid={testId}>{valor}</dd>
    </div>
  );
}
