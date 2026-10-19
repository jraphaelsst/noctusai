/** Pure column model for the Conversas kanban (one column per etiqueta). */
import type { Conversa, Etiqueta } from "@/hooks/useJuliaConversas";
import { SEM_ETIQUETA } from "./EtiquetaPicker";

export const COL_TODAS = "__todas";
export const COL_ARQUIVADAS = "__arquivadas";

/** A conversation as placed in ONE column (the same chat can sit in several). */
export interface CartaoKanban { key: string; stage: string; conversa: Conversa }

export interface ColunasInput {
  todas: Conversa[];
  arquivadas: Conversa[];
  etiquetas: Etiqueta[];
  /** Tag ids (or SEM_ETIQUETA) the user added as columns, in order. */
  colunas: string[];
  todasVisivel: boolean;
  arquivadasAberta: boolean;
}

export function montarColunas(i: ColunasInput) {
  const card = (stage: string, conversa: Conversa): CartaoKanban => ({ key: `${stage}:${conversa.contato_id}`, stage, conversa });
  const out = [
    { stage: { id: COL_TODAS, label: "Todas" }, cards: i.todasVisivel ? i.todas.map((c) => card(COL_TODAS, c)) : [] },
  ];
  for (const id of i.colunas) {
    if (id === SEM_ETIQUETA) {
      out.push({ stage: { id, label: "Sem etiqueta" }, cards: i.todas.filter((c) => (c.etiquetas ?? []).length === 0).map((c) => card(id, c)) });
      continue;
    }
    const tag = i.etiquetas.find((t) => t.id === id);
    if (!tag) continue;
    out.push({ stage: { id, label: tag.nome }, cards: i.todas.filter((c) => (c.etiquetas ?? []).some((t) => t.id === id)).map((c) => card(id, c)) });
  }
  out.push({ stage: { id: COL_ARQUIVADAS, label: "Arquivadas" }, cards: i.arquivadasAberta ? i.arquivadas.map((c) => card(COL_ARQUIVADAS, c)) : [] });
  return out;
}

export interface MovimentoPatch { arquivado?: boolean; etiquetas?: string[] }

/** What a drop means for the contact: tags are the columns, archive is the last lane. */
export function patchDoMovimento(conversa: Conversa, de: string, para: string): MovimentoPatch | null {
  if (de === para) return null;
  const tags = (conversa.etiquetas ?? []).map((t) => t.id);
  const patch: MovimentoPatch = {};
  if (para === COL_ARQUIVADAS) return { arquivado: true };
  if (de === COL_ARQUIVADAS) patch.arquivado = false;
  const base = de === COL_TODAS || de === COL_ARQUIVADAS || de === SEM_ETIQUETA ? tags : tags.filter((t) => t !== de);
  if (para === COL_TODAS || para === SEM_ETIQUETA) {
    // Dropping into "Sem etiqueta" clears every tag; into "Todas" only leaves the source column.
    patch.etiquetas = para === SEM_ETIQUETA ? [] : base;
  } else {
    patch.etiquetas = base.includes(para) ? base : [...base, para];
  }
  return patch;
}
