/** pt-BR labels the chat shows for the unified flow (Estruturas contract §9.1 / §11.1). */
import type { EstruturaFormato, FluxoEtapa } from "@/types/estruturas";

export const FORMATO_ROTULO: Record<EstruturaFormato, string> = {
  reels: "Reels",
  carrossel: "Carrossel",
  stories: "Stories",
  post: "Post",
};

export const ETAPA_ROTULO: Record<FluxoEtapa, string> = {
  headline_salva: "Headline salva",
  roteiro_gerando: "Escrevendo o roteiro...",
  roteiro_pronto: "Roteiro pronto",
  falhou: "Falhou",
};

export const LEGENDA_ROTULO = {
  pendente: "Legenda: sendo escrita",
  gerada: "Legenda gerada",
  indisponivel: "Legenda indisponível para este card",
} as const;

/** Why a flow failed, in plain pt-BR (the server's `erro_codigo`; unknown codes get the generic line). */
const ERRO_FLUXO: Record<string, string> = {
  ia_nao_configurada: "A IA ainda não está configurada para a sua organização.",
  orcamento_ia_excedido: "O orçamento de IA do período foi atingido.",
  geracao_indisponivel: "A geração está indisponível no momento.",
  limite_diario_roteiros: "Você atingiu o limite diário de roteiros.",
  headline_ja_em_post: "Esta headline já está em um card da Esteira.",
  roteiro_ja_em_post: "Este roteiro já está em um card da Esteira.",
};
export const erroDoFluxo = (codigo: string | null): string =>
  (codigo && ERRO_FLUXO[codigo]) || "Não foi possível concluir o roteiro.";
