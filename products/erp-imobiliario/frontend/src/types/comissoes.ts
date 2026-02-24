export type ComissaoStatus = 'pendente' | 'aprovada' | 'paga' | 'cancelada';

export interface ComissaoSplit {
  id: string;
  comissao_id: string;
  corretor_id: string;
  corretor_nome: string;
  percentual: number;
  valor: number;
  created_at: string;
}

export interface Comissao {
  id: string;
  venda_id?: string | null;
  imovel_id?: string | null;
  valor_venda: number;
  percentual_comissao: number;
  valor_comissao: number;
  status: ComissaoStatus;
  data_venda?: string | null;
  data_pagamento?: string | null;
  observacoes?: string | null;
  splits?: ComissaoSplit[];
  created_at: string;
  updated_at: string;
}

export interface ComissaoResumoTotais {
  total_pendente: number;
  total_aprovada: number;
  total_paga: number;
  total_cancelada: number;
  total_geral: number;
  quantidade: number;
}

export interface ComissaoPorCorretor {
  corretor_id: string;
  corretor_nome: string;
  total_pendente: number;
  total_aprovada: number;
  total_paga: number;
  total_geral: number;
  quantidade: number;
}

export interface ComissaoResumo {
  totais: ComissaoResumoTotais;
  por_corretor: ComissaoPorCorretor[];
}

export interface SplitInput {
  corretor_id: string;
  corretor_nome: string;
  percentual: number;
}

export interface ComissaoCreateData {
  venda_id?: string;
  imovel_id?: string;
  valor_venda: number;
  percentual_comissao: number;
  data_venda?: string;
  observacoes?: string;
  splits?: SplitInput[];
}

export interface ComissaoUpdateData {
  status: ComissaoStatus;
  data_pagamento?: string;
  observacoes?: string;
}
