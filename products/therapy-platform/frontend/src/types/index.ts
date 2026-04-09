// Therapy Platform type definitions

export type UserRole = "paciente" | "terapeuta" | "clinica" | "admin";

export interface Terapeuta {
  id: string;
  user_id: string;
  nome: string;
  email: string;
  crp: string;
  bio?: string;
  foto_url?: string;
  especialidades: string[];
  abordagens: string[];
  valor_sessao?: number;
  duracao_sessao?: number;
  status: "pendente" | "aprovado" | "rejeitado" | "suspenso";
  nota_media?: number;
  total_avaliacoes?: number;
  created_at: string;
  updated_at: string;
}

export interface Clinica {
  id: string;
  user_id: string;
  nome: string;
  cnpj: string;
  responsavel: string;
  email: string;
  telefone: string;
  endereco?: string;
  cidade?: string;
  estado?: string;
  logo_url?: string;
  status: "pendente" | "aprovada" | "rejeitada" | "suspensa";
  nota_media?: number;
  total_avaliacoes?: number;
  created_at: string;
  updated_at: string;
}

export interface Paciente {
  id: string;
  user_id: string;
  nome: string;
  email: string;
  telefone?: string;
  data_nascimento?: string;
  created_at: string;
  updated_at: string;
}

export interface Sessao {
  id: string;
  terapeuta_id: string;
  paciente_id: string;
  clinica_id?: string;
  data_hora: string;
  duracao_minutos: number;
  tipo: "individual" | "casal" | "grupo" | "infantil";
  modalidade: "presencial" | "online";
  status: "agendada" | "confirmada" | "em_andamento" | "concluida" | "cancelada" | "falta";
  valor: number;
  notas_terapeuta?: string;
  created_at: string;
  updated_at: string;
}

export interface Agendamento {
  id: string;
  terapeuta_id: string;
  paciente_id: string;
  sessao_id?: string;
  data_hora: string;
  status: "pendente" | "confirmado" | "cancelado";
  created_at: string;
}

export interface Avaliacao {
  id: string;
  terapeuta_id?: string;
  clinica_id?: string;
  paciente_id: string;
  nota: number;
  comentario?: string;
  anonima: boolean;
  created_at: string;
}

export interface Pagamento {
  id: string;
  sessao_id: string;
  paciente_id: string;
  terapeuta_id: string;
  valor: number;
  status: "pendente" | "pago" | "cancelado" | "reembolsado";
  metodo?: string;
  created_at: string;
}

// ── Clinical Records ──────────────────────────────────────────

export interface Anamnese {
  id: string;
  patient_id: string;
  therapist_id: string;
  queixa_principal: string;
  historia_pregressa?: string;
  historico_familiar?: string;
  medicacoes?: string;
  observacoes?: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface TreatmentPlan {
  id: string;
  patient_id: string;
  therapist_id: string;
  titulo: string;
  descricao?: string;
  status: string;
  data_inicio: string;
  data_revisao?: string;
  goals?: TreatmentPlanGoal[];
  created_at: string;
  updated_at: string;
}

export interface TreatmentPlanGoal {
  id: string;
  plan_id: string;
  descricao: string;
  status: string;
  prazo?: string;
  observacoes?: string;
  created_at: string;
  updated_at: string;
}

export interface EvolutionNote {
  id: string;
  patient_id: string;
  therapist_id: string;
  appointment_id?: string;
  formato: "soap" | "livre";
  subjetivo?: string;
  objetivo?: string;
  avaliacao?: string;
  plano?: string;
  conteudo_livre?: string;
  created_at: string;
  updated_at: string;
}

// ── Patient Portal ──────────────────────────────────────────

export interface MoodEntry {
  id: string;
  patient_id: string;
  rating: number;
  emocoes?: string[];
  nota?: string;
  data: string;
  created_at: string;
}

export interface MoodAnalytics {
  media_rating: number;
  total_registros: number;
  emocoes_frequentes: Record<string, number>;
  tendencia: string;
}

export interface JournalEntry {
  id: string;
  patient_id: string;
  titulo?: string;
  conteudo: string;
  is_shared_with_therapist: boolean;
  created_at: string;
  updated_at: string;
}

export interface HomeworkAssignment {
  id: string;
  patient_id: string;
  therapist_id: string;
  titulo: string;
  descricao: string;
  data_limite?: string;
  status: string;
  resposta_paciente?: string;
  feedback_terapeuta?: string;
  created_at: string;
  updated_at: string;
}

// ── Invoicing ──────────────────────────────────────────

export interface Invoice {
  id: string;
  transaction_id: string;
  therapist_id: string;
  patient_id: string;
  valor: number;
  descricao?: string;
  pdf_url?: string;
  status: string;
  created_at: string;
}

// ── Crisis ──────────────────────────────────────────

export interface CrisisAlert {
  id: string;
  patient_id: string;
  therapist_id: string;
  source_type: string;
  conteudo_flagged: string;
  palavras_detectadas: string[];
  severidade: string;
  status: string;
  revisado_por?: string;
  revisado_at?: string;
  created_at: string;
}

// ── Matching ──────────────────────────────────────────

export interface MatchResult {
  therapist_id: string;
  nome: string;
  score_total: number;
  score_embedding: number;
  score_regras: number;
  especialidades: string[];
  abordagens: string[];
  preco: number;
  justificativa?: string;
}

// ── BI ──────────────────────────────────────────

export interface BiResumo {
  total_sessoes: number;
  receita_total: number;
  pacientes_ativos: number;
  media_avaliacao: number;
}

export interface BiSessoes {
  data: string;
  total: number;
  concluidas: number;
  canceladas: number;
}

export interface BiReceita {
  data: string;
  valor: number;
}

export interface BiCancelamento {
  motivo: string;
  total: number;
}
