export const CHART_COLORS = [
  "#10b981", "#3b82f6", "#8b5cf6", "#f59e0b", "#ef4444",
  "#ec4899", "#14b8a6", "#6366f1", "#f97316", "#0ea5e9",
  "#a855f7", "#22c55e", "#64748b", "#84cc16",
];

export const TIPO_CONTA_LABELS: Record<string, string> = {
  corrente: "Conta Corrente",
  poupanca: "Poupanca",
  cartao_credito: "Cartao de Credito",
  investimento: "Investimento",
  carteira: "Carteira",
  emprestimo: "Emprestimo",
  outro: "Outro",
};

export const TIPO_TRANSACAO_LABELS: Record<string, string> = {
  receita: "Receita",
  despesa: "Despesa",
  transferencia: "Transferencia",
};

export const TIPO_ATIVO_LABELS: Record<string, string> = {
  acao: "Acao",
  etf: "ETF",
  fii: "FII",
  bdr: "BDR",
  renda_fixa: "Renda Fixa",
  tesouro_direto: "Tesouro Direto",
  fundo: "Fundo",
  crypto: "Crypto",
  cdb: "CDB",
  lci_lca: "LCI/LCA",
  debenture: "Debenture",
  outro: "Outro",
};

export const PRIORIDADE_LABELS: Record<string, string> = {
  alta: "Alta",
  media: "Media",
  baixa: "Baixa",
};

export const METODO_ORCAMENTO_LABELS: Record<string, string> = {
  zero_based: "Base Zero",
  envelope: "Envelope",
  "50_30_20": "50/30/20",
  personalizado: "Personalizado",
};

export const FREQUENCIA_LABELS: Record<string, string> = {
  semanal: "Semanal",
  quinzenal: "Quinzenal",
  mensal: "Mensal",
  bimestral: "Bimestral",
  trimestral: "Trimestral",
  semestral: "Semestral",
  anual: "Anual",
};
