export interface Notificacao {
  id: string;
  org_id: string;
  user_id: string;
  tipo: string;
  titulo: string;
  mensagem?: string | null;
  is_read: boolean;
  link?: string | null;
  created_at: string;
}

export interface NotificacaoPreferencia {
  id: string;
  org_id: string;
  user_id: string;
  canal: 'app' | 'email' | 'whatsapp';
  tipo_evento: string;
  ativo: boolean;
  created_at: string;
}

export interface ContagemNaoLidas {
  nao_lidas: number;
}
