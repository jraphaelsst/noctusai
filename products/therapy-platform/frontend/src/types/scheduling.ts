// Scheduling & Calendar type definitions

export interface AvailabilitySlot {
  id: string;
  therapist_id: string;
  day_of_week: number; // 0=Sunday, 6=Saturday
  start_time: string; // "HH:MM"
  end_time: string; // "HH:MM"
  is_recurring: boolean;
  specific_date?: string;
  is_blocked: boolean;
  created_at: string;
}

export interface Appointment {
  id: string;
  therapist_id: string;
  patient_id: string;
  clinic_id?: string;
  recurring_schedule_id?: string;
  patient_origin: string;
  session_price_applied?: number;
  scheduled_start: string;
  scheduled_end: string;
  status: AppointmentStatus;
  meeting_link?: string;
  is_auto_generated: boolean;
  patient_attended?: boolean;
  therapist_attended?: boolean;
  created_at: string;
  // Enriched fields
  therapist_name?: string;
  patient_name?: string;
  video_room?: VideoRoom;
}

export type AppointmentStatus =
  | 'waiting'
  | 'in_progress'
  | 'paused'
  | 'completed'
  | 'cancelled'
  | 'late_cancelled'
  | 'no_show'
  | 'payment_pending'
  | 'payment_failed';

export interface VideoRoom {
  id: string;
  meeting_url: string;
  accessible_from: string;
  accessible_until: string;
  status: string;
}

export interface RecurringSchedule {
  id: string;
  therapist_id: string;
  patient_id: string;
  clinic_id?: string;
  frequency: RecurringFrequency;
  custom_interval_weeks?: number;
  day_of_week: number;
  start_time: string;
  duration_minutes: number;
  start_date: string;
  end_condition: 'indefinite' | 'after_n_occurrences' | 'on_date';
  end_after_n?: number;
  end_on_date?: string;
  status: 'active' | 'paused' | 'ended';
  total_completed: number;
  total_absences: number;
  created_at: string;
  // Enriched
  therapist_name?: string;
  patient_name?: string;
  upcoming_appointments?: Appointment[];
}

export type RecurringFrequency = 'weekly' | 'biweekly' | 'monthly' | 'custom';

export interface BookableSlot {
  date: string;
  start_time: string;
  end_time: string;
}

export interface AppointmentFilters {
  status?: AppointmentStatus;
  date_start?: string;
  date_end?: string;
  page?: number;
  page_size?: number;
}

export interface RecurringFilters {
  status?: 'active' | 'paused' | 'ended';
  page?: number;
  page_size?: number;
}

// Status display config
export const APPOINTMENT_STATUS_CONFIG: Record<AppointmentStatus, { label: string; color: string }> = {
  waiting: { label: 'Aguardando', color: 'bg-blue-100 text-blue-800' },
  in_progress: { label: 'Em andamento', color: 'bg-green-100 text-green-800' },
  paused: { label: 'Pausado', color: 'bg-yellow-100 text-yellow-800' },
  completed: { label: 'Concluido', color: 'bg-gray-100 text-gray-800' },
  cancelled: { label: 'Cancelado', color: 'bg-red-100 text-red-800' },
  late_cancelled: { label: 'Cancelado (tardio)', color: 'bg-red-200 text-red-900' },
  no_show: { label: 'Nao compareceu', color: 'bg-red-300 text-red-950' },
  payment_pending: { label: 'Pagamento pendente', color: 'bg-orange-100 text-orange-800' },
  payment_failed: { label: 'Pagamento falhou', color: 'bg-orange-200 text-orange-900' },
};

export const RECURRING_FREQUENCY_LABELS: Record<RecurringFrequency, string> = {
  weekly: 'Semanal',
  biweekly: 'Quinzenal',
  monthly: 'Mensal',
  custom: 'Personalizado',
};

export const RECURRING_STATUS_LABELS: Record<string, { label: string; color: string }> = {
  active: { label: 'Ativo', color: 'bg-green-100 text-green-800' },
  paused: { label: 'Pausado', color: 'bg-yellow-100 text-yellow-800' },
  ended: { label: 'Encerrado', color: 'bg-gray-100 text-gray-800' },
};

export const DAY_OF_WEEK_LABELS = [
  'Domingo', 'Segunda', 'Terca', 'Quarta', 'Quinta', 'Sexta', 'Sabado',
] as const;

export const DAY_OF_WEEK_SHORT = [
  'Dom', 'Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sab',
] as const;
