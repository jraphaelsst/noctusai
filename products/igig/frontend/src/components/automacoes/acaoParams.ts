/**
 * Pure helpers for the Automações ação form — the per-tipo params the
 * backend validates with `extra="forbid"` models (`app/schemas/automacoes.py`).
 *
 * The form keeps ONE loose draft (every field any tipo might use, as
 * strings) so switching tipo never loses what was typed; `montarAcao` then
 * emits EXACTLY the keys that tipo accepts — an extra key would be a 422.
 */
import type { Acao, TipoAcao } from "@/hooks/useAutomacoes";

export interface AcaoDraft {
  titulo: string;
  itens: string;
  profissional_id: string;
  prazo_dias: string;
  responsavel_id: string;
  mensagem: string;
  assunto: string;
  para: string;
  usuario_ids: string[];
}

export const DRAFT_VAZIO: AcaoDraft = {
  titulo: "",
  itens: "",
  profissional_id: "",
  prazo_dias: "",
  responsavel_id: "",
  mensagem: "",
  assunto: "",
  para: "",
  usuario_ids: [],
};

/** An existing rule's ação → the loose draft (edit mode). */
export function draftDe(acao: Acao | null | undefined): AcaoDraft {
  if (!acao) return { ...DRAFT_VAZIO };
  const p = (acao.params ?? {}) as Record<string, unknown>;
  const str = (v: unknown) => (v == null ? "" : String(v));
  return {
    titulo: str(p.titulo),
    itens: Array.isArray(p.itens) ? (p.itens as unknown[]).map(String).join("\n") : "",
    profissional_id: str(p.profissional_id),
    prazo_dias: str(p.prazo_dias),
    responsavel_id: str(p.responsavel_id),
    mensagem: str(p.mensagem),
    assunto: str(p.assunto),
    para: str(p.para),
    usuario_ids: Array.isArray(p.usuario_ids) ? (p.usuario_ids as unknown[]).map(String) : [],
  };
}

const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

/** pt-BR reason the draft cannot be saved for this tipo, or null when valid. */
export function problemaDoDraft(tipo: TipoAcao, d: AcaoDraft): string | null {
  switch (tipo) {
    case "criar_checklist":
      return d.titulo.trim() ? null : "Informe o título do checklist.";
    case "definir_responsavel":
      return d.profissional_id ? null : "Escolha o responsável.";
    case "criar_tarefa": {
      if (!d.titulo.trim()) return "Informe o título da tarefa.";
      if (d.prazo_dias.trim() && !/^\d+$/.test(d.prazo_dias.trim())) return "Prazo em dias deve ser um número inteiro.";
      if (d.prazo_dias.trim() && Number(d.prazo_dias) > 365) return "Prazo máximo: 365 dias.";
      return null;
    }
    case "notificar":
      return null;
    case "enviar_email":
      if (!d.assunto.trim()) return "Informe o assunto.";
      if (!d.mensagem.trim()) return "Escreva a mensagem.";
      if (d.para.trim() && !EMAIL.test(d.para.trim())) return "E-mail do destinatário inválido.";
      return null;
    case "enviar_whatsapp":
      return d.mensagem.trim() ? null : "Escreva a mensagem.";
  }
}

const opcional = (v: string) => (v.trim() ? v.trim() : null);

/** The draft → `{tipo, params}` with EXACTLY the keys the tipo accepts. */
export function montarAcao(tipo: TipoAcao, d: AcaoDraft): Acao {
  switch (tipo) {
    case "criar_checklist":
      return {
        tipo,
        params: {
          titulo: d.titulo.trim(),
          itens: d.itens
            .split("\n")
            .map((i) => i.trim())
            .filter(Boolean),
        },
      };
    case "definir_responsavel":
      return { tipo, params: { profissional_id: d.profissional_id } };
    case "criar_tarefa":
      return {
        tipo,
        params: {
          titulo: d.titulo.trim(),
          prazo_dias: d.prazo_dias.trim() ? Number(d.prazo_dias) : null,
          responsavel_id: d.responsavel_id || null,
        },
      };
    case "notificar":
      return { tipo, params: { titulo: opcional(d.titulo), mensagem: opcional(d.mensagem), usuario_ids: d.usuario_ids } };
    case "enviar_email":
      return { tipo, params: { assunto: d.assunto.trim(), mensagem: d.mensagem.trim(), para: opcional(d.para) } };
    case "enviar_whatsapp":
      return { tipo, params: { mensagem: d.mensagem.trim(), para: opcional(d.para) } };
  }
}

/** One-line human summary of a rule's ação, for the list. */
export function resumoAcao(acao: Acao, nomes: { profissional?: (id: string) => string | undefined } = {}): string {
  const p = acao.params as Record<string, unknown>;
  switch (acao.tipo) {
    case "criar_checklist":
      return `Checklist "${String(p.titulo ?? "")}"`;
    case "definir_responsavel":
      return `Responsável: ${nomes.profissional?.(String(p.profissional_id)) ?? "profissional"}`;
    case "criar_tarefa":
      return `Tarefa "${String(p.titulo ?? "")}"${p.prazo_dias != null ? ` · prazo ${p.prazo_dias}d` : ""}`;
    case "notificar":
      return `Notificar${p.titulo ? `: ${String(p.titulo)}` : " o responsável"}`;
    case "enviar_email":
      return `E-mail "${String(p.assunto ?? "")}"${p.para ? ` para ${String(p.para)}` : " ao contato do card"}`;
    case "enviar_whatsapp":
      return `WhatsApp${p.para ? ` para ${String(p.para)}` : " ao contato do card"}`;
  }
}
