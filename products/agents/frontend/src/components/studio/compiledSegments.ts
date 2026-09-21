/**
 * Pure slicing of a compiled prompt into labelled blocks, driven ONLY by the
 * server's manifest offsets (CONTRACT §C: `inicio`/`fim` are character
 * offsets into `texto`). The UI never re-composes the prompt (§A4) — it cuts
 * the server's text where the server says the sections are.
 *
 * Everything between two sections is also returned: the `\n\n` separators are
 * dropped as whitespace, but any NON-whitespace text outside every manifest
 * range is surfaced as an `orfao` segment. The inspector's promise is "what
 * you see is what runs"; hiding unattributed text would break it silently.
 * Offsets that overlap or fall outside `texto` are reported as `problemas`
 * instead of being quietly clamped away.
 */
import type { ManifestSection } from "@/api/studio/types";

export type CompiledSegment =
  | { tipo: "secao"; secao: ManifestSection; texto: string; indice: number }
  | { tipo: "orfao"; texto: string; inicio: number; fim: number };

export interface SegmentResult {
  segmentos: CompiledSegment[];
  problemas: string[];
}

export function segmentCompiled(texto: string, manifest: ManifestSection[]): SegmentResult {
  const problemas: string[] = [];
  const segmentos: CompiledSegment[] = [];
  const ordered = manifest
    .map((secao, indice) => ({ secao, indice }))
    .sort((x, y) => x.secao.inicio - y.secao.inicio);

  let cursor = 0;
  const pushGap = (inicio: number, fim: number) => {
    if (fim <= inicio) return;
    const gap = texto.slice(inicio, fim);
    if (gap.trim()) segmentos.push({ tipo: "orfao", texto: gap, inicio, fim });
  };

  for (const { secao, indice } of ordered) {
    const { inicio, fim } = secao;
    if (inicio < 0 || fim > texto.length || fim < inicio) {
      problemas.push(
        `Seção "${secao.titulo}" tem limites inválidos (${inicio}–${fim}) para um texto de ${texto.length} caracteres.`,
      );
      continue;
    }
    if (inicio < cursor) {
      problemas.push(`Seção "${secao.titulo}" sobrepõe a seção anterior (começa em ${inicio}, anterior termina em ${cursor}).`);
    } else {
      pushGap(cursor, inicio);
    }
    segmentos.push({ tipo: "secao", secao, texto: texto.slice(inicio, fim), indice });
    cursor = Math.max(cursor, fim);
  }
  pushGap(cursor, texto.length);

  return { segmentos, problemas };
}

/** Same estimator as the compiler's `tokens_estimados` (§C: ceil(len/4)). */
export function estimateTokens(text: string): number {
  return Math.ceil(text.length / 4);
}

/**
 * Where a manifest block comes from, as a studio tab + deep-link params.
 * Author sections carry `origem.id` (the section id). Auto blocks are
 * recognised by their titles, which §C pins exactly ("Skills",
 * "Base de conhecimento", "Ferramentas", "Cliente em foco: {nome}").
 * Unknown auto blocks return `null` (no link rather than a wrong link).
 */
export type SourceTarget = {
  tab: "prompt" | "skills" | "conhecimento" | "configuracoes" | "clientes";
  params: Record<string, string>;
  rotulo: string;
};

export function sourceTarget(secao: ManifestSection, clientId: string | null = null): SourceTarget | null {
  if (secao.origem.tipo === "secao") {
    // `chave` travels with the id: section ids are per-version (a draft is a
    // deep copy), so the Prompt tab — which edits the DRAFT — falls back to
    // the chave when the inspected version is not the draft.
    return secao.origem.id
      ? { tab: "prompt", params: { secao: secao.origem.id, chave: secao.chave }, rotulo: "Seção do prompt" }
      : null;
  }
  const titulo = secao.titulo.trim();
  if (titulo === "Skills") return { tab: "skills", params: {}, rotulo: "Automática · skills" };
  if (titulo === "Base de conhecimento")
    return { tab: "conhecimento", params: {}, rotulo: "Automática · base de conhecimento" };
  if (titulo === "Ferramentas") return { tab: "configuracoes", params: {}, rotulo: "Automática · ferramentas" };
  if (titulo.startsWith("Cliente em foco"))
    return {
      tab: "clientes",
      params: clientId ? { cliente: clientId } : {},
      rotulo: "Automática · cliente em foco",
    };
  return null;
}

/** `sha256:abcdef…` → `sha256:abcdef12…` for headers and links. */
export function shortHash(hash: string | null | undefined, n = 12): string {
  if (!hash) return "—";
  const [algo, hex] = hash.includes(":") ? hash.split(":", 2) : ["", hash];
  const short = hex.length > n ? `${hex.slice(0, n)}…` : hex;
  return algo ? `${algo}:${short}` : short;
}

const SECTION_PALETTE = [
  "bg-primary",
  "bg-sky-500",
  "bg-emerald-500",
  "bg-amber-500",
  "bg-fuchsia-500",
  "bg-rose-500",
  "bg-indigo-500",
  "bg-teal-500",
];

/** Decorative per-block colour shared by the token bar and the block view. */
export function sectionColor(indice: number): string {
  return SECTION_PALETTE[indice % SECTION_PALETTE.length];
}
