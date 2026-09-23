/**
 * igig CRM wire types — typed from the wave-2 contract
 * (`project-history/roadmaps/cardhub-igig-crm-2026-09.wave-2-contract.md`
 * § Shapes). The contract is the source of truth; the backend slices (A, B,
 * E2) build to the same shapes in parallel.
 *
 * Money = numeric BRL (JSON number). Dates ISO-8601.
 */

// ─── Catálogo ──────────────────────────────────────────────────────────────

export type Secao = "criacao_conteudo" | "gestao_conta";

export const SECOES: readonly Secao[] = ["criacao_conteudo", "gestao_conta"] as const;

export const SECAO_LABEL: Record<Secao, string> = {
  criacao_conteudo: "Criação de conteúdo",
  gestao_conta: "Gestão de conta",
};

export interface ProdutoServico {
  id: string;
  secao: Secao;
  nome: string;
  descricao: string | null;
  preco_base: number;
  unidade: string;
  horas_estimadas: number;
  ativo: boolean;
  ordem: number;
}

export type ProdutoServicoInput = Omit<ProdutoServico, "id">;

// ─── Orçamento ─────────────────────────────────────────────────────────────

export interface OrcamentoItem {
  id?: string;
  produto_servico_id: string | null;
  secao: Secao;
  descricao: string;
  preco_unitario: number;
  recorrente: boolean;
  /** Bitmask seg=1 ter=2 qua=4 qui=8 sex=16 sab=32 dom=64. */
  dias_semana: number;
  qtd_por_dia: number;
  /** Used when `!recorrente`. */
  quantidade: number;
  /** SERVER-computed: recorrente ? popcount(dias_semana)*qtd_por_dia*4 : quantidade. */
  quantidade_mensal?: number;
  /** SERVER-computed: preco_unitario * quantidade_mensal. */
  subtotal?: number;
  ordem: number;
}

/** What the client sends for an item — the server computes the rest. */
export type OrcamentoItemInput = Omit<OrcamentoItem, "quantidade_mensal" | "subtotal">;

export type OrcamentoStatus =
  | "rascunho"
  | "enviado"
  | "aceito"
  | "recusado"
  | "expirado"
  | "substituido";

export const ORCAMENTO_STATUS_LABEL: Record<OrcamentoStatus, string> = {
  rascunho: "Rascunho",
  enviado: "Enviado",
  aceito: "Aceito",
  recusado: "Recusado",
  expirado: "Expirado",
  substituido: "Substituído",
};

/** Only these may be edited (PATCH) — anything else answers 409 `orcamento_bloqueado`. */
export const ORCAMENTO_EDITAVEL: readonly OrcamentoStatus[] = ["rascunho", "enviado"];

export interface LimitesEscopo {
  revisoes_incluidas: number;
  valor_excedente: number;
  observacoes?: string;
}

export interface Totais {
  subtotal_criacao: number;
  subtotal_gestao: number;
  desconto: number;
  total_mensal: number;
  custo_estimado: number;
  /** % 0–100, (total-custo)/total. */
  margem_estimada: number;
  horas_estimadas: number;
}

export interface Orcamento extends Totais {
  id: string;
  negocio_id: string;
  lead_id: string;
  cliente_id: string | null;
  versao: number;
  titulo: string;
  status: OrcamentoStatus;
  /** null = never expires; past validade ⇒ status expirado on read. */
  validade: string | null;
  itens: OrcamentoItem[];
  limites_escopo: LimitesEscopo;
  observacoes: string | null;
  pdf_key: string | null;
  enviado_em: string | null;
  respondido_em: string | null;
  aceito_em: string | null;
  recusado_em: string | null;
  motivo_recusa: string | null;
  created_at: string;
  lead: { id: string; nome: string; email: string | null; empresa: string | null };
  negocio: { id: string; titulo: string; etapa_id: string; status: string };
}

export interface OrcamentoInput {
  negocio_id: string;
  titulo?: string;
  validade?: string | null;
  itens: OrcamentoItemInput[];
  desconto?: number;
  limites_escopo?: LimitesEscopo;
  observacoes?: string | null;
}

