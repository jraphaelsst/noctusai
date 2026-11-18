/**
 * ImobShotAI error-code -> pt-BR message (contract §1, §4, §5). The FE branches on the error `code`, never on the
 * server message; the codes the contract lists with FE copy map to that exact copy, any other code (the lotes-route
 * ones: `modelo_nao_configurado`, `sem_tipos_edicao`, `economico_indisponivel`) keeps the server's own message
 * ("same messages as the lotes route"), and an error with neither gets `fallback`.
 */
import { ApiError } from "@noctusai/lib/api";
import { mensagemDoErro } from "@/components/card/mensagemDoErro";

export const MENSAGENS_IMOBSHOTAI: Record<string, string> = {
  sem_acesso_edicao_fotos: "Seu papel não dá acesso ao ImobShotAI.",
  imovel_inexistente: "Nenhum imóvel com esse código.",
  restrito_admin_organizacao: "Aguardando aprovação de um administrador.",
  card_nao_encontrado: "Esse imóvel não foi encontrado no ImobShotAI.",
};

export function codigoDoErro(err: unknown): string | null {
  return err instanceof ApiError ? err.code : null;
}

export function mensagemImobShotAI(err: unknown, fallback: string): string {
  const codigo = codigoDoErro(err);
  if (codigo && MENSAGENS_IMOBSHOTAI[codigo]) return MENSAGENS_IMOBSHOTAI[codigo];
  return mensagemDoErro(err, fallback);
}
