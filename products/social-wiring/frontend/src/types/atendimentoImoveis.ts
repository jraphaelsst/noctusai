/**
 * Imóveis linked to an atendimento (contract §3, §0.1). Owned by FE-leads-partes.
 */

/** §0.1 `ImovelResumo` — the keys this slice reads; extras are tolerated. */
export interface ImovelResumo {
  codigo: string;
  titulo?: string | null;
  empreendimento?: string | null;
  bairro?: string | null;
  cidade?: string | null;
  uf?: string | null;
  foto_destaque?: string | null;
  registrado?: boolean;
  fonte?: string | null;
  categoria?: string | null;
  endereco?: string | null;
  valor?: number | null;
  valor_tipo?: "venda" | "locacao" | null;
}

export type AtendimentoImovelOrigem = "lead" | "manual" | "campanha" | "negociacao";

/** §3.1 `Item`. */
export interface AtendimentoImovel {
  id: string;
  codigo: string;
  origem: AtendimentoImovelOrigem;
  principal: boolean;
  em_negociacao: boolean;
  created_at: string | null;
  created_by: string | null;
  imovel: ImovelResumo;
}

export interface AtendimentoImoveisResponse {
  items: AtendimentoImovel[];
  total: number;
  atendimento_id: string | null;
  imovel_pendente: boolean;
}

/** §3.2 body — `lead`/`negociacao` origins are system-only (422). */
export interface AtendimentoImovelCreateBody {
  codigo: string;
  principal?: boolean;
  origem?: "manual" | "campanha";
  atendimento_id?: string;
}
