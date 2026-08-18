/**
 * Espelho manual dos schemas Pydantic do backend (`backend/app/schemas/`).
 * Mudou lá, muda aqui — não há geração automática de tipos de propósito: o
 * contrato é pequeno e revisá-lo à mão é o que mantém as duas pontas honestas.
 */

export interface Me {
  id: string;
  email: string;
  nome: string | null;
  org_id: string;
}

// ── Cadastros ──────────────────────────────────────────────────────────────

export interface Cliente {
  id: string;
  org_id: string;
  nome: string;
  empresa: string | null;
  corretor: string | null;
  email: string | null;
  telefone: string | null;
  cidade: string | null;
  estado: string | null;
  observacoes: string | null;
  ativo: boolean;
  /** Dados do pagador — obrigatórios para emitir cobrança. */
  cpf_cnpj: string | null;
  cep: string | null;
  endereco: string | null;
  bairro: string | null;
  provedor: string | null;
  provedor_cliente_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface ClienteMetricas {
  cliente_id: string;
  nome: string;
  empresa: string | null;
  faturamento_total: number;
  total_servicos: number;
  total_imoveis: number;
  ticket_medio: number;
  ultimo_servico: string | null;
  frequencia_mensal: number;
}

export type TipoImovel = "casa" | "apartamento" | "cobertura" | "terreno" | "comercial" | "galpao";
export type PadraoImovel = "alto" | "medio" | "economico";

export interface Imovel {
  id: string;
  org_id: string;
  cliente_id: string | null;
  codigo: string;
  endereco: string;
  condominio: string | null;
  cidade: string | null;
  estado: string | null;
  tipo: TipoImovel | string;
  padrao: PadraoImovel | string;
  area: number | null;
  dormitorios: number;
  banheiros: number;
  vagas: number;
  valor: number | null;
  maps_url: string | null;
  observacoes: string | null;
  created_at: string;
  updated_at: string;
}

export interface Servico {
  id: string;
  org_id: string;
  nome: string;
  categoria: string | null;
  preco: number;
  prazo_dias: number;
  descricao: string | null;
  ativo: boolean;
  created_at: string;
  updated_at: string;
}

export type CategoriaEquipamento =
  | "camera"
  | "lente"
  | "drone"
  | "microfone"
  | "gimbal"
  | "bateria"
  | "cartao"
  | "iluminacao"
  | "outro";

export interface Equipamento {
  id: string;
  org_id: string;
  nome: string;
  marca: string | null;
  modelo: string | null;
  numero_serie: string | null;
  categoria: CategoriaEquipamento | string | null;
  valor: number;
  quantidade: number;
  observacoes: string | null;
  ativo: boolean;
  created_at: string;
  updated_at: string;
}

// ── CRM comercial ──────────────────────────────────────────────────────────

export type EtapaNegocio =
  | "novo_lead"
  | "orcamento"
  | "negociacao"
  | "aprovado"
  | "agendamento"
  | "producao"
  | "entregue"
  | "recebido"
  | "arquivado";

export type FormaPagamento = "pix" | "boleto" | "cartao" | "transferencia";

export interface Etapa {
  id: string;
  label: string;
}

export interface NegocioServico {
  id: string;
  servico_id: string;
  nome: string | null;
  preco: number;
}

export interface Negocio {
  id: string;
  org_id: string;
  cliente_id: string;
  imovel_id: string | null;
  titulo: string | null;
  corretor: string | null;
  etapa: EtapaNegocio | string;
  valor: number;
  prazo_entrega: string | null;
  forma_pagamento: FormaPagamento | string | null;
  observacoes: string | null;
  created_at: string;
  updated_at: string;
  cliente_nome: string | null;
  imovel_endereco: string | null;
  servicos: NegocioServico[];
}

// ── Agenda ─────────────────────────────────────────────────────────────────

export type StatusCaptacao = "agendado" | "captado" | "cancelado";

export interface CaptacaoEquipamento {
  id: string;
  equipamento_id: string;
  nome: string | null;
  categoria: string | null;
  conferido: boolean;
}

export interface Captacao {
  id: string;
  org_id: string;
  negocio_id: string | null;
  cliente_id: string | null;
  imovel_id: string | null;
  data: string;
  hora: string;
  duracao_minutos: number;
  endereco: string;
  maps_url: string | null;
  responsavel: string | null;
  status: StatusCaptacao | string;
  observacoes: string | null;
  created_at: string;
  updated_at: string;
  cliente_nome: string | null;
  equipamentos: CaptacaoEquipamento[];
}

// ── Produção ───────────────────────────────────────────────────────────────

export type EtapaProducao =
  | "agendado"
  | "captado"
  | "backup"
  | "selecao"
  | "edicao"
  | "revisao"
  | "entregue"
  | "arquivado";

export interface ProducaoEvento {
  id: string;
  producao_id: string;
  etapa: string;
  tipo: "transicao" | "comentario" | "arquivo" | string;
  responsavel: string | null;
  comentario: string | null;
  arquivo_url: string | null;
  created_at: string;
}

export interface Producao {
  id: string;
  org_id: string;
  negocio_id: string | null;
  captacao_id: string | null;
  cliente_id: string | null;
  etapa: EtapaProducao | string;
  responsavel: string | null;
  prazo_entrega: string | null;
  entregue_em: string | null;
  observacoes: string | null;
  created_at: string;
  updated_at: string;
  cliente_nome: string | null;
  endereco: string | null;
  eventos: ProducaoEvento[];
}

// ── Financeiro ─────────────────────────────────────────────────────────────

/** Status armazenados. `atrasado` não está aqui: é derivado na leitura. */
export type StatusLancamento = "a_faturar" | "faturado" | "recebido" | "cancelado";
/** Status exibidos — inclui o derivado. */
export type StatusExibido = StatusLancamento | "atrasado";

export interface Lancamento {
  id: string;
  org_id: string;
  negocio_id: string | null;
  cliente_id: string;
  descricao: string | null;
  valor: number;
  status: StatusLancamento | string;
  status_exibido: StatusExibido | string;
  data_entrega: string | null;
  vencimento: string | null;
  pago_em: string | null;
  forma_pagamento: FormaPagamento | string | null;
  observacoes: string | null;
  created_at: string;
  updated_at: string;
  cliente_nome: string | null;
  /** Espelho da cobrança no provedor. Nulos enquanto não foi cobrado. */
  provedor: string | null;
  provedor_cobranca_id: string | null;
  provedor_status: string | null;
  url_fatura: string | null;
  linha_digitavel: string | null;
  pix_copia_e_cola: string | null;
  sincronizado_em: string | null;
}

/** Forma pedida na emissão. `indefinido` deixa o pagador escolher na fatura. */
export type FormaCobranca = "pix" | "boleto" | "cartao" | "indefinido";

export interface ResumoFinanceiro {
  faturamento_total: number;
  recebido: number;
  em_aberto: number;
  atrasado: number;
  receita_mes: number;
  receita_ano: number;
  ticket_medio: number;
  clientes_inadimplentes: number;
}

export interface ReceitaCliente {
  cliente_id: string;
  nome: string | null;
  valor: number;
}

// ── Dashboard ──────────────────────────────────────────────────────────────

export interface SerieMensal {
  mes: string;
  label: string;
  valor: number;
}

export interface SerieSemanal {
  semana: string;
  captacoes: number;
}

export interface EtapaResumo {
  etapa: string;
  label: string;
  quantidade: number;
  valor: number;
}

export interface Dashboard {
  captacoes_mes: number;
  entregas_mes: number;
  servicos_andamento: number;
  faturamento_mes: number;
  a_receber: number;
  ticket_medio: number;
  clientes_ativos: number;
  prazo_medio_dias: number | null;
  taxa_recorrencia: number;
  receita_por_mes: SerieMensal[];
  captacoes_por_semana: SerieSemanal[];
  funil: EtapaResumo[];
}

// ── Integração de cobrança ─────────────────────────────────────────────────

/** Ambientes do provedor. `sandbox` é o default de um deploy que não escolheu. */
export type AmbienteProvedor = "sandbox" | "producao";

/**
 * Estado de UM ambiente, como o backend o devolve. Nunca carrega a chave de
 * API — só a máscara. O token do webhook tem rota própria.
 */
export interface CredencialAmbiente {
  ambiente: AmbienteProvedor;
  configurado: boolean;
  /** Preenchido quando a linha existe mas não decifra (ENCRYPTION_KEY trocada). */
  erro: string | null;
  api_key_mascarada: string | null;
  webhook_token_configurado: boolean;
  base_url: string;
  atualizado_em: string | null;
}

export interface StatusCredenciais {
  provedor: string;
  ambiente_ativo: AmbienteProvedor;
  ambientes: CredencialAmbiente[];
  /** `null` quando o deploy não sabe o próprio endereço público. */
  webhook_url: string | null;
}

/** Uma linha da fila de eventos do provedor (`p_studio.provedor_eventos`). */
export interface ProvedorEvento {
  id: string;
  provedor: string;
  evento_id: string | null;
  tipo: string | null;
  cobranca_id: string | null;
  lancamento_id: string | null;
  efeito: string | null;
  erro: string | null;
  processado_em: string | null;
  created_at: string;
}
