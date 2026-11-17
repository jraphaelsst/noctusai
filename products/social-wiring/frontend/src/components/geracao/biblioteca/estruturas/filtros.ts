/**
 * The Estruturas list filters as URL state (`?busca=&formato=&objetivo=&status=&pendentes=1&pagina=`),
 * so a filtered list is linkable and the back button works. Pure: parse + serialise + count.
 */
import type { EstruturaFormato, EstruturaObjetivo, EstruturaStatus } from "@/types/estruturas";
import { FORMATOS, OBJETIVOS } from "./rotulos";

export type FiltroStatus = EstruturaStatus | "todas";

export type FiltrosEstruturas = {
  busca: string;
  formatos: EstruturaFormato[];
  objetivos: EstruturaObjetivo[];
  /** Admin only. `ativa` is the member-facing default. */
  status: FiltroStatus;
  /** Admin only: "Pendentes de revisão". */
  pendentes: boolean;
  /** Admin only: "Sem uso há 24 meses" (`revisao=pendente`). */
  desuso: boolean;
  /** 1-based. */
  pagina: number;
};

export const FILTROS_ESTRUTURAS_VAZIOS: FiltrosEstruturas = {
  busca: "",
  formatos: [],
  objetivos: [],
  status: "ativa",
  pendentes: false,
  desuso: false,
  pagina: 1,
};

const STATUS_VALIDOS: readonly FiltroStatus[] = ["ativa", "rascunho", "arquivada", "todas"];

export function filtrosDeParams(p: URLSearchParams): FiltrosEstruturas {
  const pagina = Number.parseInt(p.get("pagina") ?? "", 10);
  const status = p.get("status") as FiltroStatus | null;
  return {
    busca: p.get("busca") ?? "",
    formatos: p.getAll("formato").filter((x): x is EstruturaFormato => (FORMATOS as readonly string[]).includes(x)),
    objetivos: p.getAll("objetivo").filter((x): x is EstruturaObjetivo => (OBJETIVOS as readonly string[]).includes(x)),
    status: status && STATUS_VALIDOS.includes(status) ? status : "ativa",
    pendentes: p.get("pendentes") === "1",
    desuso: p.get("desuso") === "1",
    pagina: Number.isFinite(pagina) && pagina > 1 ? pagina : 1,
  };
}

/** Writes the filters onto `base` (other params — `aba`, `viral` — are kept). Defaults are omitted. */
export function filtrosParaParams(f: FiltrosEstruturas, base?: URLSearchParams): URLSearchParams {
  const p = new URLSearchParams(base);
  for (const k of ["busca", "formato", "objetivo", "status", "pendentes", "desuso", "pagina"]) p.delete(k);
  if (f.busca.trim()) p.set("busca", f.busca.trim());
  f.formatos.forEach((x) => p.append("formato", x));
  f.objetivos.forEach((x) => p.append("objetivo", x));
  if (f.status !== "ativa") p.set("status", f.status);
  if (f.pendentes) p.set("pendentes", "1");
  if (f.desuso) p.set("desuso", "1");
  if (f.pagina > 1) p.set("pagina", String(f.pagina));
  return p;
}

export function contarFiltros(f: FiltrosEstruturas): number {
  return (f.busca.trim() ? 1 : 0) + f.formatos.length + f.objetivos.length + (f.status !== "ativa" ? 1 : 0) + (f.pendentes ? 1 : 0) + (f.desuso ? 1 : 0);
}
