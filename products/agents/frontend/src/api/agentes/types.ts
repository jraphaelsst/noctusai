/**
 * Wire types of the unified agent surface — `products/agents/projects/agents-unified/CONTRACT.md` §2/§4.
 * Mirrors `backend/app/schemas/agente_painel.py` (BE-owned; this file follows it).
 */
import type { EstadoExterno } from "@/hooks/useAgents";

export type AgenteOrigem = "legado" | "plataforma" | "instancia" | "org";
export type AgenteTier = "membro" | "org_admin" | "plataforma";

export interface CampoModelo {
  chave: string;
  rotulo: string;
  tipo: "texto" | "numero" | "booleano" | "escolha" | "lista" | "objeto";
  obrigatorio: boolean;
  max_length: number | null;
  /** Limits a form needs to block what the create route would 422 (read from the Pydantic field). */
  min_length?: number | null;
  pattern?: string | null;
  minimo?: number | null;
  minimo_exclusivo?: number | null;
  maximo?: number | null;
  /** The server's default for the field (scalars only). */
  padrao?: string | number | boolean | null;
  opcoes: string[] | null;
  modelo?: "plataforma" | "briefing" | null;
}

export interface SecaoModelo {
  id: string;
  titulo: string;
  grupo: "painel" | "conteudo" | "operacao" | "organizacao";
  tier: AgenteTier;
  origens: AgenteOrigem[];
  area: string | null;
  exige: string[];
}

export interface AreaModelo {
  id: string;
  titulo: string;
  descricao: string;
  ordem: number;
  multiplas_linhas: boolean;
  campos: CampoModelo[];
  enumeracao: Record<string, unknown> | null;
  secoes: string[];
}

export interface PassoAssistente {
  id: string;
  titulo: string;
  categoria: "quem" | "como" | "o_que" | "fechamento";
  descricao: string;
  ordem: number;
  campos: CampoModelo[];
  areas: string[];
  nota: string | null;
}

/** `GET /api/studio/modelo` */
export interface AgenteModelo {
  versao: number;
  tier: AgenteTier;
  conteudo_modo: "linhas";
  origens: AgenteOrigem[];
  secoes: SecaoModelo[];
  areas: AreaModelo[];
  assistente: { passos: PassoAssistente[] } | null;
}

/** `GET /api/agents/painel` items · `GET /api/agents/{key}/painel` */
export interface AgentePainel {
  key: string;
  nome: string;
  descricao: string | null;
  papel: string | null;
  capacidades: string[];
  origem: AgenteOrigem;
  tipo: string;
  runtime: string;
  owner_product: string | null;
  usa_canais: boolean;
  ativo: boolean;
  estado_externo: EstadoExterno | null;
  aviso: string | null;
  secoes: string[];
  pode_alternar: boolean;
}

export interface AgentesPainelResponse {
  items: AgentePainel[];
  total: number;
}

/** `GET /api/agents/{key}/painel/interno` — superadmin only (404 for anyone else, D31). */
export interface AgenteInterno {
  key: string;
  origem: AgenteOrigem;
  definition_scope: string;
  conteudo_modo: string;
  versao_ativa: number | null;
  tem_rascunho: boolean;
  publicacao_limiar: number | null;
  conteudo_status: Record<string, unknown> | null;
}
