/**
 * Honest batch feedback shared by the form (progress) and the result modal:
 * the warnings the backend reports (few structures, Método fallback, structures
 * that failed) and the real progress block (etapa + counters, never a fake bar).
 */
import { AlertTriangle, Loader2 } from "lucide-react";

import { Progress } from "@/components/ui/progress";
import type { HeadlineLote } from "@/types/geracao";

export function mensagemErro(e: unknown, fallback: string): string {
  const msg = e instanceof Error ? e.message.replace(/^\[\d+\]\s*/, "") : "";
  return msg || fallback;
}

export function alternarEm<T>(lista: T[], valor: T, max?: number): T[] {
  if (lista.includes(valor)) return lista.filter((v) => v !== valor);
  if (max != null && lista.length >= max) return lista;
  return [...lista, valor];
}

type AvisoLote = Pick<
  HeadlineLote,
  "aviso_poucas_estruturas" | "fallback_metodo" | "estruturas_com_erro" | "erro"
>;

export function AvisosLote({ lote }: { lote: AvisoLote }) {
  const avisos: string[] = [];
  if (lote.fallback_metodo) {
    avisos.push("Sem estruturas da biblioteca — usando templates do Método Audience.");
  }
  if (lote.aviso_poucas_estruturas) {
    avisos.push("Poucas estruturas compatíveis com os critérios escolhidos (menos de 3). Amplie os filtros para ter mais variedade.");
  }
  if (lote.estruturas_com_erro > 0) {
    avisos.push(
      lote.estruturas_com_erro === 1
        ? "1 estrutura não pôde ser processada."
        : `${lote.estruturas_com_erro} estruturas não puderam ser processadas.`,
    );
  }
  if (avisos.length === 0 && !lote.erro) return null;
  return (
    <div className="space-y-2" data-testid="avisos-lote">
      {avisos.map((a) => (
        <p
          key={a}
          role="status"
          className="flex items-start gap-2 rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900"
        >
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" /> {a}
        </p>
      ))}
      {lote.erro && (
        <p role="alert" className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
          {lote.erro}
        </p>
      )}
    </div>
  );
}

/** "Processando suas Headlines": the real `etapa` and counters of the running batch. */
export function ProgressoLote({ lote }: { lote: HeadlineLote }) {
  const temContagem = lote.estruturas_total > 0;
  const pct = temContagem ? Math.round((lote.estruturas_processadas / lote.estruturas_total) * 100) : 0;
  return (
    <section aria-live="polite" className="space-y-3 rounded-lg border p-4" data-testid="progresso-lote">
      <h2 className="flex items-center gap-2 text-base font-semibold">
        <Loader2 className="h-4 w-4 animate-spin" /> Processando suas Headlines
      </h2>
      {lote.etapa && <p className="text-sm">{lote.etapa}</p>}
      {temContagem && (
        <div className="space-y-1">
          <Progress value={pct} aria-label="Estruturas processadas" />
          <p className="text-xs text-muted-foreground">
            {lote.estruturas_processadas} de {lote.estruturas_total} estruturas processadas
            {lote.estruturas_com_erro > 0 ? ` · ${lote.estruturas_com_erro} com erro` : ""}
          </p>
        </div>
      )}
      <p className="text-xs text-muted-foreground">Isto pode levar 1–2 minutos.</p>
      <AvisosLote lote={lote} />
    </section>
  );
}
