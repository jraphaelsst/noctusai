/**
 * Biblioteca filters <-> URL query string (contract §4.3 #7, §7.3). All state
 * lives in the URL so a filtered view is shareable and survives reload.
 */
export type OrdemViral = "mais_vistos" | "mais_recentes";
export type BuscarEm = "gancho" | "transcricao";

export interface FiltrosViral {
  nichos: number[];
  profissoes: number[];
  verTodos: boolean;
  ordem: OrdemViral;
  q: string;
  buscarEm: BuscarEm;
  dataDe: string;
  dataAte: string;
  viewsMin: number | null;
  likesMin: number | null;
  commentsMin: number | null;
  perfilId: string;
  formatoId: number | null;
  codigo: number | null;
  somenteVirais: boolean;
  /** Restrict to the marca's own library (Minha Biblioteca). Not in the URL. */
  pool?: "minha_biblioteca";
  page: number;
}

export const FILTROS_VAZIOS: FiltrosViral = {
  nichos: [],
  profissoes: [],
  verTodos: false,
  ordem: "mais_vistos",
  q: "",
  buscarEm: "gancho",
  dataDe: "",
  dataAte: "",
  viewsMin: null,
  likesMin: null,
  commentsMin: null,
  perfilId: "",
  formatoId: null,
  codigo: null,
  somenteVirais: true,
  page: 1,
};

const ints = (raw: string[]): number[] =>
  raw.map(Number).filter((n) => Number.isInteger(n) && n > 0);
const intOuNull = (v: string | null): number | null => {
  if (v == null || v === "") return null;
  const n = Number(v);
  return Number.isInteger(n) && n >= 0 ? n : null;
};

export function filtrosDeParams(p: URLSearchParams): FiltrosViral {
  const page = intOuNull(p.get("page"));
  return {
    nichos: ints(p.getAll("nichos")),
    profissoes: ints(p.getAll("profissoes")),
    verTodos: p.get("ver_todos") === "1",
    ordem: p.get("ordem") === "mais_recentes" ? "mais_recentes" : "mais_vistos",
    q: p.get("q") ?? "",
    buscarEm: p.get("buscar_em") === "transcricao" ? "transcricao" : "gancho",
    dataDe: p.get("data_de") ?? "",
    dataAte: p.get("data_ate") ?? "",
    viewsMin: intOuNull(p.get("views_min")),
    likesMin: intOuNull(p.get("likes_min")),
    commentsMin: intOuNull(p.get("comments_min")),
    perfilId: p.get("perfil") ?? "",
    formatoId: intOuNull(p.get("formato_id")),
    codigo: intOuNull(p.get("codigo")),
    somenteVirais: p.get("somente_virais") !== "0",
    page: page && page > 0 ? page : 1,
  };
}

export function filtrosParaParams(f: FiltrosViral): URLSearchParams {
  const p = new URLSearchParams();
  f.nichos.forEach((n) => p.append("nichos", String(n)));
  f.profissoes.forEach((n) => p.append("profissoes", String(n)));
  if (f.verTodos) p.set("ver_todos", "1");
  if (f.ordem !== "mais_vistos") p.set("ordem", f.ordem);
  if (f.q.trim()) p.set("q", f.q.trim());
  if (f.q.trim() && f.buscarEm !== "gancho") p.set("buscar_em", f.buscarEm);
  if (f.dataDe) p.set("data_de", f.dataDe);
  if (f.dataAte) p.set("data_ate", f.dataAte);
  if (f.viewsMin != null) p.set("views_min", String(f.viewsMin));
  if (f.likesMin != null) p.set("likes_min", String(f.likesMin));
  if (f.commentsMin != null) p.set("comments_min", String(f.commentsMin));
  if (f.perfilId) p.set("perfil", f.perfilId);
  if (f.formatoId != null) p.set("formato_id", String(f.formatoId));
  if (f.codigo != null) p.set("codigo", String(f.codigo));
  if (!f.somenteVirais) p.set("somente_virais", "0");
  if (f.page > 1) p.set("page", String(f.page));
  return p;
}

/** Count of active filter groups (shown on the Filtros button). */
export function contarFiltrosAtivos(f: FiltrosViral): number {
  return [
    f.nichos.length > 0,
    f.profissoes.length > 0,
    !!f.q.trim(),
    !!f.dataDe || !!f.dataAte,
    f.viewsMin != null,
    f.likesMin != null,
    f.commentsMin != null,
    !!f.perfilId,
    f.formatoId != null,
    f.codigo != null,
    !f.somenteVirais,
  ].filter(Boolean).length;
}

/**
 * Instagram embed URL. Only `instagram.com/(p|reel|tv)/<shortcode>` https
 * permalinks are accepted (contract §7.3); anything else returns null.
 */
export function embedUrlInstagram(permalink: string | null | undefined): string | null {
  if (!permalink) return null;
  let u: URL;
  try {
    u = new URL(permalink);
  } catch {
    return null;
  }
  if (u.protocol !== "https:") return null;
  if (u.hostname !== "www.instagram.com" && u.hostname !== "instagram.com") return null;
  const m = u.pathname.match(/\/(p|reel|tv)\/([A-Za-z0-9_-]+)/);
  return m ? `https://www.instagram.com/p/${m[2]}/embed/` : null;
}
