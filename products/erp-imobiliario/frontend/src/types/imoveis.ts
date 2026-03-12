export type StatusNegociacao = 'qualificacao' | 'visitas' | 'proposta' | 'negociacao' | 'fechado' | 'cancelado';

export interface Negociacao {
  id: string;
  owner_id: string;
  created_at: string;
  updated_at: string;

  // Vínculos com ativos
  ativo_origem_id: string;
  ativo_destino_id: string;
  cliente_proprietario_id: string;
  cliente_ofertante_id: string;

  // Proposta
  valor_imovel: number;
  valor_permuta: number;
  valor_complemento: number;
  status_etapa: StatusNegociacao;

  // Histórico
  timeline: Array<{ data: string; descricao: string; tipo?: string }>;
  observacoes?: string;
}
