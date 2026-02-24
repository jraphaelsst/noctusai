export type TipoContrato = 'venda' | 'locacao';

export type StatusContrato = 'rascunho' | 'ativo' | 'concluido' | 'cancelado' | 'distratado';

export type StatusParcela = 'pendente' | 'pago' | 'atrasado' | 'cancelado';

export interface Contrato {
  id: string;
  tipo: TipoContrato;
  status: StatusContrato;
  cliente_id: string;
  imovel_id: string;
  proposta_id?: string;
  valor_total: number;
  valor_entrada: number;
  num_parcelas: number;
  data_inicio: string;
  data_fim?: string;
  data_assinatura?: string;
  observacoes?: string;
  created_at: string;
  updated_at: string;
}

export interface ParcelaContrato {
  id: string;
  contrato_id: string;
  numero: number;
  valor: number;
  data_vencimento: string;
  data_pagamento?: string;
  status: StatusParcela;
  forma_pagamento?: string;
  created_at: string;
}

export interface ResumoContratos {
  por_status: Record<string, number>;
  por_tipo: Record<string, number>;
  valor_total: number;
  inadimplencia: {
    total_parcelas: number;
    parcelas_atrasadas: number;
    valor_atrasado: number;
    taxa_inadimplencia: number;
  };
}

export interface ContratoCreateData {
  tipo: TipoContrato;
  cliente_id: string;
  imovel_id: string;
  proposta_id?: string;
  valor_total: number;
  valor_entrada?: number;
  num_parcelas?: number;
  data_inicio: string;
  data_fim?: string;
  data_assinatura?: string;
  observacoes?: string;
}

export interface ContratoUpdateData {
  id: string;
  tipo?: TipoContrato;
  status?: StatusContrato;
  cliente_id?: string;
  imovel_id?: string;
  valor_total?: number;
  valor_entrada?: number;
  num_parcelas?: number;
  data_inicio?: string;
  data_fim?: string;
  data_assinatura?: string;
  observacoes?: string;
}
