/**
 * SIMEC — types + pure helpers for the marketing-intelligence page.
 *
 * Contract: products/social-wiring/projects/marketing-intelligence/specs/simec-api-contract.md
 * (backend: `app/modules/simec/router.py`).
 *
 * Rules carried here so every consumer gets them by construction:
 *   - A number is a CELL (`{value, status, n?}`), never a bare number.
 *     `value` is null for every status except `ok` and is NEVER coerced to 0.
 *   - `nao_disponivel` = the source does not provide the metric at all; it is
 *     rendered "não disponível" with the config's `note`, never estimated.
 *   - Rates are fractions (0.0868 → "8,68%"); counts may arrive as floats and
 *     render as integers.
 *   - Panel rows / columns come from the readout's OWN config (the one that
 *     produced the numbers), never from an FE list.
 */
import { ApiError } from "@noctusai/lib";

// ─── Wire types ─────────────────────────────────────────────────────────────

export type CellStatus = "ok" | "ausente" | "sem_dados" | "nao_disponivel";

export interface SimecCell {
  value: number | null;
  status: CellStatus;
  n?: number;
}

export interface SimecLatestRef {
  id: string;
  computed_at: string;
  period_start: string;
  period_end: string;
  source: string;
}

export interface SimecAccount {
  account_id: string;
  label: string | null;
  username: string | null;
  marca_id: string | null;
  status: string | null;
  last_synced_at: string | null;
  insights_scope_granted: boolean;
  latest_readout: SimecLatestRef | null;
}

export interface SimecAccountsResponse {
  metrics_source: string;
  accounts: SimecAccount[];
}

export interface SimecMetricDef {
  label: string;
  unit?: string;
  available?: boolean;
  note?: string | null;
}
export interface SimecWindowDef {
  label: string;
  min_days: number;
  max_days: number;
  enabled?: boolean;
}
export interface SimecIndicatorDef {
  label: string;
  op?: string;
  inputs?: string[];
  unit?: string;
  enabled?: boolean;
}
export interface SimecPanelDef {
  label: string;
  aggregate?: string;
  source?: string;
  enabled?: boolean;
}
export interface SimecAlertDef {
  indicator: string;
  method: string;
  threshold: number;
  direction?: string;
  windows?: string[];
  enabled?: boolean;
}
export interface SimecConfig {
  platform: string;
  version: string;
  description?: string;
  required_metrics?: string[];
  metrics: Record<string, SimecMetricDef>;
  windows: Record<string, SimecWindowDef>;
  indicators: Record<string, SimecIndicatorDef>;
  panel: Record<string, SimecPanelDef>;
  baseline: { lookback_days: number; min_posts: number; group_by?: string[]; indicators?: string[] };
  alerts: Record<string, SimecAlertDef>;
  cadence: {
    reviews: Record<string, { label: string; every_days: number }>;
    decision_validation_days: number;
  };
}

export type Overrides = Record<string, unknown>;

export interface SimecLayer {
  version: number;
  overrides: Overrides;
  updated_at?: string | null;
  updated_by?: string | null;
}

export interface SimecConfigResponse {
  platform: string;
  version: string;
  fingerprint: string;
  config: SimecConfig;
  layers: {
    defaults: { version: string };
    org: SimecLayer | null;
    account: SimecLayer | null;
  };
}

export type ReadingStatus =
  | "ok"
  | "incompleto"
  | "data_invalida"
  | "fora_da_janela"
  | "duplicado"
  | "janela_desconhecida";

export interface SimecReadoutSummary {
  id: string;
  account_id: string;
  platform: string;
  source: string;
  period_start: string;
  period_end: string;
  history_start: string;
  config_version: string;
  config_fingerprint: string;
  status_counts: Record<string, number>;
  computed_by: string | null;
  computed_at: string;
}

export interface SimecBaseline {
  window: string;
  group: Record<string, string>;
  indicator: string;
  n: number;
  mean: number | null;
  median: number | null;
  p25: number | null;
  p75: number | null;
  sufficient: boolean;
}

export interface SimecAlertFired {
  rule: string;
  indicator: string;
  method: string;
  threshold: number;
  content_id: string;
  window: string;
  group: Record<string, string>;
  value: number;
  direction: "above" | "below";
  deviation: number;
  baseline: { n: number; median: number | null; p25: number | null; p75: number | null };
}

export interface SimecAlertNotEvaluated {
  rule: string;
  window: string;
  group: Record<string, string>;
  reason: string;
  baseline_n?: number;
}

export interface SimecReading {
  content_id: string | null;
  window: string | null;
  published_on: string | null;
  collected_on: string | null;
  format: string | null;
  topic: string | null;
  status: ReadingStatus | string;
  age_days: number | null;
  metrics: Record<string, SimecCell>;
  indicators: Record<string, SimecCell>;
  source_ref: { permalink?: string | null; snapshot_date?: string | null } & Record<string, unknown> | null;
}

