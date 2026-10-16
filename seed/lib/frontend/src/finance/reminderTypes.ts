/** Billing-reminders (dunning) wire types — mirror `noctusai_lib.domain.finance.reminders` (types.py + router.py). */

/** The template vocabulary (`TEMPLATE_VARIABLES` in the backend; the server refuses anything else with 422 `variavel_desconhecida`). */
export const REMINDER_VARIABLES = [
  'nome',
  'razao_social',
  'nome_fantasia',
  'valor',
  'vencimento',
  'link_pagamento',
  'pix_copia_cola',
  'dias_atraso',
] as const;
export type ReminderVariable = (typeof REMINDER_VARIABLES)[number];

export const REMINDER_LOG_STATUSES = ['pending', 'sent', 'failed'] as const;
export type ReminderLogStatus = (typeof REMINDER_LOG_STATUSES)[number];

/** Skip reason codes of the preview (`SKIP_*` in the backend). */
export const REMINDER_SKIP_REASONS = ['no_contact', 'no_address_for_channel', 'receivable_opt_out', 'blocked_by_host', 'no_channel_configured'] as const;
export type ReminderSkipReason = (typeof REMINDER_SKIP_REASONS)[number];

export interface ReminderSettings {
  enabled: boolean;
  timezone: string;
  variables: string[];
}

export interface ReminderRule {
  id: string;
  channel: string;
  /** Days relative to the due date: negative = before, 0 = on the day, positive = overdue. */
  offset_days: number;
  template: string;
  enabled: boolean;
}
export interface ReminderRuleInput {
  offset_days: number;
  template: string;
  enabled?: boolean;
  channel?: string;
}
export type ReminderRulePatch = Partial<ReminderRuleInput>;

export interface ReminderLogRow {
  id: string;
  entry_id: string;
  rule_id: string;
  channel: string;
  offset_days: number;
  cycle_date: string;
  status: ReminderLogStatus;
  attempts: number;
  recipient: string;
  message: string;
  last_error: string | null;
  sent_at: string | null;
  created_at: string;
}

export interface PlannedReminderRow {
  entry_id: string;
  rule_id: string;
  channel: string;
  offset_days: number;
  cycle_date: string;
  recipient: string;
  text: string;
  /** Log status when the dedup ledger already holds this key (it will not be sent again). */
  already: ReminderLogStatus | null;
  description: string | null;
}
export interface SkippedReminderRow {
  entry_id: string;
  rule_id: string;
  reason: ReminderSkipReason;
  description: string | null;
}
export interface ReminderPreview {
  on: string;
  enabled: boolean;
  planned: PlannedReminderRow[];
  skipped: SkippedReminderRow[];
}
