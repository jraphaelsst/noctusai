/** Display helpers shared by the esteira card face and detail sheet. */
import { isoLocal } from "@/components/calendario/grade";

/** `prazo` is a date (`YYYY-MM-DD`) — compare as local dates, never via UTC. */
export function prazoVencido(prazo: string | null, hoje: Date = new Date()): boolean {
  if (!prazo) return false;
  return prazo.slice(0, 10) < isoLocal(hoje);
}

/** `2026-09-23` → `23/09/26`. */
export function formatarPrazo(prazo: string): string {
  const [ano, mes, dia] = prazo.slice(0, 10).split("-");
  return `${dia}/${mes}/${ano.slice(2)}`;
}

/** Minutes → `1h05` / `40 min`. */
export function formatarMinutos(total: number): string {
  const h = Math.floor(total / 60);
  const m = total % 60;
  return h > 0 ? `${h}h${String(m).padStart(2, "0")}` : `${m} min`;
}

/**
 * A pauta option's label for a picker — title alone (the old shape) leaves
 * auto-generated pautas ("Post feed (1/2)") indistinguishable across days
 * (achado 12). Shared by "Nova tarefa" and the tarefa detail's pauta editor.
 */
export function rotuloPauta(
  pauta: { titulo: string; data_publicacao: string | null },
  clienteNome?: string,
): string {
  const data = pauta.data_publicacao
    ? new Date(pauta.data_publicacao).toLocaleDateString("pt-BR")
    : "sem data";
  return `${pauta.titulo} — ${data}${clienteNome ? ` — ${clienteNome}` : ""}`;
}