export interface SimecReadout extends SimecReadoutSummary {
  config: SimecConfig;
  panel: Record<string, Record<string, SimecCell>>;
  baselines: SimecBaseline[];
  alerts: { fired: SimecAlertFired[]; not_evaluated: SimecAlertNotEvaluated[] };
  readings: SimecReading[];
}

// ─── Ordered, enabled entries (config order = display order) ────────────────

export function enabledEntries<T extends { enabled?: boolean }>(
  coll: Record<string, T> | undefined | null,
): [string, T][] {
  return Object.entries(coll ?? {}).filter(([, v]) => v && v.enabled !== false);
}

// ─── Number formatting ──────────────────────────────────────────────────────

export type SimecUnit = "count" | "ratio" | "fraction" | "seconds";

const intFmt = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 });
const pctFmt = new Intl.NumberFormat("pt-BR", { style: "percent", minimumFractionDigits: 2, maximumFractionDigits: 2 });
const secFmt = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 });
const decFmt = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 2 });

export function formatSimecNumber(value: number, unit: SimecUnit | string | undefined): string {
  switch (unit) {
    case "ratio":
    case "fraction":
      return pctFmt.format(value);
    case "seconds":
      return `${secFmt.format(value)} s`;
    case "count":
      return intFmt.format(Math.round(value));
    default:
      return decFmt.format(value);
  }
}

/** Unit of a metric/indicator key in a config (`ratio` indicators → percent). */
export function unitOf(config: SimecConfig, key: string | undefined): SimecUnit | string | undefined {
  if (!key) return undefined;
  if (config.metrics?.[key]) return config.metrics[key].unit;
  if (config.indicators?.[key]) return config.indicators[key].unit;
  return undefined;
}

/** Unit a panel line renders in: count/sample aggregates are counts; mean/sum follow the source. */
export function panelUnit(config: SimecConfig, panelKey: string): SimecUnit | string | undefined {
  const def = config.panel?.[panelKey];
  if (!def) return undefined;
  if (def.aggregate === "count" || def.aggregate === "sample") return "count";
  return unitOf(config, def.source);
}

/**
 * The config `note` explaining why a key is `nao_disponivel`: the metric's own
 * note, or (for an indicator / panel line) the note of the first unavailable
 * metric it is built from.
 */
export function unavailableNote(config: SimecConfig, key: string | undefined, depth = 0): string | null {
  if (!key || depth > 8) return null;
  const metric = config.metrics?.[key];
  if (metric) return metric.available === false ? (metric.note ?? null) : null;
  const ind = config.indicators?.[key];
  if (ind) {
    for (const input of ind.inputs ?? []) {
      const n = unavailableNote(config, input, depth + 1);
      if (n) return n;
    }
    return null;
  }
  const panel = config.panel?.[key];
  if (panel) return unavailableNote(config, panel.source, depth + 1);
  return null;
}

export const READING_STATUS_LABEL: Record<string, string> = {
  ok: "ok",
  incompleto: "incompleto",
  data_invalida: "data inválida",
  fora_da_janela: "fora da janela",
  duplicado: "duplicado",
  janela_desconhecida: "janela desconhecida",
};

export const NOT_EVALUATED_LABEL: Record<string, string> = {
  baseline_insuficiente: "linha de base com amostra insuficiente",
  sem_baseline: "sem linha de base para comparar",
  mediana_zero: "mediana da linha de base é zero",
  iqr_zero: "intervalo interquartil da linha de base é zero",
};

export function labelOf(config: SimecConfig, key: string): string {
  return config.indicators?.[key]?.label ?? config.metrics?.[key]?.label ?? key;
}

export function formatGroup(group: Record<string, string> | null | undefined): string {
  const parts = Object.values(group ?? {}).filter(Boolean);
  return parts.length ? parts.join(" · ") : "todos";
}

/** "acima/abaixo do padrão do perfil" — a fact about the profile's own history, never a cause. */
export function describeAlert(alert: SimecAlertFired, config: SimecConfig): string {
  const lado = alert.direction === "above" ? "acima" : "abaixo";
  const unit = unitOf(config, alert.indicator);
  const desvio =
    alert.method === "pct_from_median"
      ? `${pctFmt.format(Math.abs(alert.deviation))} ${lado} da mediana`
      : `${decFmt.format(Math.abs(alert.deviation))} IQR além do ${alert.direction === "above" ? "p75" : "p25"}`;
  return `${labelOf(config, alert.indicator)} ${lado} do padrão do perfil: ${formatSimecNumber(alert.value, unit)} (${desvio}; base n=${alert.baseline.n})`;
}

/** Every panel window reports zero valid content and there are no readings. */
export function readoutIsEmpty(readout: SimecReadout): boolean {
  if (readout.readings.length > 0) return false;
  return Object.values(readout.panel ?? {}).every((w) => {
    const c = w?.conteudos_validos;
    return !c || c.status !== "ok" || (c.value ?? 0) === 0;
  });
}

