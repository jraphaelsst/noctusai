/**
 * Report snapshot payload -> display items (shared by the internal detail view
 * and the public page). No raw JSON ever reaches the screen.
 *
 * Payload shape (BE reports service): leads, revenues, expenses, scope,
 * meta_ads { spend, leads, cpl, active_campaigns }. For client-scoped reports
 * `expenses` may be `{ available: false, reason }` (expenses are not
 * attributable to a client) — internal view: "Indisponível" + a pt-BR reason;
 * public (client-facing) view: omitted. Metadata keys never become tiles.
 */
export type PayloadKind = "number" | "money" | "text" | "unavailable";

export interface PayloadItem {
  key: string;
  label: string;
  kind: PayloadKind;
  value: number | string | null;
  hint?: string;
}

const SCOPE_LABEL: Record<string, string> = {
  client: "Cliente",
  org: "Agência (todos os clientes)",
  agency: "Agência (todos os clientes)",
};

/** Backend reasons are English developer strings; never show them raw. */
const REASON_PT: Record<string, string> = {
  "expenses are not attributed to clients": "Despesas não são vinculadas a clientes — veja o relatório da agência.",
};

/** Snapshot bookkeeping, not metrics: the pages show these elsewhere (header). */
const METADATA_KEYS = new Set(["generated_at", "period_start", "period_end", "report_id", "client_id", "org_id"]);

export interface DescribeOptions {
  /** "public" = the client-facing page: drop unavailable metrics and the scope line. */
  audience?: "internal" | "public";
}

const isObj = (v: unknown): v is Record<string, unknown> =>
  typeof v === "object" && v !== null && !Array.isArray(v);

export function describePayload(
  payload: Record<string, unknown>,
  { audience = "internal" }: DescribeOptions = {},
): PayloadItem[] {
  const out: PayloadItem[] = [];
  const isPublic = audience === "public";

  if (typeof payload.leads === "number")
    out.push({ key: "leads", label: "Leads gerados", kind: "number", value: payload.leads });
  if (typeof payload.revenues === "number")
    out.push({ key: "revenues", label: "Receitas", kind: "money", value: payload.revenues });

  const exp = payload.expenses;
  if (typeof exp === "number") {
    out.push({ key: "expenses", label: "Despesas", kind: "money", value: exp });
  } else if (isObj(exp) && exp.available === false && !isPublic) {
    out.push({
      key: "expenses",
      label: "Despesas",
      kind: "unavailable",
      value: null,
      hint:
        typeof exp.reason === "string" && REASON_PT[exp.reason]
          ? REASON_PT[exp.reason]
          : "Não disponível para este escopo.",
    });
  }

  const meta = payload.meta_ads;
  if (isObj(meta)) {
    if (typeof meta.spend === "number")
      out.push({ key: "meta_spend", label: "Investimento em anúncios", kind: "money", value: meta.spend, hint: "Lançado manualmente" });
    if (typeof meta.leads === "number")
      out.push({ key: "meta_leads", label: "Leads de anúncios", kind: "number", value: meta.leads });
    if (typeof meta.cpl === "number")
      out.push({ key: "meta_cpl", label: "CPL", kind: "money", value: meta.cpl });
    if (typeof meta.active_campaigns === "number")
      out.push({ key: "meta_active", label: "Campanhas ativas", kind: "number", value: meta.active_campaigns });
  }

  if (typeof payload.scope === "string" && !isPublic)
    out.push({ key: "scope", label: "Escopo", kind: "text", value: SCOPE_LABEL[payload.scope] ?? payload.scope });

  const handled = new Set(["leads", "revenues", "expenses", "meta_ads", "scope"]);
  for (const [k, v] of Object.entries(payload)) {
    if (handled.has(k) || METADATA_KEYS.has(k) || v === null || v === undefined) continue;
    if (typeof v === "number") out.push({ key: k, label: k.replace(/_/g, " "), kind: "number", value: v });
    else if (typeof v === "string") out.push({ key: k, label: k.replace(/_/g, " "), kind: "text", value: v });
  }
  return out;
}

export function formatPayloadValue(item: PayloadItem): string {
  if (item.kind === "unavailable") return "Indisponível";
  if (item.kind === "money" && typeof item.value === "number")
    return new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(item.value);
  if (typeof item.value === "number") return item.value.toLocaleString("pt-BR");
  return String(item.value ?? "—");
}
