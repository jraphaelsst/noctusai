export interface Wallet {
  id: string;
  owner_id: string;
  owner_type: 'patient' | 'therapist' | 'clinic';
  balance: number;
  last_updated: string;
}

export interface WalletMovement {
  id: string;
  wallet_id: string;
  type: 'credit' | 'debit';
  amount: number;
  reference_type: 'session_commission' | 'voluntary_transfer' | 'withdrawal' | 'refund' | 'top_up' | 'no_show_fee';
  reference_id?: string;
  description?: string;
  created_at: string;
}

export interface Transaction {
  id: string;
  appointment_id: string;
  patient_id: string;
  therapist_id: string;
  clinic_id?: string;
  patient_origin: string;
  gross_amount: number;
  platform_fee_pct: number;
  platform_fee_amount: number;
  clinic_commission_pct?: number;
  clinic_share_amount?: number;
  therapist_share_amount: number;
  status: 'pre_authorized' | 'captured' | 'refunded' | 'failed' | 'released';
  gateway_ref?: string;
  created_at: string;
}

export interface Payout {
  id: string;
  recipient_id: string;
  recipient_type: 'patient' | 'therapist' | 'clinic';
  amount: number;
  fee_pct: number;
  fee_amount: number;
  net_amount: number;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  requested_at: string;
  processed_at?: string;
}

export interface RefundRequest {
  id: string;
  transaction_id: string;
  patient_id: string;
  patient_name?: string;
  therapist_name?: string;
  session_date?: string;
  reason: string;
  status: 'pending' | 'approved' | 'denied';
  review_response?: string;
  refund_amount: number;
  created_at: string;
}

export interface ClinicTransfer {
  id: string;
  clinic_id: string;
  therapist_id: string;
  therapist_name?: string;
  amount: number;
  reason: string;
  created_at: string;
}

export interface PaymentMethod {
  id: string;
  brand: string;
  last4: string;
  exp_month: number;
  exp_year: number;
  is_default: boolean;
}

export interface ClinicFinancials {
  total_revenue: number;
  platform_fees: number;
  clinic_balance: number;
  total_therapists: number;
  therapist_breakdown: TherapistBreakdown[];
}

export interface TherapistBreakdown {
  therapist_id: string;
  therapist_name: string;
  sessions_count: number;
  gross_revenue: number;
  clinic_commission_pct: number;
  clinic_share: number;
  therapist_share: number;
  patient_origin: string;
}

export interface AdminFinancialSummary {
  total_revenue: number;
  platform_fees: number;
  payouts_completed: number;
  payouts_pending: number;
}

export interface CommissionOverride {
  id: string;
  entity_id: string;
  entity_type: 'clinic' | 'therapist';
  entity_name: string;
  rate_pct: number;
}

export interface AdminWalletSummary {
  id: string;
  owner_name: string;
  owner_type: 'patient' | 'therapist' | 'clinic';
  balance: number;
}

// Status config for badges
export const TRANSACTION_STATUS_CONFIG: Record<string, { label: string; variant: 'default' | 'secondary' | 'outline' | 'destructive' }> = {
  pre_authorized: { label: 'Pre-autorizado', variant: 'outline' },
  captured: { label: 'Capturado', variant: 'default' },
  refunded: { label: 'Reembolsado', variant: 'secondary' },
  failed: { label: 'Falhou', variant: 'destructive' },
  released: { label: 'Liberado', variant: 'outline' },
};

export const MOVEMENT_TYPE_LABELS: Record<string, string> = {
  session_commission: 'Comissao de Sessao',
  voluntary_transfer: 'Transferencia',
  withdrawal: 'Saque',
  refund: 'Reembolso',
  top_up: 'Credito',
  no_show_fee: 'Taxa de Ausencia',
};

export const PAYOUT_STATUS_CONFIG: Record<string, { label: string; variant: 'default' | 'secondary' | 'outline' | 'destructive' }> = {
  pending: { label: 'Pendente', variant: 'outline' },
  processing: { label: 'Processando', variant: 'secondary' },
  completed: { label: 'Concluido', variant: 'default' },
  failed: { label: 'Falhou', variant: 'destructive' },
};

export const REFUND_STATUS_CONFIG: Record<string, { label: string; variant: 'default' | 'secondary' | 'outline' | 'destructive' }> = {
  pending: { label: 'Pendente', variant: 'outline' },
  approved: { label: 'Aprovado', variant: 'default' },
  denied: { label: 'Negado', variant: 'destructive' },
};
