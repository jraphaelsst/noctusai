/**
 * pt-BR copy for the stable error CODES orbity's backend answers with.
 *
 * An HTTP error body is a code, never exception text (owner rule 2026-11-11); the words the user reads live here.
 * An unknown code falls back to the server's string / transport message unchanged, so a refusal is never silent and never blank.
 */
export const ERROR_COPY: Record<string, string> = {
  flow_or_lead_not_found: "Fluxo ou lead não encontrado.",
  plan_reference_invalid: "Cliente, campanha ou item informado não existe ou não pertence ao planejamento.",
  post_not_promotable: "Este conteúdo não pode virar post: ele já virou post, foi descartado ou falta definir a plataforma.",
  invalid_stage: "Etapa inválida para este funil.",
  lead_not_found: "Lead não encontrado.",
  capture_stage_invalid: "A etapa informada não pertence a esta organização.",
  invalid_month: "Mês inválido.",
  ad_account_not_found: "Conta de anúncios não encontrada.",
  report_not_found: "Relatório não encontrado.",
  cliente_nao_encontrado: "Cliente não encontrado.",
  cobranca_nao_encontrada: "Cobrança não encontrada.",
  cobranca_ja_gerada: "A cobrança já foi gerada no gateway (ou está sendo gerada).",
  recebivel_nao_aberto: "Só um recebível em aberto pode ser enviado ao gateway.",
  cobranca_nao_enfileirada: "Não foi possível enfileirar a cobrança.",
  valor_invalido: "O valor deve ser maior que zero.",
  financeiro_indisponivel: "Não foi possível lançar o recebível.",
  cobranca_invalida: "Uma das cobranças informadas não está em aberto para este cliente.",
  acao_invalida: "A ação de cada cobrança deve ser 'cancel' ou 'keep'.",
  cobrancas_em_aberto: "Decida o destino de todas as cobranças em aberto do cliente.",
  cobranca_parcialmente_paga: "Uma cobrança com pagamento parcial não pode ser cancelada: mantenha-a.",
};

/** The user-facing text for a failed request: the mapped copy for a known server code, else the server's own curated string, else the error's own message. */
export function errorCopy(err: unknown): string | undefined {
  // The seed envelope is `{error: {code, message}}` (message = the backend's code); some seed refusals are flat `{detail}`.
  const body = (err as { body?: { detail?: unknown; error?: { message?: unknown } } } | null)?.body;
  const detail = body?.error?.message ?? body?.detail;
  if (typeof detail === "string") return ERROR_COPY[detail] ?? detail;
  return err instanceof Error ? err.message : undefined;
}
