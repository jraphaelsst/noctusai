export type TipoLancamento = 'receita' | 'despesa';

export type StatusLancamento = 'pendente' | 'pago' | 'atrasado' | 'cancelado';

export interface Lancamento {
  id: string;
  tipo: TipoLancamento;
  categoria: string;
  descricao: string;
  valor: number;
  data_vencimento: string;
  data_pagamento?: string;
  status: StatusLancamento;
  forma_pagamento?: string;
  imovel_id?: string;
  cliente_id?: string;
  comissao_id?: string;
  recorrente: boolean;
  observacoes?: string;
  created_at: string;
  updated_at: string;
}

export interface ResumoFinanceiro {
  receitas: number;
  despesas: number;
  saldo: number;
  atrasados: number;
}

export interface FluxoCaixa {
  mes: string;
  receitas: number;
  despesas: number;
  saldo: number;
}

export interface LancamentoCreateData {
  tipo: TipoLancamento;
  categoria: string;
  descricao: string;
  valor: number;
  data_vencimento: string;
  data_pagamento?: string;
  status?: StatusLancamento;
  forma_pagamento?: string;
  imovel_id?: string;
  cliente_id?: string;
  recorrente?: boolean;
  observacoes?: string;
}

export interface LancamentoUpdateData {
  id: string;
  tipo?: TipoLancamento;
  categoria?: string;
  descricao?: string;
  valor?: number;
  data_vencimento?: string;
  data_pagamento?: string;
  status?: StatusLancamento;
  forma_pagamento?: string;
  imovel_id?: string;
  cliente_id?: string;
  recorrente?: boolean;
  observacoes?: string;
}
