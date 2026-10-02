/**
 * Pure helpers for one certidão cell of a party — chip label/color,
 * automation eligibility, and the per-party status summary line. Kept out of
 * the components so they are unit-testable without rendering.
 */
import type { CertidaoParte, CertidaoParteCelula } from "@/types/certidoesPartes";

import { formatarDocumentoArmazenado } from "../documentoBr";

export type ChipTom = "ok" | "alerta" | "erro" | "pendente" | "processando" | "na";

/** Color classes per tone — text always travels WITH the color. Same palette as
 *  the rest of the card's status chips. */
export const CHIP_ESTILO: Record<ChipTom, string> = {
  ok: "bg-emerald-100 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-200",
  alerta: "bg-red-100 text-red-900 dark:bg-red-950 dark:text-red-200",
  erro: "bg-red-100 text-red-900 dark:bg-red-950 dark:text-red-200",
  pendente: "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200",
  processando: "bg-sky-100 text-sky-900 dark:bg-sky-950 dark:text-sky-200",
  na: "bg-muted text-muted-foreground",
};

export interface ChipInfo {
  rotulo: string;
  tom: ChipTom;
}

/** Pendente / Processando / Negativa / Positiva / Erro / N/A (+ "Não emitida"). */
export function chipDaCelula(c: CertidaoParteCelula): ChipInfo {
  if (c.status === "na") return { rotulo: "N/A", tom: "na" };
  if (c.status_processamento === "processando" || c.status_processamento === "na_fila") {
    return { rotulo: "Processando", tom: "processando" };
  }
  if (c.status_processamento === "erro") return { rotulo: "Erro", tom: "erro" };
  switch (c.resultado) {
    case "negativa":
    case "negativa_com_homonimos":
      return { rotulo: "Negativa", tom: "ok" };
    case "positiva":
      return { rotulo: "Positiva", tom: "alerta" };
    case "positiva_com_efeito_de_negativa":
      return { rotulo: "Positiva c/ efeito de negativa", tom: "ok" };
    case "nao_emitida":
      return { rotulo: "Não emitida", tom: "alerta" };
    default:
      break;
  }
  if (c.status === "nao_constam") return { rotulo: "Negativa", tom: "ok" };
  if (c.status === "constam") return { rotulo: "Positiva", tom: "alerta" };
  return { rotulo: "Pendente", tom: "pendente" };
}

/** Tipos the backend NEVER auto-requests (contract §1.2 `TIPO_NAO_AUTOMATICO`). */
export function tipoAutomatico(tipo: string | null | undefined): boolean {
  if (!tipo) return false; // custom rows
  if (tipo.startsWith("tjsp")) return false;
  return tipo !== "serasa" && tipo !== "fgts_regularidade";
}

/** `2026-11-30` → `30/11/2026` (no timezone shift — the date is already a calendar day). */
export function dataBr(iso: string): string {
  const [y, m, d] = iso.slice(0, 10).split("-");
  return `${d}/${m}/${y}`;
}

export function avisoVencida(c: CertidaoParteCelula): string | null {
  if (!c.stale_para_contrato) return null;
  // The Receita PCEN 2ª via is judged by its printed validity, not by age.
  if (c.pcen) return `Validade impressa venceu em ${dataBr(c.pcen.validade_ate)} — vencida para contrato`;
  if (c.idade_dias == null) return null;
  return `Emitida há ${c.idade_dias} dias — vencida para contrato`;
}

/** Why a 2ª via reads older than "today": it carries the original emission date. */
export function notaSegundaVia(c: CertidaoParteCelula): string | null {
  if (c.pcen && !c.pcen.vencida) {
    return `2ª via — data de emissão original; válida até ${dataBr(c.pcen.validade_ate)}`;
  }
  return c.segunda_via ? "2ª via — data de emissão original" : null;
}

/** Where "Tenho dúvida" can actually reach someone: the org's configured
 *  WhatsApp, else its e-mail, else `null` (the UI then says so — never a dead
 *  button). */
export function linkDeSuporte(
  suporte: { email: string | null; whatsapp: string | null } | null,
  mensagem: string,
): { href: string; rotulo: string } | null {
  const fone = (suporte?.whatsapp ?? "").replace(/\D/g, "");
  if (fone) return { href: `https://wa.me/${fone}?text=${encodeURIComponent(mensagem)}`, rotulo: "Abrir WhatsApp" };
  if (suporte?.email) {
    return {
      href: `mailto:${suporte.email}?subject=${encodeURIComponent("Dúvida sobre certidão da Receita")}&body=${encodeURIComponent(mensagem)}`,
      rotulo: "Enviar e-mail",
    };
  }
  return null;
}

/** "9/13 ok · 2 pendentes · 1 vencida p/ contrato" — zero parts are dropped. */
export function resumoDaParte(p: CertidaoParte): string {
  const { nao_constam, constam, pendente, vencidas } = p.totais;
  const total = nao_constam + constam + pendente;
  const partes = [`${nao_constam}/${total} ok`];
  if (constam) partes.push(`${constam} com apontamento`);
  if (pendente) partes.push(`${pendente} ${pendente === 1 ? "pendente" : "pendentes"}`);
  if (vencidas) partes.push(`${vencidas} ${vencidas === 1 ? "vencida" : "vencidas"} p/ contrato`);
  return partes.join(" · ");
}

/** The party's document in its canonical punctuated form (the ONE identifier
 *  seam — `@noctusai/lib/identificador`, owner rule 2026-10-01); a value that
 *  does not fit its type is shown as stored. */
export function formatarDocumento(doc: string | null): string {
  if (!doc) return "sem documento";
  return formatarDocumentoArmazenado(doc);
}
