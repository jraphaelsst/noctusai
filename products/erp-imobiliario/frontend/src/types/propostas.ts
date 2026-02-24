export type StatusProposta = 'enviada' | 'em_analise' | 'contraproposta' | 'aceita' | 'recusada' | 'expirada';

export interface HistoricoProposta {
  action: string;
  timestamp: string;
  user_id?: string;
  details?: Record<string, any>;
}

export interface Proposta {
  id: string;
  imovel_id: string;
  cliente_id: string;
  corretor_id: string;
  valor_proposta: number;
  valor_contraproposta?: number;
  status: StatusProposta;
  condicoes_pagamento?: string;
  prazo_validade?: string;
  observacoes?: string;
  historico: HistoricoProposta[];
  created_at: string;
  updated_at: string;
}

export interface PropostaStats {
  total: number;
  enviada: number;
  em_analise: number;
  contraproposta: number;
  aceita: number;
  recusada: number;
  expirada: number;
}

export interface PropostaCreateData {
  imovel_id: string;
  cliente_id: string;
  valor_proposta: number;
  condicoes_pagamento?: string;
  prazo_validade?: string;
  observacoes?: string;
}

export interface PropostaUpdateData {
  id: string;
  status?: StatusProposta;
  valor_proposta?: number;
  valor_contraproposta?: number;
  condicoes_pagamento?: string;
  prazo_validade?: string;
  observacoes?: string;
}

export interface ContrapropostaData {
  proposta_id: string;
  valor_contraproposta: number;
  condicoes_pagamento?: string;
  observacoes?: string;
}
