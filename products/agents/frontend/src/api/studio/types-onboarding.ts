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
  /** What the LIVE interview says about the item; `null` when no interview exists for this company. */
  entrevista: EstadoEntrevista | null;
}
export type EstadoEntrevista = "aberto" | "respondido" | "pendente" | "proposto" | "recusado";
export interface SessaoEntrevista {
  id: string;
  conversation_id: string;
  criada_em: string;
  /** Ledger event count: grows with every answer, refusal, import, summary and apply. */
  eventos: number;
  resumo_apresentado: boolean;
  aplicada: boolean;
}
/** `POST .../onboarding/conversa`: the interviewer's conversation bound to the company. */
export interface ConversaEntrevista {
  sessao_id: string;
  conversation_id: string;
  agent_key: string;
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
  sessao: SessaoEntrevista | null;
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
