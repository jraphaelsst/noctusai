/**
 * Pure cache edits for the certidões grid (`CertidoesPartesResponse`): what a
 * write KNOWS about one cell (a typed value, the server's resultado row) is
 * put into the cached grid so the screen agrees with the server at once —
 * the settle refetch only refreshes derived fields.
 *
 * Mirrors the backend rules the cell/summary derive from
 * (`certidoes_matriz_service._status_da_celula`, `_concluida`) — keep in sync.
 */
import type { ResultadoPatchInput } from "@/types/certidoesEstruturadas";
import type {
  CelulaStatus,
  CertidaoParte,
  CertidaoParteCelula,
  CertidaoParteTotais,
  CertidoesPartesResponse,
} from "@/types/certidoesPartes";

const NAO_CONSTAM = new Set(["negativa", "positiva_com_efeito_de_negativa", "negativa_com_homonimos"]);
const CONSTAM = new Set(["positiva", "nao_emitida"]);
const LENDO = new Set(["processando", "na_fila"]);

/** Which cell: the party's alvo (cliente/empresa id) + the linha key. */
export interface AlvoCelula {
  kind: string;
  alvoId: string;
  linhaChave: string;
}

/** The resultado row the server returns (PATCH / voltar-automatico). */
export interface ResultadoServidor {
  id: string;
  consulta_id?: string | null;
  status?: string | null;
  resultado?: string | null;
  numero?: string | null;
  emitida_em?: string | null;
  validade_ate?: string | null;
  emitida_em_origem?: string | null;
  resultado_origem?: string | null;
  confirmado_em?: string | null;
  erro_mensagem?: string | null;
  releitura?: { estado?: string; concluida_em?: string | null; divergencias?: unknown[] } | null;
}

export const statusDoResultado = (resultado: string | null | undefined): CelulaStatus =>
  resultado && NAO_CONSTAM.has(resultado) ? "nao_constam"
  : resultado && CONSTAM.has(resultado) ? "constam"
  : "pendente";

/** A finished read, or a certidão a human typed COMPLETE (backend `_concluida`). */
function concluida(c: Pick<CertidaoParteCelula, "status_processamento" | "origem" | "resultado" | "numero" | "emitida_em">) {
  if (c.status_processamento === "sucesso") return true;
  return (
    c.origem === "manual" &&
    (c.status_processamento === "pendente" || c.status_processamento === "erro" || c.status_processamento == null) &&
    !!(c.resultado && c.numero && c.emitida_em)
  );
}

function lendo(c: CertidaoParteCelula): boolean {
  return !!c.status_processamento && LENDO.has(c.status_processamento);
}

/** The cell with a server row (or typed values) written over it. */
export function celulaComResultado(c: CertidaoParteCelula, row: Partial<ResultadoServidor>): CertidaoParteCelula {
  const next: CertidaoParteCelula = { ...c };
  if (row.id !== undefined) next.resultado_id = row.id;
  if (row.consulta_id !== undefined) next.consulta_id = row.consulta_id;
  if (row.status !== undefined) next.status_processamento = row.status as CertidaoParteCelula["status_processamento"];
  if (row.resultado !== undefined) next.resultado = row.resultado as CertidaoParteCelula["resultado"];
  if (row.numero !== undefined) next.numero = row.numero;
  if (row.emitida_em !== undefined) next.emitida_em = row.emitida_em;
  if (row.validade_ate !== undefined) next.validade_ate = row.validade_ate;
  if (row.emitida_em_origem !== undefined) next.emitida_em_origem = row.emitida_em_origem as CertidaoParteCelula["emitida_em_origem"];
  if (row.resultado_origem !== undefined) next.origem = (row.resultado_origem as CertidaoParteCelula["origem"]) || null;
  if (row.confirmado_em !== undefined) next.confirmado = row.confirmado_em != null;
  if (row.erro_mensagem !== undefined) next.erro_mensagem = row.erro_mensagem;
  if (row.releitura !== undefined) {
    next.releitura = row.releitura
      ? {
          em_andamento: row.releitura.estado === "em_andamento",
          concluida_em: row.releitura.concluida_em ?? null,
          divergencias: (row.releitura.divergencias ?? []) as never,
        }
      : null;
  }
  // A previous value survives a re-read (`processando` keeps it): classify by it.
  const status = concluida(next) || (lendo(next) && !!next.resultado) ? statusDoResultado(next.resultado) : "pendente";
  next.status = status;
  next.texto = status === "nao_constam" ? "Não constam" : status === "constam" ? "Constam" : "Pendente";
  if (status !== "pendente" || lendo(next)) next.opcional = false;
  return next;
}

