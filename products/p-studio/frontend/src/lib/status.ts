/**
 * Sistema de status por cor (spec § 9) — oito cores semânticas, herdadas do
 * protótipo. Os três pipelines (comercial, produção, financeiro) andam
 * separados, mas se pintam com o mesmo vocabulário visual: um cartão amarelo
 * quer dizer "captado" em qualquer tela.
 */

export type TomStatus =
  | "lead"
  | "scheduled"
  | "captured"
  | "editing"
  | "delivered"
  | "received"
  | "late"
  | "cancelled";

/** Classes utilitárias por tom — o padrão `bg-X/15 text-X border-X/30`. */
export const CLASSES_STATUS: Record<TomStatus, string> = {
  lead: "bg-status-lead/15 text-status-lead border-status-lead/30",
  scheduled: "bg-status-scheduled/15 text-status-scheduled border-status-scheduled/30",
  captured: "bg-status-captured/15 text-status-captured border-status-captured/30",
  editing: "bg-status-editing/15 text-status-editing border-status-editing/30",
  delivered: "bg-status-delivered/15 text-status-delivered border-status-delivered/30",
  received: "bg-status-received/15 text-status-received border-status-received/30",
  late: "bg-status-late/15 text-status-late border-status-late/30",
  cancelled: "bg-status-cancelled/15 text-foreground border-status-cancelled/30",
};

/** Cor sólida do tom — para bolinhas, barras de gráfico e topos de coluna. */
export const COR_STATUS: Record<TomStatus, string> = {
  lead: "oklch(var(--status-lead))",
  scheduled: "oklch(var(--status-scheduled))",
  captured: "oklch(var(--status-captured))",
  editing: "oklch(var(--status-editing))",
  delivered: "oklch(var(--status-delivered))",
  received: "oklch(var(--status-received))",
  late: "oklch(var(--status-late))",
  cancelled: "oklch(var(--status-cancelled))",
};

/** Etapa do funil comercial → tom. */
export const TOM_NEGOCIO: Record<string, TomStatus> = {
  novo_lead: "lead",
  orcamento: "scheduled",
  negociacao: "captured",
  aprovado: "editing",
  agendamento: "scheduled",
  producao: "editing",
  entregue: "delivered",
  recebido: "received",
  arquivado: "cancelled",
};

/** Etapa do pipeline de produção → tom. */
export const TOM_PRODUCAO: Record<string, TomStatus> = {
  agendado: "scheduled",
  captado: "captured",
  backup: "captured",
  selecao: "editing",
  edicao: "editing",
  revisao: "editing",
  entregue: "delivered",
  arquivado: "cancelled",
};

/** Status financeiro exibido → tom. */
export const TOM_FINANCEIRO: Record<string, TomStatus> = {
  a_faturar: "lead",
  faturado: "scheduled",
  recebido: "received",
  atrasado: "late",
  cancelado: "cancelled",
};

/** Status de captação → tom. */
export const TOM_CAPTACAO: Record<string, TomStatus> = {
  agendado: "scheduled",
  captado: "captured",
  cancelado: "cancelled",
};

// ── Rótulos (espelho dos dicionários do backend) ───────────────────────────

export const LABEL_STATUS_CAPTACAO: Record<string, string> = {
  agendado: "Agendado",
  captado: "Captado",
  cancelado: "Cancelado",
};

export const LABEL_FORMA_PAGAMENTO: Record<string, string> = {
  pix: "PIX",
  boleto: "Boleto",
  cartao: "Cartão",
  transferencia: "Transferência",
};

export const FORMAS_PAGAMENTO = ["pix", "boleto", "cartao", "transferencia"] as const;

export const LABEL_TIPO_IMOVEL: Record<string, string> = {
  casa: "Casa",
  apartamento: "Apartamento",
  cobertura: "Cobertura",
  terreno: "Terreno",
  comercial: "Comercial",
  galpao: "Galpão",
};

export const TIPOS_IMOVEL = [
  "casa",
  "apartamento",
  "cobertura",
  "terreno",
  "comercial",
  "galpao",
] as const;

export const LABEL_PADRAO_IMOVEL: Record<string, string> = {
  alto: "Alto padrão",
  medio: "Médio padrão",
  economico: "Econômico",
};

export const PADROES_IMOVEL = ["alto", "medio", "economico"] as const;

export const LABEL_CATEGORIA_EQUIPAMENTO: Record<string, string> = {
  camera: "Câmera",
  lente: "Lente",
  drone: "Drone",
  microfone: "Microfone",
  gimbal: "Gimbal",
  bateria: "Baterias",
  cartao: "Cartões SD",
  iluminacao: "Iluminação",
  outro: "Outro",
};

export const CATEGORIAS_EQUIPAMENTO = [
  "camera",
  "lente",
  "drone",
  "microfone",
  "gimbal",
  "bateria",
  "cartao",
  "iluminacao",
  "outro",
] as const;

/** Categorias do catálogo de serviços observadas na operação do estúdio. */
export const CATEGORIAS_SERVICO = ["Fotografia", "Aéreo", "Audiovisual", "Outro"] as const;
