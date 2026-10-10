import type { ExtracaoTipo, ExtractionStatus } from "@/hooks/usePesquisaExtracao";

/** Compact K/M metric; null renders "—" (never 0). */
export function formatMetrica(n: number | null | undefined): string {
  if (n == null) return "—";
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1).replace(/\.0$/, "")}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1).replace(/\.0$/, "")}K`;
  return String(n);
}

/** dd/mm/aaaa from an ISO string (date part only, no timezone shift). */
export function formatData(iso: string | null | undefined): string {
  if (!iso) return "—";
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  return m ? `${m[3]}/${m[2]}/${m[1]}` : "—";
}

export const TIPO_ROTULO: Record<ExtracaoTipo, string> = {
  pesquisa: "Itens de pesquisa",
  assuntos_virais: "Assuntos virais",
};

export const STATUS_ROTULO: Record<ExtractionStatus, string> = {
  queued: "Na fila",
  running: "Em andamento",
  completed: "Concluída",
  completed_with_errors: "Concluída com avisos",
  failed: "Falhou",
  cancelled: "Cancelada",
};
