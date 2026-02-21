export type EtapaFunil = 'qualificacao' | 'visitas' | 'proposta' | 'negociacao' | 'fechado';

export type TipoAtividade = 'ligacao' | 'email' | 'reuniao' | 'whatsapp' | 'visita' | 'proposta' | 'negociacao' | 'outro';

export interface Cliente {
  id: string;
  usuario_id: string;
  nome: string;
  email?: string | null;
  telefone?: string | null;
  origem?: string | null;
  interesse?: string | null;
  observacoes?: string | null;
  etapa_atual: EtapaFunil;
  probabilidade: number;
  valor_estimado: number;
  arquivado: boolean;
  kanban_pos: number;
  created_at: string;
  updated_at: string;
  usuario?: {
    id: string;
    nome: string;
    email: string;
  };
}

export interface FunilMovimento {
  id: string;
  cliente_id: string;
  de_etapa?: EtapaFunil | null;
  para_etapa: EtapaFunil;
  responsavel_id: string;
  motivo?: string | null;
  created_at: string;
  responsavel?: {
    id: string;
    nome: string;
    email: string;
  };
}

export interface Atividade {
  id: string;
  cliente_id: string;
  usuario_id: string;
  tipo: TipoAtividade;
  descricao: string;
  data_execucao: string;
  created_at: string;
  usuario?: {
    id: string;
    nome: string;
    email: string;
  };
}

export interface ColunaFunil {
  etapa: EtapaFunil;
  total: number;
  valorTotal: number;
  cards: Cliente[];
}
