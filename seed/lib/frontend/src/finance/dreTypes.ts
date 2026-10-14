/**
 * DRE / accountant types — mirror the shipped backend (`noctusai_lib.domain.finance`: `types.py`, `dre.py`,
 * `dre_settings.py`, `simples_base.py`, `accountant.py`, `schemas.py`; CONTRACT §10 + §10.5 + §11).
 * Money is integer CENTS.
 */

/** `DreLine` — the lines a category / setting can point at (subtotals are computed, never a member). */
export const DRE_LINES = [
  'gross_revenue',
  'deductions',
  'cost_of_sales',
  'selling_expenses',
  'administrative_expenses',
  'other_operating',
  'financial_revenue',
  'financial_expenses',
  'income_taxes',
  'unclassified',
] as const;
export type DreLine = (typeof DRE_LINES)[number];

/** Lines a category or a setting can be assigned to (everything but the `unclassified` block). */
export const DRE_ASSIGNABLE_LINES = DRE_LINES.filter((l) => l !== 'unclassified') as readonly Exclude<DreLine, 'unclassified'>[];
export type DreAssignableLine = (typeof DRE_ASSIGNABLE_LINES)[number];

/** Computed subtotals, in statement order (`dre_help.STATEMENT_ORDER`). */
export const DRE_SUBTOTAL_KEYS = [
  'net_revenue',
  'gross_result',
  'result_before_financial',
  'result_before_income_taxes',
  'net_result',
] as const;
export type DreSubtotalKey = (typeof DRE_SUBTOTAL_KEYS)[number];

export const FINANCE_TAX_REGIMES = ['mei', 'simples', 'presumido', 'unknown'] as const;
export type FinanceTaxRegime = (typeof FINANCE_TAX_REGIMES)[number];

/** The provisional choices (`dre_settings.CHOICES`), in checklist order. */
export const DRE_LINE_SETTING_KEYS = [
  'gateway_fee_line',
  'anticipation_fee_line',
  'chargeback_line',
  'chargeback_fee_line',
  'installment_interest_line',
] as const;
export type DreLineSettingKey = (typeof DRE_LINE_SETTING_KEYS)[number];

/** One provisional choice as `GET /dre-settings` presents it. `provisional` defaults to true server-side. */
export interface DreChoice {
  value: DreAssignableLine;
  default: DreAssignableLine;
  provisional: boolean;
  confirmed_by: string | null;
  confirmed_at: string | null;
  note: string | null;
}

/** `GET/PUT /api/finance/dre-settings`. */
export interface DreSettings {
  /** False until the first PUT (defaults are answered). */
  persisted: boolean;
  tax_regime: FinanceTaxRegime;
  /** Regime pre-filled from the commerce store profile (not yet saved). */
  tax_regime_prefilled: boolean;
  das_split_irpj_csll: boolean;
  /** IRPJ+CSLL share of the DAS in basis points (1250 = 12,50 %). */
  das_irpj_csll_share_bps: number;
  choices: Record<DreLineSettingKey, DreChoice>;
}

/** `{confirmed, note}` — the accountant's sign-off on ONE choice (`DreChoiceMeta`). */
export interface DreChoiceConfirmation {
  confirmed: boolean;
  note?: string | null;
}
/** `PUT /dre-settings` body (`DreSettingsBody`): every field optional. Confirming = `confirmations[name]`. */
export type DreSettingsInput = Partial<
  { tax_regime: FinanceTaxRegime; das_split_irpj_csll: boolean; das_irpj_csll_share_bps: number } & Record<
    DreLineSettingKey,
    DreAssignableLine
  >
> & { confirmations?: Partial<Record<DreLineSettingKey, DreChoiceConfirmation>> };
/** Convenience for the hook: confirm (or un-confirm) choices without touching their values. */
export interface DreConfirmInput {
  fields: DreLineSettingKey[];
  note?: string | null;
  confirmed?: boolean;
}

export type DreWarningSeverity = 'info' | 'warning' | 'critical';
/** `warnings[]` — `{code, severity, message, action}` (+ optional `details`). */
export interface DreWarning {
  code: string;
  severity: DreWarningSeverity;
  message: string;
  action?: string | null;
  details?: Record<string, unknown>;
}
/** `accountant_alerts[]` — when a professional is needed, why, and the source. */
export interface DreAccountantAlert {
  code: string;
  message: string;
  why: string;
  source: string;
}
/** `help[key]` — plain-language help per line / subtotal. */
export interface DreLineHelp {
  label?: string;
  what: string;
  example?: string | null;
  source?: string | null;
}

/** A category (or fact group) under a line. `cents` is the magnitude. */
export interface DreDetailRow {
  category_id: string | null;
  name: string;
  cents: number;
  by_month: Record<string, number>;
  behavior: 'variable' | 'fixed' | null;
  source: string | null;
}

