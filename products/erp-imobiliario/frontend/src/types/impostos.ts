export type TipoImposto = 'iptu' | 'itbi' | 'txa_lixo' | 'contribuicao_melhoria' | 'outro';
export type StatusImposto = 'pendente' | 'parcial' | 'pago' | 'atrasado' | 'isento';

export interface Imposto {
  id: string;
  imovel_id: string;
  tipo: TipoImposto;
  ano: number;
  valor_total: number;
  valor_pago: number;
  num_parcelas: number;
  parcela_atual: number;
  desconto_cota_unica: number;
  data_vencimento: string;
  status: StatusImposto;
  numero_guia?: string;
  comprovante_url?: string;
  observacoes?: string;
  created_at: string;
  updated_at: string;
}

export interface ResumoImpostos {
  total_devido: number;
  total_pago: number;
  total_pendente: number;
  total_atrasado: number;
  count_by_status: Record<string, number>;
  quantidade: number;
}

export interface ImpostoCreateData {
  imovel_id: string;
  tipo: TipoImposto;
  ano: number;
  valor_total: number;
  valor_pago?: number;
  num_parcelas?: number;
  parcela_atual?: number;
  desconto_cota_unica?: number;
  data_vencimento: string;
  status?: StatusImposto;
  numero_guia?: string;
  comprovante_url?: string;
  observacoes?: string;
}

export interface ImpostoUpdateData {
  id: string;
  valor_pago?: number;
  parcela_atual?: number;
  status?: StatusImposto;
  numero_guia?: string;
  comprovante_url?: string;
  observacoes?: string;
}