/** The typed values as the row the PATCH will produce (optimistic stand-in). */
export function linhaDigitada(patch: ResultadoPatchInput, atual: CertidaoParteCelula): Partial<ResultadoServidor> {
  const resultado = patch.resultado ?? atual.resultado;
  const numero = patch.numero ?? atual.numero;
  const emitida = patch.emitida_em ?? atual.emitida_em;
  const completo = !!(resultado && numero && emitida);
  return {
    ...patch,
    resultado_origem: "manual",
    confirmado_em: new Date().toISOString(),
    // A typed date is not a PDF-metadata inference anymore.
    ...(patch.emitida_em !== undefined ? { emitida_em_origem: null } : {}),
    ...(completo && !lendo(atual) ? { status: "sucesso" } : {}),
  };
}

/** Recount the party's totals from its cells (vencidas stay the server's). */
export function recalcularTotais(parte: CertidaoParte): CertidaoParteTotais {
  const t: CertidaoParteTotais = {
    nao_constam: 0, constam: 0, pendente: 0, processando: 0, relendo: 0, erros: 0,
    vencidas: parte.totais.vencidas, opcionais: 0,
  };
  for (const c of Object.values(parte.celulas)) {
    if (c.status === "na") continue;
    if (c.status_processamento === "erro") t.erros = (t.erros ?? 0) + 1;
    if (lendo(c) && c.status === "pendente") { t.processando = (t.processando ?? 0) + 1; continue; }
    if (c.opcional) { t.opcionais = (t.opcionais ?? 0) + 1; continue; }
    t[c.status === "nao_constam" ? "nao_constam" : c.status === "constam" ? "constam" : "pendente"] += 1;
    if (lendo(c) || c.releitura?.em_andamento) t.relendo = (t.relendo ?? 0) + 1;
  }
  return t;
}

/** Apply `edit` to the addressed cell; totals recounted. Uncached / unmatched ⇒ unchanged. */
export function comCelulaEditada(
  data: CertidoesPartesResponse | undefined,
  alvo: AlvoCelula,
  edit: (c: CertidaoParteCelula) => CertidaoParteCelula,
): CertidoesPartesResponse | undefined {
  if (!data) return data;
  let mudou = false;
  const partes = data.partes.map((p) => {
    const dono = alvo.kind === "empresa" ? p.empresa_id : p.cliente_id;
    if (p.kind !== alvo.kind || dono !== alvo.alvoId) return p;
    const celula = p.celulas[alvo.linhaChave];
    if (!celula) return p;
    mudou = true;
    const parte = { ...p, celulas: { ...p.celulas, [alvo.linhaChave]: edit(celula) } };
    return { ...parte, totais: recalcularTotais(parte) };
  });
  return mudou ? { ...data, partes } : data;
}

/** Edit a cell addressed by its resultado id (when the caller has no alvo). */
export function comCelulaDoResultado(
  data: CertidoesPartesResponse | undefined,
  resultadoId: string,
  edit: (c: CertidaoParteCelula) => CertidaoParteCelula,
): CertidoesPartesResponse | undefined {
  if (!data) return data;
  let mudou = false;
  const partes = data.partes.map((p) => {
    const chave = Object.keys(p.celulas).find((k) => p.celulas[k].resultado_id === resultadoId);
    if (!chave) return p;
    mudou = true;
    const parte = { ...p, celulas: { ...p.celulas, [chave]: edit(p.celulas[chave]) } };
    return { ...parte, totais: recalcularTotais(parte) };
  });
  return mudou ? { ...data, partes } : data;
}


/** Put the server's freshly-built party over the cached one (same `chave`) —
 *  what a card-scoped emission control answers with. Uncached / unmatched ⇒ unchanged. */
export function comParteSubstituida(
  data: CertidoesPartesResponse | undefined,
  parte: CertidaoParte,
): CertidoesPartesResponse | undefined {
  if (!data || !data.partes.some((p) => p.chave === parte.chave)) return data;
  return { ...data, partes: data.partes.map((p) => (p.chave === parte.chave ? parte : p)) };
}
