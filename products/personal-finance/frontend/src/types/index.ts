export interface Conta {
  id: string;
  user_id: string;
  nome: string;
  tipo: string;
  instituicao?: string;
  saldo: number;
  moeda: string;
  cor: string;
  icone?: string;
  ativo: boolean;
  created_at: string;
  updated_at: string;
}

export interface Categoria {
  id: string;
  user_id?: string;
  nome: string;
  tipo: string;
  categoria_pai_id?: string;
  icone?: string;
  cor?: string;
  tipo_orcamento?: string;
  is_sistema: boolean;
  ordem: number;
  subcategorias?: Categoria[];
}

export interface Transacao {
  id: string;
  user_id: string;
  conta_id: string;
  conta_destino_id?: string;
  categoria_id?: string;
  data: string;
  valor: number;
  tipo: string;
  descricao?: string;
  comerciante?: string;
  notas?: string;
  tags?: string[];
  conta?: { id: string; nome: string; cor?: string; icone?: string };
  categoria?: { id: string; nome: string; icone?: string; cor?: string };
  created_at: string;
}

export interface Orcamento {
  id: string;
  user_id: string;
  nome: string;
  metodo: string;
  periodo: string;
  ativo: boolean;
  created_at: string;
}

export interface OrcamentoItem {
  id: string;
  orcamento_id: string;
  categoria_id: string;
  valor_planejado: number;
  periodo_mes: string;
  valor_gasto: number;
  rollover: number;
  categoria?: Categoria;
}

export interface Meta {
  id: string;
  user_id: string;
  nome: string;
  tipo: string;
  valor_alvo: number;
  valor_atual: number;
  data_alvo?: string;
  conta_vinculada_id?: string;
  prioridade: string;
  status: string;
  icone?: string;
  cor?: string;
  percentual?: number;
  created_at: string;
}

export interface Carteira {
  id: string;
  user_id: string;
  nome: string;
  tipo: string;
  corretora?: string;
  ativo: boolean;
  valor_total?: number;
  ganho_perda_total?: number;
  total_ativos?: number;
  created_at: string;
}

export interface Ativo {
  id: string;
  carteira_id: string;
  user_id: string;
  ticker: string;
  nome?: string;
  tipo: string;
  quantidade: number;
  preco_medio: number;
  preco_atual: number;
  valor_atual: number;
  ganho_perda: number;
  ganho_perda_pct: number;
  setor?: string;
  last_update?: string;
}

export interface Operacao {
  id: string;
  carteira_id: string;
  ativo_id?: string;
  user_id: string;
  ticker: string;
  tipo: string;
  data: string;
  quantidade?: number;
  preco_unitario?: number;
  taxas: number;
  valor_total: number;
  notas?: string;
  created_at: string;
}

export interface Recorrente {
  id: string;
  user_id: string;
  conta_id?: string;
  nome: string;
  valor: number;
  categoria_id?: string;
  tipo: string;
  frequencia: string;
  dia_vencimento?: number;
  proxima_data?: string;
  is_automatico: boolean;
  comerciante?: string;
  lembrete_dias: number;
  ativo: boolean;
  conta?: { id: string; nome: string };
  categoria?: Categoria;
}

export interface PatrimonioSnapshot {
  id: string;
  data: string;
  total_ativos: number;
  total_passivos: number;
  patrimonio_liquido: number;
  detalhamento?: any;
}

export interface DashboardKPIs {
  patrimonio_liquido: number;
  total_ativos: number;
  total_passivos: number;
  receita_mensal: number;
  despesa_mensal: number;
  fluxo_caixa_mensal: number;
  taxa_poupanca: number;
  retorno_investimentos: number;
  valor_investimentos: number;
}

export interface DashboardResumo {
  transacoes_recentes: Transacao[];
  proximas_contas: Recorrente[];
  metas_ativas: Meta[];
}

export interface Cotacao {
  ticker: string;
  preco: number;
  variacao: number;
  variacao_pct: number;
  volume: number;
  max_dia: number;
  min_dia: number;
  max_52s: number;
  min_52s: number;
  timestamp: string;
  fonte: string;
}

export interface WatchlistItem {
  id: string;
  watchlist_id: string;
  ticker: string;
  nome?: string;
  alerta_preco_acima?: number;
  alerta_preco_abaixo?: number;
  notas?: string;
}

export interface Watchlist {
  id: string;
  user_id: string;
  nome: string;
  itens?: WatchlistItem[];
  created_at: string;
}
