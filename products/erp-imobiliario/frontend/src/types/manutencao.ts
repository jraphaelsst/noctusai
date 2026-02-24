export type TipoOrdem = 'preventiva' | 'corretiva' | 'emergencial' | 'reforma';
export type PrioridadeOrdem = 'baixa' | 'media' | 'alta' | 'urgente';
export type StatusOrdem = 'aberto' | 'em_andamento' | 'aguardando' | 'concluido' | 'cancelado';

export interface OrdemServico {
  id: string;
  imovel_id?: string;
  cliente_id?: string;
  titulo: string;
  descricao: string;
  tipo: TipoOrdem;
  prioridade: PrioridadeOrdem;
  status: StatusOrdem;
  responsavel?: string;
  fornecedor?: string;
  custo_estimado?: number;
  custo_real?: number;
  data_abertura: string;
  data_previsao?: string;
  data_conclusao?: string;
  fotos: string[];
  observacoes?: string;
  created_at: string;
  updated_at: string;
}

export interface ResumoManutencao {
  por_status: Record<string, number>;
  tempo_medio_resolucao: number;
  atrasados: number;
  custo_total: number;
}

export interface OrdemServicoCreateData {
  titulo: string;
  descricao: string;
  tipo: TipoOrdem;
  prioridade?: PrioridadeOrdem;
  imovel_id?: string;
  cliente_id?: string;
  responsavel?: string;
  fornecedor?: string;
  custo_estimado?: number;
  data_abertura: string;
  data_previsao?: string;
  fotos?: string[];
  observacoes?: string;
}

export interface OrdemServicoUpdateData {
  id: string;
  titulo?: string;
  descricao?: string;
  tipo?: TipoOrdem;
  prioridade?: PrioridadeOrdem;
  status?: StatusOrdem;
  responsavel?: string;
  fornecedor?: string;
  custo_estimado?: number;
  custo_real?: number;
  data_previsao?: string;
  data_conclusao?: string;
  fotos?: string[];
  observacoes?: string;
}
