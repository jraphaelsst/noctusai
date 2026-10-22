/** Briefing draft (form strings) + validation mirroring S3a CONTRACT §1 limits, and the key slug rule. */
import type { Briefing, BriefingCanal } from "@/api/studio/types-geracao";

export const KEY_RE = /^[a-z0-9][a-z0-9-]{1,62}$/;

export const BRIEFING_LIMITES = {
  nome: [1, 80],
  objetivo: [10, 600],
  publico: [3, 300],
  tom_de_voz: [0, 300],
  limites: [0, 1000],
  exemplos: [0, 4000],
} as const;

export interface BriefingDraft {
  nome: string;
  objetivo: string;
  publico: string;
  canal: BriefingCanal | "";
  idioma: string;
  tom_de_voz: string;
  limites: string;
  exemplos: string;
}

export const BRIEFING_VAZIO: BriefingDraft = {
  nome: "",
  objetivo: "",
  publico: "",
  canal: "",
  idioma: "pt-BR",
  tom_de_voz: "",
  limites: "",
  exemplos: "",
};

export type BriefingErrors = Partial<Record<keyof BriefingDraft, string>>;

/** nome -> `^[a-z0-9][a-z0-9-]{1,62}$` candidate (accents stripped, runs of non-alnum -> "-"). */
export function slugify(nome: string): string {
  return nome
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 63)
    .replace(/-+$/g, "");
}

function faixa(label: string, v: string, [min, max]: readonly [number, number]): string | undefined {
  const n = v.trim().length;
  if (n < min) return min <= 1 ? `${label} é obrigatório.` : `${label}: mínimo de ${min} caracteres.`;
  if (n > max) return `${label}: máximo de ${max} caracteres.`;
  return undefined;
}

export function validarBriefing(d: BriefingDraft): { errors: BriefingErrors; briefing: Briefing | null } {
  const errors: BriefingErrors = {};
  const L = BRIEFING_LIMITES;
  const set = (k: keyof BriefingErrors, e: string | undefined) => {
    if (e) errors[k] = e;
  };
  set("nome", faixa("Nome", d.nome, L.nome));
  set("objetivo", faixa("Objetivo", d.objetivo, L.objetivo));
  set("publico", faixa("Público", d.publico, L.publico));
  if (!d.canal) errors.canal = "Escolha o canal.";
  set("tom_de_voz", faixa("Tom de voz", d.tom_de_voz, L.tom_de_voz));
  set("limites", faixa("Limites", d.limites, L.limites));
  set("exemplos", faixa("Exemplos", d.exemplos, L.exemplos));
  if (Object.keys(errors).length > 0 || !d.canal) return { errors, briefing: null };
  const briefing: Briefing = {
    nome: d.nome.trim(),
    objetivo: d.objetivo.trim(),
    publico: d.publico.trim(),
    canal: d.canal,
  };
  if (d.idioma.trim()) briefing.idioma = d.idioma.trim();
  if (d.tom_de_voz.trim()) briefing.tom_de_voz = d.tom_de_voz.trim();
  if (d.limites.trim()) briefing.limites = d.limites.trim();
  if (d.exemplos.trim()) briefing.exemplos = d.exemplos.trim();
  return { errors, briefing };
}
