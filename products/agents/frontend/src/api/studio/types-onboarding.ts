/** Onboarding by interview — wire types of `onboarding_router.py` (staff, per company). */
export interface OnboardingItem {
  n: number;
  bloco: string;
  /** R required | C required when the operation applies | O optional (has a default). */
  nivel: "R" | "C" | "O";
  titulo: string;
  pergunta: string;
  /** `spec:<key>` | `sw:<setting>` | `humano:<step>`. */
  destino: string;
  padrao: string | null;
  quando: string[];
  /** `preenchido` | `vazio` for spec-backed items; `fora_do_agents` when the answer lives in SW or is a human step. */
  estado: "preenchido" | "vazio" | "fora_do_agents";
}
export interface OnboardingProgresso {
  por_nivel: Record<"R" | "C" | "O", { total: number; feitos: number }>;
  faltando_obrigatorios: number[];
}
export interface Onboarding {
  agent_key: string;
  operacoes: string[];
  itens: OnboardingItem[];
  progresso: OnboardingProgresso;
  proximo_passo: string;
}
export interface RespostaImportada {
  n: number;
  valor: unknown;
  fonte: string;
  origem: string;
  confirmado: boolean;
}
export interface Importacao {
  preenchidas: RespostaImportada[];
  nao_reconhecidas: string[];
  conflitos: string[];
}
export interface ItemRelatorio {
  n: number;
  titulo: string;
  estado: "aplicado" | "recusado" | "pendente_humano" | "pendente_confirmacao";
  codigo: string | null;
  motivo: string | null;
  destino: string;
  rota: string | null;
  corpo: Record<string, unknown> | null;
}
export interface RelatorioAplicacao {
  itens: ItemRelatorio[];
  aplicados: number;
  recusados: number;
  obrigatorios_faltando: number[];
  proximo_passo: string;
}

/** The onboarding channel to social-wiring — wire types of `sw_canal_router.py` (platform admin). NEVER carries the token. */
export type SwCanalEstado = "provisionado" | "ausente" | "expirado" | "erro";
export interface SwCanalEvento {
  em: string;
  evento: string;
  codigo: string | null;
  /** pt-BR reason, short; never a secret. */
  motivo: string | null;
}
export interface SwCanalStatus {
  estado: SwCanalEstado;
  escopo: string;
  emissor: string;
  expira_em: string | null;
  dias_restantes: number | null;
  ultima_chamada_ok: SwCanalEvento | null;
  ultimo_erro: SwCanalEvento | null;
  codigo: string | null;
  motivo: string | null;
}
export interface SwCanalTeste {
  ok: boolean;
  codigo: string | null;
  motivo: string;
  status: SwCanalStatus;
}