export type OrcamentoPatch = Omit<OrcamentoInput, "negocio_id">;

export interface CalculoOrcamento extends Totais {
  itens: OrcamentoItem[];
}

export interface OrcamentoEmail {
  id: string;
  orcamento_id: string;
  direction: "out" | "in";
  message_id: string;
  thread_id: string | null;
  from_addr: string;
  subject: string;
  snippet: string | null;
  occurred_at: string;
}

export type OrcamentoAba = "ativos" | "aceitos" | "recusados";

export interface OrcamentoFiltros {
  aba?: OrcamentoAba;
  status?: OrcamentoStatus;
  negocio_id?: string;
  lead_id?: string;
  cliente_id?: string;
  q?: string;
}

export interface AceiteResultado {
  orcamento: Orcamento;
  negocio: { id: string; status: string };
  cliente: { id: string; nome: string };
  pautas_criadas: number;
}

export type ModalidadeAssinatura = "digital" | "fisica";

/** The `contrato` row `POST /api/orcamentos/{id}/contrato` writes (+ the
 * signature-provider fields it fills in for `digital`). */
export interface Contrato {
  id: string;
  cliente_id: string;
  orcamento_id: string;
  valor_mensal: number;
  posts_por_mes: number;
  valor_excedente: number;
  dia_vencimento: number | null;
  data_inicio: string;
  status: string;
  modalidade_assinatura: ModalidadeAssinatura;
  documento_key: string;
  provedor_assinatura?: string | null;
  assinatura_external_id?: string | null;
  link_assinatura?: string | null;
}

/** `assinatura` is only set for `modalidade === "digital"` (the dry-run
 * signature-provider dispatch, `NOC-REMEDIATE[igig-assinatura]`). */
export interface ContratoAssinatura {
  provedor: string;
  link_assinatura: string | null;
  external_id: string;
  dry_run: boolean;
}

/** `POST /api/orcamentos/{id}/contrato` → `{data: ContratoGerado}`. */
export interface ContratoGerado {
  contrato: Contrato;
  url: string;
  assinatura: ContratoAssinatura | null;
}

// ─── Funil comercial ───────────────────────────────────────────────────────

export type LeadOrigem = "formulario" | "manual" | "whatsapp" | "meta_ads" | (string & {});

export const ORIGEM_LABEL: Record<string, string> = {
  formulario: "Formulário",
  manual: "Manual",
  whatsapp: "WhatsApp",
  meta_ads: "Meta Ads",
};

/** The lead as the board's card DTO carries it (`_LEAD_CARD`). */
export interface LeadResumo {
  id: string;
  nome: string;
  empresa: string | null;
  email: string | null;
  telefone: string | null;
  instagram: string | null;
  origem: LeadOrigem | null;
  status: string;
}

export interface Negocio {
  id: string;
  org_id: string;
  lead_id: string;
  titulo: string;
  valor_estimado: number | null;
  etapa_id: string;
  kanban_pos: number;
  responsavel_id: string | null;
  status: "aberto" | "ganho" | "perdido";
  stage_entered_at: string | null;
  ganho_em: string | null;
  perdido_em: string | null;
  motivo_perda: string | null;
  orcamento_aceito_id: string | null;
  cliente_id: string | null;
  created_at: string;
  lead: LeadResumo | null;
  responsavel: { id: string; nome: string | null } | null;
  /** The stage this card was in when marked `perdido` — `null` otherwise. */
  perdido_stage: { id: string; label: string } | null;
  /** Days between entering `perdido_stage` and being marked lost —
   * `null` unless `status === "perdido"`. */
  dwell_dias: number | null;
}

export interface LeadManualInput {
  nome: string;
  email?: string;
  telefone?: string;
  empresa?: string;
  instagram?: string;
  observacoes?: string;
}

export type AssistenteAcao = "resumo" | "proxima_acao" | "rascunho_mensagem";
