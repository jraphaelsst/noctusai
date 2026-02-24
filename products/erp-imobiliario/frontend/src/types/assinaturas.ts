export type StatusAssinatura = 'pendente' | 'enviado' | 'assinado' | 'recusado' | 'expirado' | 'cancelado';
export type ProvedorAssinatura = 'interno' | 'clicksign' | 'docusign' | 'd4sign';

export interface Signatario {
  nome: string;
  email: string;
  papel: string;
  status?: string;
}

export interface Assinatura {
  id: string;
  documento_nome: string;
  documento_url?: string;
  contrato_id?: string;
  status: StatusAssinatura;
  provedor: ProvedorAssinatura;
  link_assinatura?: string;
  signatarios: Signatario[];
  historico: Array<{ evento: string; data: string; detalhes?: string }>;
  data_envio?: string;
  data_assinatura?: string;
  data_expiracao?: string;
  created_at: string;
  updated_at: string;
}

export interface ResumoAssinaturas {
  pendentes: number;
  enviadas: number;
  assinadas: number;
  recusadas: number;
  expiradas: number;
  canceladas: number;
  total: number;
}

export interface EnviarAssinaturaData {
  documento_nome: string;
  documento_url?: string;
  contrato_id?: string;
  signatarios: Signatario[];
  provedor?: ProvedorAssinatura;
}
