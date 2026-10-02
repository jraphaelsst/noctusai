/**
 * CPF / CNPJ helpers for the party-registration lookup (contract §2.5).
 *
 * The backend is the authority; this only decides WHEN to fire the lookup — a
 * half-typed or check-digit-invalid documento must not cost a round trip nor
 * flash a server 400.
 *
 * Owner rule 2026-10-01 (`canonical-identifiers`): the check-digit algorithms
 * and the punctuated shape live in ONE place — `@noctusai/lib/identificador`
 * (the TS twin of `noctusai_lib.primitives.identificador`). This file used to
 * carry its own copy of the CPF / CNPJ mod-11 code; it is now a thin adapter.
 */
import {
  chaveBuscaIdentificador,
  formatIdentificador,
  lerIdentificador,
} from "@noctusai/lib/identificador";

export function apenasDigitos(valor: string): string {
  return valor.replace(/\D/g, "");
}

/** Does `valor` FIT a CPF — punctuated shape and check digits? */
export function cpfValido(valor: string): boolean {
  return lerIdentificador("cpf", valor).cabe;
}

/** Does `valor` FIT a CNPJ (numeric or alphanumeric)? */
export function cnpjValido(valor: string): boolean {
  return lerIdentificador("cnpj", valor).cabe;
}

/** A stored CPF-or-CNPJ rendered in its canonical PUNCTUATED form — the kind
 *  is told by the number itself (11 / 14 alphanumerics), as a stored
 *  `certidao_consultas.documento` or a `parte.documento` carries no other hint.
 *  A value that does not fit is shown as stored (visible, never hidden). */
export function formatarDocumentoArmazenado(doc: string | null | undefined): string {
  if (!doc) return "";
  const tamanho = doc.replace(/[^0-9A-Za-z]/g, "").length;
  if (tamanho === 11) return formatIdentificador("cpf", doc);
  if (tamanho === 14) return formatIdentificador("cnpj", doc);
  return doc;
}

/** The document to look up (its alphanumeric key — digits for a CPF and for a
 *  numeric CNPJ), or `null` while it is incomplete/invalid for the chosen kind
 *  of person. */
export function documentoParaLookup(valor: string, tipo: "PF" | "PJ"): string | null {
  const identificador = tipo === "PF" ? "cpf" : "cnpj";
  return lerIdentificador(identificador, valor).cabe
    ? chaveBuscaIdentificador(identificador, valor)
    : null;
}
