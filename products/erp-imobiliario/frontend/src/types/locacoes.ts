export type IndiceReajuste = 'IGPM' | 'IPCA' | 'INPC' | 'fixo';
export type StatusLocacao = 'ativo' | 'encerrado' | 'renovado' | 'inadimplente';

export interface ContratoLocacao {
  id: string;
  org_id: string;
  imovel_id: string;
  locatario_id: string;
  proprietario_id?: string | null;
  valor_aluguel: number;
  dia_vencimento: number;
  data_inicio: string;
  data_fim: string;
  indice_reajuste: IndiceReajuste;
  percentual_reajuste?: number | null;
  status: StatusLocacao;
  taxa_administracao: number;
  valor_caucao?: number | null;
  observacoes?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ContratoCreateData {
  imovel_id: string;
  locatario_id: string;
  proprietario_id?: string;
  valor_aluguel: number;
  dia_vencimento?: number;
  data_inicio: string;
  data_fim: string;
  indice_reajuste?: IndiceReajuste;
  percentual_reajuste?: number;
  taxa_administracao?: number;
  valor_caucao?: number;
  observacoes?: string;
}

export interface ContratoUpdateData {
  id: string;
  valor_aluguel?: number;
  dia_vencimento?: number;
  data_fim?: string;
  indice_reajuste?: IndiceReajuste;
  percentual_reajuste?: number;
  status?: StatusLocacao;
  taxa_administracao?: number;
  valor_caucao?: number;
  observacoes?: string;
}

export interface ReajusteResult {
  valor_anterior: number;
  valor_novo: number;
  diferenca: number;
  indice: string;
  percentual_aplicado: number;
  aplicado: boolean;
}

export interface RenovacaoResult {
  contrato_anterior: ContratoLocacao;
  contrato_novo: ContratoLocacao;
}

export type TipoVistoria = 'entrada' | 'saida' | 'periodica';
export type StatusVistoria = 'agendada' | 'em_andamento' | 'concluida' | 'cancelada';
export type EstadoChecklist = 'bom' | 'regular' | 'ruim' | 'NA';

export interface ChecklistItem {
  item: string;
  estado: EstadoChecklist;
  observacao: string;
}

export interface Vistoria {
  id: string;
  org_id: string;
  imovel_id: string;
  tipo: TipoVistoria;
  data_vistoria: string;
  responsavel_id: string;
  responsavel_nome?: string | null;
  status: StatusVistoria;
  checklist: ChecklistItem[];
  fotos: string[];
  observacoes_gerais?: string | null;
  assinatura_locatario?: string | null;
  resumo_checklist?: Record<string, number>;
  created_at: string;
  updated_at: string;
}

export interface VistoriaCreateData {
  imovel_id: string;
  tipo: TipoVistoria;
  data_vistoria: string;
  responsavel_id: string;
  responsavel_nome?: string;
  checklist?: ChecklistItem[];
  fotos?: string[];
  observacoes_gerais?: string;
}

export interface VistoriaUpdateData {
  id: string;
  tipo?: TipoVistoria;
  data_vistoria?: string;
  responsavel_id?: string;
  responsavel_nome?: string;
  status?: StatusVistoria;
  checklist?: ChecklistItem[];
  fotos?: string[];
  observacoes_gerais?: string;
  assinatura_locatario?: string;
}

export interface RankingCorretor {
  usuario_id: string;
  nome: string;
  email: string;
  total_clientes: number;
  clientes_fechados: number;
  valor_total_fechados: number;
  total_atividades: number;
}

export interface ConversaoFunil {
  etapa: string;
  label: string;
  total: number;
  taxa_conversao: number | null;
}

export interface AtividadeMensal {
  mes: string;
  periodo: string;
  total_atividades: number;
  novos_clientes: number;
  fechados: number;
}

export type ModoDistribuicao = 'manual' | 'round_robin' | 'por_regiao' | 'por_especialidade';

export interface DistribuicaoConfig {
  id?: string;
  org_id?: string;
  modo: ModoDistribuicao;
  corretores_ativos: string[];
  proximo_corretor_idx: number;
  regras: Record<string, any>;
  created_at?: string;
  updated_at?: string;
}

export interface CorretorFila {
  id: string;
  nome: string;
  email: string;
  is_next: boolean;
}

export interface FilaInfo {
  modo: ModoDistribuicao;
  corretores_ativos: CorretorFila[];
  proximo_corretor_id: string | null;
  proximo_corretor_idx: number;
  regras?: Record<string, any>;
}

export interface AtribuicaoResult {
  atribuido: boolean;
  corretor_id?: string;
  modo?: string;
  motivo?: string;
  cliente?: { id: string; nome: string };
}
