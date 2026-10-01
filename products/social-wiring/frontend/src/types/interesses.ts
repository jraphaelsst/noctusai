/**
 * Types for the interesse / propriedade / interessados / similares surfaces
 * (`atendimento-partes-imoveis-CONTRACT.md` §0.1, §0.2, §4.1-§4.4).
 * snake_case kept 1:1 with the wire (CONTRACT §6) — no camelCase mapping.
 */
import type { ImovelVisita } from "@/types/cardHub";

/** CONTRACT §0.1 — `ImovelVisita` (the existing enriched keys) plus the
 *  additive keys BE-imoveis ships. Every additive key is optional here because
 *  the backend lands in parallel; a missing key renders as "—", never crashes. */
export interface ImovelResumo extends ImovelVisita {
  categoria?: string | null;
  valor_venda?: number | null;
  valor_locacao?: number | null;
  dormitorios?: number | null;
  suites?: number | null;
  vagas?: number | null;
  area_total?: number | null;
  area_privativa?: number | null;
  area_construida?: number | null;
  endereco?: string | null;
  valor?: number | null;
  valor_tipo?: "venda" | "locacao" | null;
}

/** CONTRACT §0.2. */
export interface ImovelLinhaPessoa {
  id: string;
  codigo: string;
  origem: string;
  created_at: string;
  created_by: string | null;
  imovel: ImovelResumo;
}

export type InteresseOrigem = "lead" | "manual" | "campanha" | "roteiro" | "permuta";

/** CONTRACT §4.1 `Item`. */
export interface InteresseItem extends ImovelLinhaPessoa {
  origem: InteresseOrigem;
  lead_id: string | null;
  meta_ads_lead_id: string | null;
}

/** `POST /api/clientes/{id}/interesses` body — `lead`/`roteiro` are 422. */
export interface InteresseCriarBody {
  codigo: string;
  origem?: "manual" | "campanha" | "permuta";
}

/** CONTRACT §4.2 (`origem ∈ manual|matricula|atendimento`). */
export type PropriedadeItem = ImovelLinhaPessoa;

export interface ItemsTotal<T> {
  items: T[];
  total: number;
}

/** CONTRACT §4.2 `GET /api/imoveis/{codigo}/proprietarios` item. */
export interface ProprietarioDoImovel {
  id: string;
  tipo_pessoa: "PF" | "PJ";
  cliente_id: string | null;
  empresa_id: string | null;
  nome: string;
  documento: string | null;
  celular: string | null;
  email: string | null;
  origem: "manual" | "matricula" | "atendimento";
  created_at: string | null;
}

/** CONTRACT §4.3 `Row`. */
export interface InteressadoRow {
  interesse_id: string;
  cliente_id: string;
  nome: string;
  telefone: string | null;
  email: string | null;
  origem: InteresseOrigem;
  interesse_created_at: string;
  lead_created_at: string | null;
  ultima_interacao_em: string | null;
  tem_atendimento_aberto: boolean;
  atendimento_aberto_id: string | null;
}

/** CONTRACT §4.4 item. */
export interface SimilarItem extends ImovelResumo {
  score: number;
  justificativa: string;
  reasons: string[];
  detalhes?: Record<string, unknown>;
  score_breakdown?: Record<string, unknown>;
}

export interface SimilaresResponse extends ItemsTotal<SimilarItem> {
  sem_semantica: number;
  aviso?: string;
}