/** One row of `statement[]`. `sign` = effect on net_result (+1 revenue side, −1 costs); subtotals are +1. */
export interface DreStatementItem {
  key: string;
  kind: 'line' | 'subtotal';
  /** Already carries the operator, e.g. "(-) Deduções da receita", "= Receita líquida". */
  label: string;
  sign: 1 | -1;
  cents: number;
  by_month: Record<string, number>;
  detail: DreDetailRow[];
  /** No detail rows (or all zero) — shown greyed with its help. */
  empty: boolean;
}

export interface DreManagerialRow {
  line: DreLine;
  category_id: string | null;
  name: string;
  by_month: Record<string, number>;
  cents: number;
}
export interface DreManagerialBlock {
  cents: number;
  by_month: Record<string, number>;
  detail?: DreManagerialRow[];
}
/** `managerial` block (view=managerial replaces `statement`). Reconciles to `net_result`. */
export interface DreManagerial {
  title: string;
  revenue: DreManagerialBlock;
  variable_costs: DreManagerialBlock;
  contribution_margin: DreManagerialBlock & { percent_of_revenue_bps: number | null };
  fixed_costs: DreManagerialBlock;
  other_income: DreManagerialBlock;
  net_result: DreManagerialBlock;
}

/** Wire name of the `view` query param: `statement` (contábil) or `managerial` (margem de contribuição). */
export type DreView = 'statement' | 'managerial';

export interface DreUnclassified {
  /** Net effect of money with no DRE line — NOT part of `net_result_cents`. */
  net_cents: number;
  by_month: Record<string, number>;
  detail: DreDetailRow[];
  included_in_net_result: false;
}

export interface DreReportData {
  from: string;
  to: string;
  months: string[];
  view: DreView;
  /** MEI stores: "DRE gerencial (MEI não é obrigado a ter DRE)". */
  title: string;
  /** `nbc_tg_1002` (≤ R$ 4,8 mi) or `nbc_tg_1001`. */
  standard: string;
  tax_regime: FinanceTaxRegime;
  trailing_12m_gross_revenue_cents: number;
  net_result_cents: number;
  unclassified: DreUnclassified;
  help: Record<string, DreLineHelp>;
  warnings: DreWarning[];
  accountant_alerts: DreAccountantAlert[];
  /** Present when `view=statement`. */
  statement?: DreStatementItem[];
  /** Present when `view=managerial`. */
  managerial?: DreManagerial;
}

/** One provisional / confirmed choice in `GET /accountant-checklist`. */
export interface AccountantChoiceItem {
  choice: DreLineSettingKey;
  question_id: string;
  question: string;
  why_open: string;
  /** line value → label ("Despesas com vendas (padrão)"). */
  options: Record<string, string>;
  current_value: string;
  default_value: string;
  provisional: boolean;
  confirmed_by: string | null;
  confirmed_at: string | null;
  note: string | null;
  sources: string[];
}
export interface AccountantOpenQuestion {
  id: string;
  question: string;
  context: string;
  sources: string[];
}
export interface AccountantChecklistData {
  generated_at: string;
  tax_regime: FinanceTaxRegime;
  tax_regime_informed: boolean;
  das_split_irpj_csll: boolean;
  provisional_choices: AccountantChoiceItem[];
  confirmed_choices: AccountantChoiceItem[];
  open_questions: AccountantOpenQuestion[];
  /** `name` ∈ dre_csv · entries_csv · ledger_ofx. */
  exports: { name: string; path: string }[];
  disclaimer: string;
}

/** `GET /api/finance/reports/simples-base`. */
export interface SimplesBaseRow {
  month: string;
  /** `cash` (recebimento) until 2026-12; `invoice` (faturamento, approximated by competence) from 2027-01. */
  basis: 'cash' | 'invoice';
  sales_cents: number;
  interest_cents: number;
  refunds_cents: number;
  /** Lost chargebacks — informational, NOT deducted from the base. */
  chargebacks_cents: number;
  base_cents: number;
}
export interface SimplesBaseTotals {
  sales_cents: number;
  interest_cents: number;
  refunds_cents: number;
  chargebacks_cents: number;
  base_cents: number;
}
export interface SimplesBaseData {
  from: string;
  to: string;
  tax_regime: FinanceTaxRegime;
  invoice_basis_from: string;
  crosses_basis_boundary: boolean;
  months: SimplesBaseRow[];
  totals: SimplesBaseTotals & { cash_basis: SimplesBaseTotals; invoice_basis: SimplesBaseTotals };
  basis_note: string;
  notes: string[];
  warnings: DreWarning[];
}
