/**
 * Negociação de Venda — the Funil board's card entity.
 *
 * Mirrors the backend DTO whitelist in
 * `backend/app/services/negociacoes_venda_service.py::_NEGOCIACAO_DTO_FIELDS`.
 *
 * NOT the same as `Negociacao` in `@/types/negociacoes-permuta` — that is the
 * property-SWAP domain. This is a sales deal. The names collide because the
 * domain word does; see the roadmap anti-goals.
 */
import type { EtapaFunil } from '@/types/clientes';

/** Terminal-state vocabulary — mirrors `erp.status_negociacao_venda`. */
export type StatusNegociacao = 'aberta' | 'aceita' | 'perdida';

export interface NegociacaoVenda {
  id: string;
  cliente_id: string;
  corretor_id: string;
  titulo?: string | null;
  etapa: EtapaFunil;
  status: StatusNegociacao;
  valor_estimado: number;
  probabilidade: number;
  kanban_pos: number;
  arquivado: boolean;
  /** Set when `status` leaves 'aberta'. The cycle-time substrate. */
  closed_at?: string | null;
  created_at: string;
  updated_at: string;
  /** Nested join — the person the deal is for. */
  cliente?: {
    id: string;
    nome: string;
    email?: string | null;
    telefone?: string | null;
    origem?: string | null;
  };
  /** Nested join — the corretor who owns the deal. */
  corretor?: {
    id: string;
    nome: string;
    email?: string | null;
  };
}

/** One kanban column of the Funil board. */
export interface ColunaNegociacoes {
  etapa: EtapaFunil;
  total: number;
  valorTotal: number;
  cards: NegociacaoVenda[];
}
