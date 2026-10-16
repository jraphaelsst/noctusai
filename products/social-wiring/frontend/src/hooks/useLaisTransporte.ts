/**
 * Shared Cloud-API transport state for the Lais wave-12 pages (contract §14).
 *
 * Dispatch/approval endpoints answer 409 `transporte_indisponivel` until the
 * connection uses the official API. List responses carry
 * `meta.transporte` ("waha" | "cloud"); anything but "cloud" disables send.
 */
import { mensagemErroLais } from "@/hooks/useLaisAgente";

export type Transporte = "waha" | "cloud";

export const TRANSPORTE_BADGE = "Aguardando verificação da Meta";
export const TRANSPORTE_EXPLICACAO =
  "O envio em massa só é liberado após a verificação da Meta (API oficial). Você já pode criar, salvar e agendar.";
export const TRANSPORTE_INDISPONIVEL = "transporte_indisponivel";

export function codigoErroTransporte(err: unknown): string | null {
  const c = (err as { body?: { error?: { code?: unknown } } } | null | undefined)?.body?.error?.code;
  return typeof c === "string" ? c : null;
}

export function transporteIndisponivel(err: unknown): boolean {
  return codigoErroTransporte(err) === TRANSPORTE_INDISPONIVEL;
}

export function mensagemErroTransporte(err: unknown, fallback: string): string {
  if (transporteIndisponivel(err)) return TRANSPORTE_EXPLICACAO;
  return mensagemErroLais(err, fallback);
}

export function envioLiberado(transporte: Transporte | undefined): boolean {
  return transporte === "cloud";
}
