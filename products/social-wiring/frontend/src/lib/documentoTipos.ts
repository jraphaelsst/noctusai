/**
 * Human labels for document types — one map per surface, one definition each.
 *
 * WHY THIS FILE EXISTS
 * --------------------
 * `useFinanciamento.ts` already carried `TIPO_LABEL` for the deal's paperwork.
 * The retention screen (Configurações → Retenção) needs the same labels plus
 * the cliente surface's, and a second copy of the first map is how the two
 * silently drift apart — one gets a new type, the other keeps showing the raw
 * slug. So both live here and `useFinanciamento` re-exports its half.
 *
 * 🔴 THE KEYS ARE THE SERVER'S CONTRACT, THE VALUES ARE FOR PEOPLE. A type
 * missing from a map falls back to its slug, which is ugly but readable —
 * never blank. Blank would look like a rendering bug; a slug looks like a
 * label nobody has written yet, which is exactly what it is.
 */

/** `atendimento_documentos` — the deal's closing paperwork (migration 078). */
export const TIPO_LABEL: Record<string, string> = {
  certidao_casamento: "Certidão de casamento",
  escritura_pacto: "Escritura do pacto",
  registro_pacto: "Registro do pacto",
  comprovante_residencia: "Comprovante de residência",
  imposto_renda_com_recibo: "Imposto de renda (com recibo de entrega)",
  carteira_trabalho: "Carteira de trabalho",
  extratos_fgts: "Extratos do FGTS",
  comprovante_residencia_1ano: "Comprovante de residência (há 1 ano)",
};

/** `cliente_documentos` — the client's own file (migration 057). */
export const TIPO_LABEL_CLIENTE: Record<string, string> = {
  contrato: "Contrato",
  proposta: "Proposta comercial",
  comprovante_pagamento: "Comprovante de pagamento",
  comprovante_endereco: "Comprovante de endereço",
  planta_imovel: "Planta do imóvel",
  foto_imovel: "Foto do imóvel",
  outro: "Outro documento",
  rg: "RG",
  cpf: "CPF",
};

/**
 * The label for one type on one surface, falling back to the slug.
 *
 * `superficie` is the same value the retention API uses, so a caller never has
 * to know which of the two maps to reach for.
 */
export function rotuloTipo(superficie: string, tipo: string): string {
  const map = superficie === "cliente" ? TIPO_LABEL_CLIENTE : TIPO_LABEL;
  return map[tipo] ?? tipo;
}
