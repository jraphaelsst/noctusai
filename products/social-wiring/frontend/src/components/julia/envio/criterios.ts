/** Pure helpers for the "Envio de leads qualificados" criteria builder. */
import {
  CAMPOS_CRITERIO,
  CRITERIO_BASE,
  type Criterio,
  type Grupo,
  type OperadorCriterio,
} from "@/hooks/useJuliaEnvio";

export interface CriterioRascunho {
  campo: string;
  operador: OperadorCriterio | "";
  valor: unknown;
}
export type GrupoRascunho = CriterioRascunho[];

export const OPERADORES: { op: OperadorCriterio; rotulo: string }[] = [
  { op: "preenchido", rotulo: "Independentemente" },
  { op: ">=", rotulo: "A partir de" },
  { op: "<=", rotulo: "Até" },
  { op: "entre", rotulo: "De – Até" },
];

export const campoDe = (campo: string) => CAMPOS_CRITERIO.find((c) => c.campo === campo);
export const ehBase = (c: { campo: string }) => c.campo === CRITERIO_BASE.campo;

export function novoCriterio(): CriterioRascunho {
  return { campo: "", operador: "", valor: null };
}
export function clonarGrupos(g: Grupo[]): GrupoRascunho[] {
  return g.map((grupo) => grupo.map((c) => ({ ...c })));
}
/** The base criterion is ALWAYS first of the first group, whatever the server sent. */
export function garantirBase(g: GrupoRascunho[]): GrupoRascunho[] {
  const sem = g.map((grupo) => grupo.filter((c) => !ehBase(c)));
  const primeiro = [{ ...CRITERIO_BASE }, ...(sem[0] ?? [])];
  return [primeiro, ...sem.slice(1).filter((x) => x.length > 0)];
}

export function rotuloValor(c: CriterioRascunho): string {
  const meta = campoDe(c.campo);
  const fmt = (n: unknown) =>
    meta?.moeda ? `R$ ${Number(n).toLocaleString("pt-BR")}` : Number(n).toLocaleString("pt-BR");
  if (c.operador === ">=") return `a partir de ${fmt(c.valor)}`;
  if (c.operador === "<=") return `até ${fmt(c.valor)}`;
  if (c.operador === "entre" && Array.isArray(c.valor)) return `de ${fmt(c.valor[0])} até ${fmt(c.valor[1])}`;
  if (c.operador === "preenchido") return "preenchido";
  return "";
}
export function rotuloCriterio(c: CriterioRascunho): string {
  if (ehBase(c)) return "Comportamento — Qualificado via inteligência da Julia";
  const meta = campoDe(c.campo);
  if (meta?.booleano) return meta.rotulo;
  return `${meta?.rotulo ?? c.campo}: ${rotuloValor(c)}`;
}

/** null when valid, else the pt-BR reason. */
export function validarCriterio(c: CriterioRascunho): string | null {
  if (ehBase(c)) return null;
  const meta = campoDe(c.campo);
  if (!meta) return "Selecione o critério.";
  if (meta.booleano) return null;
  if (!c.operador) return "Selecione a condição.";
  if (c.operador === "preenchido") return null;
  const n = (v: unknown) => v !== null && v !== "" && Number.isFinite(Number(v));
  if (c.operador === "entre") {
    const [a, b] = Array.isArray(c.valor) ? c.valor : [];
    if (!n(a) || !n(b)) return "Informe o intervalo.";
    if (Number(a) > Number(b)) return "O valor inicial deve ser menor ou igual ao final.";
    return null;
  }
  return n(c.valor) ? null : "Informe o valor.";
}
export function validarGrupos(g: GrupoRascunho[]): string | null {
  if (!g.length || !g[0]?.some(ehBase)) return "Defina ao menos um critério no cartão Comportamento.";
  for (const grupo of g) for (const c of grupo) {
    const e = validarCriterio(c);
    if (e) return e;
  }
  return null;
}
/** Normalises a validated draft to the wire shape. */
export function paraWire(g: GrupoRascunho[]): Grupo[] {
  return g.map((grupo) =>
    grupo.map((c): Criterio => {
      if (ehBase(c)) return { ...CRITERIO_BASE };
      const meta = campoDe(c.campo);
      if (meta?.booleano) return { campo: c.campo, operador: "=", valor: true };
      if (c.operador === "entre") {
        const [a, b] = c.valor as unknown[];
        return { campo: c.campo, operador: "entre", valor: [Number(a), Number(b)] };
      }
      if (c.operador === "preenchido") return { campo: c.campo, operador: "preenchido", valor: null };
      return { campo: c.campo, operador: c.operador as OperadorCriterio, valor: Number(c.valor) };
    }),
  );
}
