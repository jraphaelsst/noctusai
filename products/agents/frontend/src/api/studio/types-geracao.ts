/**
 * Agent Studio — AI-generated first draft (S3a CONTRACT §1/§2). Shapes mirror the backend contract
 * exactly; `datetime` fields travel as ISO strings.
 */
export type GeracaoArea = "secoes" | "textos" | "ferramentas" | "decisoes" | "specs" | "skills" | "configuracoes" | "evals";
export const GERACAO_AREAS: GeracaoArea[] = ["secoes", "textos", "ferramentas", "decisoes", "specs", "skills", "configuracoes", "evals"];
export const GERACAO_AREA_LABEL: Record<GeracaoArea, string> = {
  secoes: "Seções do prompt",
  textos: "Textos do sistema",
  ferramentas: "Ferramentas",
  decisoes: "Decisões",
  specs: "Especificações",
  skills: "Skills",
  configuracoes: "Configurações",
  evals: "Casos de avaliação",
};

export type BriefingCanal = "whatsapp" | "web" | "interno";
export const BRIEFING_CANAIS: { id: BriefingCanal; label: string }[] = [
  { id: "whatsapp", label: "WhatsApp" },
  { id: "web", label: "Web" },
  { id: "interno", label: "Interno" },
];

export interface Briefing {
  nome: string;
  objetivo: string;
  publico: string;
  canal: BriefingCanal;
  idioma?: string;
  tom_de_voz?: string;
  limites?: string;
  exemplos?: string;
}

export type GeracaoStatus = "pendente" | "executando" | "concluida" | "parcial" | "falhou" | "cancelada";
export type GeracaoAreaStatus = "pendente" | "executando" | "concluida" | "falhou" | "pulado" | "cancelada";

export interface ItemGerado {
  chave: string;
  estado: "gerado" | "editado";
}

export interface GeracaoAreaOut {
  area: GeracaoArea;
  status: GeracaoAreaStatus;
  erro: string | null;
  custo_usd: number;
  itens_escritos: number;
  itens: ItemGerado[];
  lacunas: string[];
  concluido_em: string | null;
}

export interface GeracaoOut {
  id: string;
  agent_key: string;
  status: GeracaoStatus;
  versao_gerador: number | null;
  modelo: string;
  briefing: Briefing;
  custo_usd: number;
  limite_usd: number;
  criado_em: string;
  iniciado_em: string | null;
  concluido_em: string | null;
  erro: string | null;
  areas: GeracaoAreaOut[];
  /** The exemplar agent the run imitates (`null` = every exemplar). */
  referencia?: string | null;
}

export interface GeracoesList {
  items: GeracaoOut[];
}

/** `POST /agents/{key}/geracoes` body. */
export interface GeracaoCreateInput {
  briefing: Briefing;
  areas?: GeracaoArea[];
  forcar?: boolean;
  limite_usd?: number;
  /** Key of an EXEMPLAR agent to imitate instead of every exemplar (422 `referencia_invalida` otherwise). */
  referencia?: string;
}

/** `GET /agents/{key}` completeness signal (null for legado agents). */
export interface ConteudoStatusDetail {
  textos_preenchidos: number;
  textos_total: number;
  obrigatorios_faltando: string[];
}

export const GERACAO_ATIVA: GeracaoStatus[] = ["pendente", "executando"];
export const isGeracaoAtiva = (s: GeracaoStatus | undefined): boolean => !!s && GERACAO_ATIVA.includes(s);

export const LIMITE_USD_MAX = 5;
