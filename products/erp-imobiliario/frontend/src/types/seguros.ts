export type TipoCobertura = 'incendio' | 'completo' | 'responsabilidade_civil' | 'vida' | 'fianca_locaticia' | 'outro';
export type StatusSeguro = 'ativo' | 'vencido' | 'cancelado' | 'renovado';

export interface Seguro {
  id: string;
  imovel_id: string;
  cliente_id?: string;
  seguradora: string;
  numero_apolice?: string;
  tipo_cobertura: TipoCobertura;
  valor_cobertura: number;
  valor_premio: number;
  data_inicio: string;
  data_vencimento: string;
  status: StatusSeguro;
  auto_renovar: boolean;
  observacoes?: string;
  created_at: string;
  updated_at: string;
}

export interface ResumoSeguros {
  ativos: number;
  total_cobertura: number;
  total_premio_anual: number;
  vencendo_30d: number;
}

export interface SeguroCreateData {
  imovel_id: string;
  cliente_id?: string;
  seguradora: string;
  numero_apolice?: string;
  tipo_cobertura: TipoCobertura;
  valor_cobertura: number;
  valor_premio: number;
  data_inicio: string;
  data_vencimento: string;
  auto_renovar?: boolean;
  observacoes?: string;
}

export interface SeguroUpdateData {
  id: string;
  seguradora?: string;
  numero_apolice?: string;
  tipo_cobertura?: TipoCobertura;
  valor_cobertura?: number;
  valor_premio?: number;
  data_inicio?: string;
  data_vencimento?: string;
  status?: StatusSeguro;
  auto_renovar?: boolean;
  observacoes?: string;
}
