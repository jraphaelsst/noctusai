export type FinalidadeImovel = 'venda' | 'aluguel';
export type TipoImovel = 'casa' | 'apartamento' | 'terreno' | 'comercial' | 'rural' | 'outro';
export type CategoriaPermuta = 'imovel' | 'movel';
export type TipoMovel = 'carro' | 'moto';
export type StatusNegociacao = 'qualificacao' | 'visitas' | 'proposta' | 'negociacao' | 'fechado' | 'cancelado';

export interface Imovel {
  id: string;
  owner_id: string;
  status: string;
  created_at: string;
  updated_at: string;
  
  // Comercial
  finalidade: FinalidadeImovel;
  preco_pedido: number;
  aceita_permutas: boolean;
  observacoes_negociacao?: string;
  
  // Localização
  cep: string;
  logradouro?: string;
  numero?: string;
  complemento?: string;
  bairro?: string;
  cidade?: string;
  estado?: string;
  latitude?: number;
  longitude?: number;
  
  // Especificações
  tipo: TipoImovel;
  area_privativa?: number;
  area_total?: number;
  quartos?: number;
  suites?: number;
  banheiros?: number;
  vagas?: number;
  andar?: number;
  condominio?: number;
  iptu?: number;
  condominio_nome?: string;
  ano_construcao?: number;
  
  // Mídia
  fotos: string[];
  tour_virtual_url?: string;
  plantas: string[];
  titulo_anuncio?: string;
  descricao_seo?: string;
  palavras_chave: string[];
  pontos_de_interesse: string[];
  
  // Qualidade
  pronto_para_portais: boolean;
  lqs_score_hint?: string;
  
  // Relacionamentos
  perfis_permutas?: PerfilPermuta[];
}

export interface PerfilPermuta {
  id: string;
  cliente_ofertante_id: string;
  status: string;
  created_at: string;
  updated_at: string;
  
  // Tipo
  categoria: CategoriaPermuta;
  
  // Se imóvel
  tipo_imovel?: TipoImovel;
  faixa_preco_min?: number;
  faixa_preco_max?: number;
  regiao_preferida: string[];
  metragem_min?: number;
  metragem_max?: number;
  quartos_min?: number;
  vagas_min?: number;
  
  // Se móvel
  tipo_movel?: TipoMovel;
  marca?: string;
  modelo?: string;
  ano_min?: number;
  ano_max?: number;
  quilometragem_max?: number;
  
  // Flexibilidade
  aceita_completar_diferenca: boolean;
  limite_complemento?: number;
  observacoes?: string;
  
  // Valor
  valor_estimado?: number;
}

export interface Negociacao {
  id: string;
  owner_id: string;
  created_at: string;
  updated_at: string;
  
  // Vínculos
  imovel_id: string;
  perfil_permuta_id: string;
  cliente_proprietario_id: string;
  cliente_ofertante_id: string;
  
  // Proposta
  valor_imovel: number;
  valor_permuta: number;
  valor_complemento: number;
  status_etapa: StatusNegociacao;
  
  // Histórico
  timeline: any[];
  observacoes?: string;
  
  // Relacionamentos
  imovel?: Imovel;
  perfil_permuta?: PerfilPermuta;
}

export interface MatchResult {
  score: number;
  imovel_id: string;
  perfil_permuta_id: string;
  justificativa: string;
  detalhes: {
    compatibilidade_regiao: number;
    compatibilidade_preco: number;
    compatibilidade_specs: number;
    qualidade_anuncio: number;
    gap_valor: number;
  };
  imovel?: Imovel;
  perfil_permuta?: PerfilPermuta;
}

export interface NovoImovelForm {
  finalidade: FinalidadeImovel;
  preco_pedido: number;
  aceita_permutas: boolean;
  observacoes_negociacao?: string;
  
  cep: string;
  logradouro?: string;
  numero?: string;
  complemento?: string;
  bairro?: string;
  cidade?: string;
  estado?: string;
  
  tipo: TipoImovel;
  area_privativa?: number;
  area_total?: number;
  quartos?: number;
  suites?: number;
  banheiros?: number;
  vagas?: number;
  andar?: number;
  condominio?: number;
  iptu?: number;
  condominio_nome?: string;
  ano_construcao?: number;
  
  titulo_anuncio?: string;
  descricao_seo?: string;
  palavras_chave?: string[];
  pontos_de_interesse?: string[];
}

export interface NovoPerfilPermutaForm {
  categoria: CategoriaPermuta;
  
  // Imóvel
  tipo_imovel?: TipoImovel;
  faixa_preco_min?: number;
  faixa_preco_max?: number;
  regiao_preferida?: string[];
  metragem_min?: number;
  metragem_max?: number;
  quartos_min?: number;
  vagas_min?: number;
  
  // Móvel
  tipo_movel?: TipoMovel;
  marca?: string;
  modelo?: string;
  ano_min?: number;
  ano_max?: number;
  quilometragem_max?: number;
  
  // Flexibilidade
  aceita_completar_diferenca: boolean;
  limite_complemento?: number;
  observacoes?: string;
  valor_estimado?: number;
}
