export interface Profile {
  id: string;
  nome: string;
  email: string;
  telefone: string;
  avatar?: string;
  created_at: string;
  updated_at: string;
}

// Alias para manter compatibilidade
export type Corretor = Profile;

export type TipoMeta = 'diaria' | 'semanal' | 'mensal' | 'anual';

export type CategoriaMeta = 
  | 'captacao' 
  | 'captacao_imoveis' 
  | 'captacao_compradores' 
  | 'atualizacao_imoveis' 
  | 'visitas' 
  | 'propostas' 
  | 'fechamento'
  | 'contatos' // mantido para compatibilidade com dados antigos
  | 'outro';

export type StatusMeta = 'aberta' | 'concluida' | 'atrasada' | 'no_prazo' | 'vence_amanha';
export type NivelPerformanceMeta = 'baixo' | 'regular' | 'bom' | 'excelente';

export interface Meta {
  id: string;
  usuario_id: string;
  tipo: TipoMeta;
  categoria: CategoriaMeta;
  categoria_custom?: string;
  meta_pretendida: number;
  meta_realizada?: number;
  data_prazo: string;
  status: StatusMeta;
  nivel_performance: NivelPerformanceMeta;
  created_at: string;
  updated_at: string;
  finalizada_em?: string;
  finalizada_no_prazo?: boolean;
  conclusao_prazo?: 'no_prazo' | 'atrasada';
  carry_in?: number;
  carry_out?: number;
  tem_impedimento: boolean;
  motivo_impedimento?: string;
  dias_restantes?: number;
  detalhes?: string;
  criada_manualmente: boolean;
  nome?: string;
  usuario?: {
    id: string;
    nome: string;
    email: string;
  };
}

// Form types
export interface NovoUsuarioForm {
  nome: string;
  email: string;
  telefone: string;
  password: string;
}

export interface NovaMetaForm {
  usuario_id: string;
  tipo: TipoMeta;
  categoria: CategoriaMeta;
  categoria_custom?: string;
  meta_pretendida: number;
  data_prazo?: string;
  detalhes?: string;
  nome?: string;
}