export function needsReconnect(acc: SimecAccount): boolean {
  return acc.status !== "validated" || !acc.insights_scope_granted;
}

export function accountLabel(acc: SimecAccount): string {
  if (acc.username && acc.label && acc.label !== acc.username) return `@${acc.username} — ${acc.label}`;
  if (acc.username) return `@${acc.username}`;
  return acc.label ?? acc.account_id;
}

export function isDemo(source: string | null | undefined): boolean {
  return source === "fake";
}

// ─── Errors (contract § Error envelope) ─────────────────────────────────────

export type SimecErrorContext = "conta" | "leitura" | "config" | "geral";

function envelopeMessage(err: unknown): string | null {
  const msg = (err as { body?: { error?: { message?: unknown } } } | null)?.body?.error?.message;
  return typeof msg === "string" && msg ? msg : null;
}

/** The pt-BR sentence for a failed SIMEC request (contract error table). */
export function simecErrorMessage(err: unknown, ctx: SimecErrorContext = "geral"): string {
  const status = err instanceof ApiError ? err.status : (err as { status?: number } | null)?.status ?? null;
  switch (status) {
    case 400:
      return "Conta inválida.";
    case 401:
      return "Sua sessão expirou. Entre novamente.";
    case 403:
      return "A configuração do SIMEC é restrita a administradores.";
    case 404:
      return ctx === "leitura" ? "Leitura não encontrada." : "Conta não encontrada.";
    case 422:
      return envelopeMessage(err) ?? "Dados inválidos.";
    case 503:
      return "SIMEC indisponível no momento.";
    default:
      return envelopeMessage(err) ?? "Não foi possível carregar o SIMEC. Tente novamente.";
  }
}

// ─── Override layer editing (pure) ──────────────────────────────────────────

export type Path = readonly string[];

export function getPath(obj: unknown, path: Path): unknown {
  let cur: unknown = obj;
  for (const k of path) {
    if (!cur || typeof cur !== "object") return undefined;
    cur = (cur as Record<string, unknown>)[k];
  }
  return cur;
}

function clone<T>(x: T): T {
  return JSON.parse(JSON.stringify(x ?? {})) as T;
}

/** Remove `path` from `obj` (immutably) and prune parents left empty. */
export function deletePath(obj: Overrides, path: Path): Overrides {
  const out = clone(obj);
  const stack: Record<string, unknown>[] = [out];
  let cur: Record<string, unknown> = out;
  for (let i = 0; i < path.length - 1; i++) {
    const next = cur[path[i]];
    if (!next || typeof next !== "object") return out;
    cur = next as Record<string, unknown>;
    stack.push(cur);
  }
  delete cur[path[path.length - 1]];
  for (let i = path.length - 2; i >= 0; i--) {
    const parent = stack[i];
    const child = parent[path[i]];
    if (child && typeof child === "object" && Object.keys(child as object).length === 0) delete parent[path[i]];
    else break;
  }
  return out;
}

export function setPath(obj: Overrides, path: Path, value: unknown): Overrides {
  const out = clone(obj);
  let cur: Record<string, unknown> = out;
  for (let i = 0; i < path.length - 1; i++) {
    const next = cur[path[i]];
    if (!next || typeof next !== "object") cur[path[i]] = {};
    cur = cur[path[i]] as Record<string, unknown>;
  }
  cur[path[path.length - 1]] = value;
  return out;
}

/**
 * Set a field in a layer's overrides: a value equal to the layer BELOW
 * (`base`) is not an override — it is removed, so the layer stays minimal.
 */
export function applyFieldEdit(draft: Overrides, base: unknown, path: Path, value: unknown): Overrides {
  if (value === undefined || value === "" || (typeof value === "number" && Number.isNaN(value))) {
    return deletePath(draft, path);
  }
  if (getPath(base, path) === value) return deletePath(draft, path);
  return setPath(draft, path, value);
}

export function hasAnyPath(draft: Overrides, paths: readonly Path[]): boolean {
  return paths.some((p) => getPath(draft, p) !== undefined);
}

export function restoreItem(draft: Overrides, paths: readonly Path[]): Overrides {
  return paths.reduce<Overrides>((acc, p) => deletePath(acc, p), draft);
}

/** Stable comparison of two override objects (key order independent). */
export function sameOverrides(a: Overrides | null | undefined, b: Overrides | null | undefined): boolean {
  const norm = (x: unknown): unknown => {
    if (Array.isArray(x)) return x.map(norm);
    if (x && typeof x === "object") {
      return Object.keys(x as object)
        .sort()
        .reduce<Record<string, unknown>>((acc, k) => {
          acc[k] = norm((x as Record<string, unknown>)[k]);
          return acc;
        }, {});
    }
    return x;
  };
  return JSON.stringify(norm(a ?? {})) === JSON.stringify(norm(b ?? {}));
}
