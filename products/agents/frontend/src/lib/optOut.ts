/** Display helpers of a lead opt-out event (shared by the Opt-outs page and the thread banner). */
import type { OptOutEvento } from "@/api/studio/types-julia";

/** The backend's default when nobody gave a reason (`OPT_OUT_MOTIVO_PADRAO`). */
const MOTIVO_NAO_INFORMADO = "nao_informado";

export function optOutQuem(ev: Pick<OptOutEvento, "origem" | "agent_nome" | "agent_key">): string {
  if (ev.origem === "agente") return `Agente ${ev.agent_nome ?? ev.agent_key ?? "(não identificado)"}`;
  if (ev.origem === "operador") return "Operador";
  if (ev.origem === "integracao") return "Integração";
  return ev.origem;
}

export function optOutMotivo(ev: Pick<OptOutEvento, "motivo">): string {
  return ev.motivo === MOTIVO_NAO_INFORMADO ? "motivo não informado" : ev.motivo;
}

export function optOutData(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}

/** The page + highlighted record the banner and the notification bell link to. */
export function optOutLink(eventoId: string): string {
  return `/opt-outs?evento=${encodeURIComponent(eventoId)}`;
}
