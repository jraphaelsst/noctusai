/** Shared pt-BR labels and limits for the Segundo Cérebro surfaces (contract §6). */
import type { BrainDisplayStatus, ExtractionStatus, ImportStatus } from "@/types/cerebro";

export const STATUS_CEREBRO_ROTULO: Record<BrainDisplayStatus, string> = {
  vazio: "Vazio",
  pronto: "Pronto",
  processando: "Processando",
};

export const STATUS_IMPORT_ROTULO: Record<ImportStatus, string> = {
  processing: "Processando",
  appended: "Anexado",
  error: "Falha",
};

export const STATUS_EXTRACAO_ROTULO: Record<ExtractionStatus, string> = {
  transcribing: "Transcrevendo",
  ready: "Pronta",
  applied: "Aplicada",
  error: "Falha",
};

export const MAX_CONTEUDO = 200_000;
export const MAX_BIO = 5_000;
export const MAX_ARQUIVO_BYTES = 20 * 1024 * 1024;
export const EXTENSOES_ARQUIVO = ["pdf", "docx", "txt", "md", "csv"] as const;

export const MSG_SEM_ARQUIVO = "Selecione um arquivo antes de enviar.";
export const MSG_FORMATO = "Formato não suportado. Use PDF, DOCX, TXT, MD ou CSV.";
export const MSG_GRANDE = "Arquivo muito grande. Limite: 20 MB.";

/** Client-side validation of an import file; null = ok. */
export function validarArquivo(file: File | null): string | null {
  if (!file) return MSG_SEM_ARQUIVO;
  const ext = file.name.includes(".") ? file.name.split(".").pop()!.toLowerCase() : "";
  if (!(EXTENSOES_ARQUIVO as readonly string[]).includes(ext)) return MSG_FORMATO;
  if (file.size > MAX_ARQUIVO_BYTES) return MSG_GRANDE;
  return null;
}

export function formatarChars(n: number): string {
  return `${n.toLocaleString("pt-BR")} caracteres`;
}

export function mensagemErro(e: unknown, fallback: string): string {
  const msg = e instanceof Error ? e.message : "";
  // ApiError prefixes "[status] "; keep the server's pt-BR detail only.
  return msg.replace(/^\[\d+\]\s*/, "") || fallback;
}

/** HTTP status carried by an ApiError (or parsed from its "[status] " prefix); null if none. */
export function statusDe(e: unknown): number | null {
  const s = (e as { status?: unknown } | null)?.status;
  if (typeof s === "number") return s;
  const m = e instanceof Error ? /^\[(\d+)\]/.exec(e.message) : null;
  return m ? Number(m[1]) : null;
}
