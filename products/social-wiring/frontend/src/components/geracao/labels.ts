/** pt-BR labels for the Geração (Criação de Mídia) vocabularies (contract §4.8). */
import type {
  Gatilho,
  GeracaoStatus,
  Headline,
  LoteOrigem,
  RoteiroStatus,
} from "@/types/geracao";

export type StatusGeracao = GeracaoStatus | RoteiroStatus;

export const STATUS_ROTULO: Record<StatusGeracao, string> = {
  criando: "Criando",
  perguntas: "Perguntas",
  processando: "Processando",
  completo: "Completo",
  falha: "Falha",
};

/** Statuses that are still moving (the UI polls while any item is here). */
export function emAndamento(status: StatusGeracao): boolean {
  return status === "criando" || status === "processando";
}

export const ORIGEM_ROTULO: Record<LoteOrigem, string> = {
  form_me: "Sobre mim",
  form_public: "Meu público",
  form_viral: "Assuntos virais",
  biblioteca: "Biblioteca",
  sugestao_auto: "Sugestão automática",
};

export const GATILHO_ROTULO: Record<Gatilho, string> = {
  recompensa: "Recompensa",
  misterio: "Mistério",
  reconhecimento: "Reconhecimento",
  popularidade: "Popularidade",
  crenca: "Crença",
  autoridade: "Autoridade",
  disrupcao: "Disrupção",
};

export const MODO_ROTULO: Record<NonNullable<Headline["modo"]>, string> = {
  automatico: "Automático",
  manual: "Manual",
};

export const CRIATIVIDADE_ROTULO = {
  essencial: "Essencial",
  equilibrado: "Equilibrado",
  explorador: "Explorador",
} as const;

export const HEADLINE_TEXTO_MAX = 500;
