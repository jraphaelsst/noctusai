export type TipoDocumento = 'contrato' | 'procuracao' | 'laudo' | 'certidao' | 'outro';

export interface Documento {
  id: string;
  nome: string;
  tipo: TipoDocumento;
  arquivo_url?: string;
  arquivo_path?: string;
  tamanho_bytes?: number;
  mime_type?: string;
  imovel_id?: string;
  cliente_id?: string;
  proposta_id?: string;
  template_id?: string;
  metadata: Record<string, unknown>;
  created_by: string;
  created_at: string;
}

export interface DocumentTemplate {
  id: string;
  nome: string;
  tipo: TipoDocumento;
  conteudo: string;
  variaveis: string[];
  is_active: boolean;
  created_at: string;
}

export interface DocumentoCreateData {
  nome: string;
  tipo: TipoDocumento;
  arquivo_url?: string;
  arquivo_path?: string;
  tamanho_bytes?: number;
  mime_type?: string;
  imovel_id?: string;
  cliente_id?: string;
  proposta_id?: string;
  metadata?: Record<string, any>;
}

export interface TemplateCreateData {
  nome: string;
  tipo: TipoDocumento;
  conteudo: string;
  variaveis?: string[];
  is_active?: boolean;
}

export interface GenerateDocumentData {
  template_id: string;
  variables: Record<string, string>;
  imovel_id?: string;
  cliente_id?: string;
  proposta_id?: string;
}
