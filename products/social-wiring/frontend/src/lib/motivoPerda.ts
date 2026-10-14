/**
 * Closed set of reasons a funil deal (`atendimentos`) is marked lost.
 *
 * The snake_case keys are the CONTRACT with the backend (`MotivoPerdaCategoria`
 * in `pipeline/routers/boards.py` + the CHECK in migration 263) — the
 * pt-BR labels live here only. `outro` is the one category that requires the
 * free-text note.
 */
export const MOTIVOS_PERDA = [
  { value: "preco_acima_mercado", label: "Preço acima do mercado" },
  { value: "cliente_desistiu", label: "Cliente desistiu da compra" },
  { value: "comprou_outro_imovel", label: "Comprou outro imóvel" },
  { value: "comprou_com_concorrente", label: "Fechou com outra imobiliária" },
  { value: "financiamento_negado", label: "Financiamento/crédito negado" },
  { value: "documentacao_imovel", label: "Problema de documentação do imóvel" },
  { value: "proprietario_desistiu", label: "Proprietário desistiu da venda" },
  { value: "imovel_vendido_outro", label: "Imóvel vendido para outro comprador" },
  { value: "sem_retorno", label: "Cliente sem retorno" },
  { value: "outro", label: "Outro" },
] as const;

export type MotivoPerdaCategoria = (typeof MOTIVOS_PERDA)[number]["value"];

export function motivoPerdaLabel(categoria: string | null | undefined): string | null {
  if (!categoria) return null;
  return MOTIVOS_PERDA.find((m) => m.value === categoria)?.label ?? categoria;
}

/** `outro` has no meaning without the operator's own words. */
export function exigeObservacao(categoria: MotivoPerdaCategoria | ""): boolean {
  return categoria === "outro";
}
