/**
 * Shared building blocks for the Anúncios (Meta Ads) console subtabs —
 * date-range control, not-configured/empty/error state guards, the
 * objective-aware KPI model, and client-side account-period aggregation.
 *
 * NOTE on the aggregation: the `/api/meta/ads/*` contract is object-scoped
 * (campaign/adset/ad) — there is NO account-level insights aggregate
 * endpoint. So an account overview sums each campaign's `/insights/series`
 * for the window client-side (via `useAccountPeriodTotals`). Flagged as a
 * backend follow-up (an `/insights/account` aggregate would remove the N
 * fan-out); until then this is correct, just chattier.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Bookmark,
  CircleAlert,
  Download,
  FileText,
  Loader2,
  SlidersHorizontal,
  Trash2,
} from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { downloadAdsExport } from "@/hooks/useMetaAds";
import type {
  AdsActivity,
  AdsCampaign,
  AdsInsightsRow,
} from "@/hooks/useMetaAds";

// ─── activity change-log label ──────────────────────────────────────────────

const EVENT_LABELS: Record<string, string> = {
  update_ad_run_status: "Status alterado",
  ad_account_billing_charge: "Cobrança",
  update_campaign_budget: "Orçamento alterado",
  update_ad_set_budget: "Orçamento do conjunto alterado",
  first_delivery_event: "Primeira veiculação",
  create_campaign: "Campanha criada",
  update_campaign_run_status: "Status da campanha alterado",
};

/** Human, pt-BR label for a change-log event (old → new, actor). */
export function activityLabel(a: AdsActivity): string {
  const base = EVENT_LABELS[a.event_type ?? ""] ?? a.event_type ?? "Mudança";
  const change =
    a.old_value && a.new_value ? `: ${a.old_value} → ${a.new_value}` : "";
  const who = a.actor_name ? ` (${a.actor_name})` : "";
  return `${base}${change}${who}`;
}

// ─── Date range ─────────────────────────────────────────────────────────────

export type RangePreset = "7d" | "28d" | "this_month" | "last_month";

export interface DateRange {
  since: string; // YYYY-MM-DD
  until: string; // YYYY-MM-DD
}

function iso(d: Date): string {
  return d.toISOString().slice(0, 10);
}

export function rangeForPreset(preset: RangePreset, now = new Date()): DateRange {
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  if (preset === "7d") {
    const since = new Date(today);
    since.setDate(today.getDate() - 6);
    return { since: iso(since), until: iso(today) };
  }
  if (preset === "28d") {
    const since = new Date(today);
    since.setDate(today.getDate() - 27);
    return { since: iso(since), until: iso(today) };
  }
  if (preset === "this_month") {
    const since = new Date(today.getFullYear(), today.getMonth(), 1);
    return { since: iso(since), until: iso(today) };
  }
  // last_month
  const firstThis = new Date(today.getFullYear(), today.getMonth(), 1);
  const lastPrevEnd = new Date(firstThis);
  lastPrevEnd.setDate(0); // last day of previous month
  const lastPrevStart = new Date(lastPrevEnd.getFullYear(), lastPrevEnd.getMonth(), 1);
  return { since: iso(lastPrevStart), until: iso(lastPrevEnd) };
}

const PRESET_LABELS: Record<RangePreset, string> = {
  "7d": "Últimos 7 dias",
  "28d": "Últimos 28 dias",
  this_month: "Este mês",
  last_month: "Mês passado",
};

export function useDateRange(initial: RangePreset = "28d") {
  const [preset, setPreset] = useState<RangePreset>(initial);
  const range = useMemo(() => rangeForPreset(preset), [preset]);
  return { preset, setPreset, range };
}

export function DateRangeSelect({
  preset,
  onChange,
}: {
  preset: RangePreset;
  onChange: (p: RangePreset) => void;
}) {
  return (
    <div className="flex items-center gap-2">
      <SlidersHorizontal className="h-4 w-4 text-muted-foreground" />
      <Select value={preset} onValueChange={(v) => onChange(v as RangePreset)}>
        <SelectTrigger className="w-[180px]">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {(Object.keys(PRESET_LABELS) as RangePreset[]).map((p) => (
            <SelectItem key={p} value={p}>
              {PRESET_LABELS[p]}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}

// ─── Export (CSV / PDF) ─────────────────────────────────────────────────────

export function ExportButtons({
  since,
  until,
}: {
  since: string;
  until: string;
}) {
  const [busy, setBusy] = useState<"csv" | "pdf" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = useCallback(
    async (format: "csv" | "pdf") => {
      setBusy(format);
      setError(null);
      try {
        await downloadAdsExport(format, since, until);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Falha ao exportar");
      } finally {
        setBusy(null);
      }
    },
    [since, until],
  );

  return (
    <div className="flex items-center gap-2">
      <Button variant="outline" size="sm" disabled={busy !== null}
        onClick={() => run("csv")}>
        {busy === "csv" ? (
          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
        ) : (
          <Download className="mr-2 h-4 w-4" />
        )}
        CSV
      </Button>
      <Button variant="outline" size="sm" disabled={busy !== null}
        onClick={() => run("pdf")}>
        {busy === "pdf" ? (
          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
        ) : (
          <FileText className="mr-2 h-4 w-4" />
        )}
        PDF
      </Button>
      {error && <span className="text-xs text-destructive">{error}</span>}
    </div>
  );
}

// ─── Saved views (localStorage) ─────────────────────────────────────────────

const _SAVED_VIEWS_KEY = "meta-ads:saved-views";

interface SavedView {
  name: string;
  preset: RangePreset;
}

function _loadViews(): SavedView[] {
  try {
    const raw = localStorage.getItem(_SAVED_VIEWS_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

/** A named-date-range "saved view" store, persisted to localStorage. The
 *  saved view captures the date-range preset so an operator can jump back
 *  to a reporting window they use often. */
export function useSavedViews() {
  const [views, setViews] = useState<SavedView[]>(_loadViews);

  useEffect(() => {
    try {
      localStorage.setItem(_SAVED_VIEWS_KEY, JSON.stringify(views));
    } catch {
      /* private-mode / quota — non-fatal */
    }
  }, [views]);

  const save = useCallback((name: string, preset: RangePreset) => {
    const clean = name.trim();
    if (!clean) return;
    setViews((prev) => [
      ...prev.filter((v) => v.name !== clean),
      { name: clean, preset },
    ]);
  }, []);

  const remove = useCallback((name: string) => {
    setViews((prev) => prev.filter((v) => v.name !== name));
  }, []);

  return { views, save, remove };
}

export function SavedViewsControl({
  preset,
  onApply,
}: {
  preset: RangePreset;
  onApply: (preset: RangePreset) => void;
}) {
  const { views, save, remove } = useSavedViews();
  const [name, setName] = useState("");
  const [open, setOpen] = useState(false);

  return (
    <div className="flex items-center gap-2">
      {views.length > 0 && (
        <Select onValueChange={(n) => {
          const v = views.find((x) => x.name === n);
          if (v) onApply(v.preset);
        }}>
          <SelectTrigger className="h-9 w-[160px]">
            <Bookmark className="mr-1.5 h-3.5 w-3.5" />
            <SelectValue placeholder="Visões salvas" />
          </SelectTrigger>
          <SelectContent>
            {views.map((v) => (
              <div key={v.name} className="flex items-center justify-between pr-1">
                <SelectItem value={v.name} className="flex-1">{v.name}</SelectItem>
                <button
                  className="p-1 text-muted-foreground hover:text-destructive"
                  onClick={(e) => { e.preventDefault(); remove(v.name); }}
                  aria-label={`Remover ${v.name}`}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            ))}
          </SelectContent>
        </Select>
      )}
      {open ? (
        <div className="flex items-center gap-1">
          <Input
            autoFocus
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Nome da visão"
            className="h-9 w-[150px]"
            onKeyDown={(e) => {
              if (e.key === "Enter") { save(name, preset); setName(""); setOpen(false); }
              if (e.key === "Escape") setOpen(false);
            }}
          />
          <Button size="sm" variant="secondary"
            onClick={() => { save(name, preset); setName(""); setOpen(false); }}>
            Salvar
          </Button>
        </div>
      ) : (
        <Button size="sm" variant="ghost" onClick={() => setOpen(true)}>
          <Bookmark className="mr-1.5 h-3.5 w-3.5" /> Salvar visão
        </Button>
      )}
    </div>
  );
}

// ─── State guards (never a zeros dashboard) ─────────────────────────────────

export function AdsLoading({ label = "Carregando…" }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-16 text-muted-foreground">
      <Loader2 className="h-5 w-5 animate-spin" />
      <span className="text-sm">{label}</span>
    </div>
  );
}

export function AdsNotConfigured({ detail }: { detail?: string | null }) {
  return (
    <Card className="border-dashed">
      <CardContent className="flex flex-col items-center gap-3 py-14 text-center">
        <CircleAlert className="h-8 w-8 text-muted-foreground" />
        <div className="text-lg font-medium">Anúncios não configurado</div>
        <p className="max-w-md text-sm text-muted-foreground">
          {detail ??
            "Nenhuma conta de anúncios do Meta está conectada. Configure o token de Usuário do Sistema e a conta de anúncios (META_AD_ACCOUNT_ID) para ver suas campanhas aqui."}
        </p>
      </CardContent>
    </Card>
  );
}

export function AdsError({
  message,
  onRetry,
}: {
  message?: string | null;
  onRetry?: () => void;
}) {
  return (
    <Card className="border-destructive/40">
      <CardContent className="flex flex-col items-center gap-3 py-12 text-center">
        <CircleAlert className="h-7 w-7 text-destructive" />
        <div className="font-medium">Não foi possível carregar os anúncios</div>
        <p className="max-w-md text-sm text-muted-foreground">
          {message ??
            "O Meta retornou um erro (possível limite de requisições). Tente novamente em alguns minutos."}
        </p>
        {onRetry && (
          <Button variant="outline" size="sm" onClick={onRetry}>
            Tentar de novo
          </Button>
        )}
      </CardContent>
    </Card>
  );
}

// ─── status badge (shared: Campanhas table + AdDetalheModal header) ────────

/** ACTIVE/PAUSED/... → pt-BR badge label + Tailwind class. Lifted out of
 *  AdsCampanhas (was file-local) so AdDetalheModal renders the identical
 *  badge for an ad's own effective_status, not a re-implementation. */
export function statusVariant(effective?: string | null): {
  label: string;
  cls: string;
} {
  const s = (effective ?? "").toUpperCase();
  if (s === "ACTIVE") return { label: "Ativa", cls: "bg-emerald-500/15 text-emerald-600 border-emerald-500/30" };
  if (s === "PAUSED") return { label: "Pausada", cls: "bg-amber-500/15 text-amber-600 border-amber-500/30" };
  if (s.includes("REVIEW")) return { label: "Em análise", cls: "bg-blue-500/15 text-blue-600 border-blue-500/30" };
  if (s === "DELETED" || s === "ARCHIVED") return { label: "Arquivada", cls: "bg-muted text-muted-foreground" };
  return { label: effective ?? "—", cls: "bg-muted text-muted-foreground" };
}

// ─── period-comparison math (shared: VisaoGeral + AdDetalheModal) ──────────

/** `(curr - prev) / prev * 100`, or null when there's no prior baseline —
 *  the single pct-change formula every Δ% tile in the Ads console uses. */
export function pct(curr: number, prev: number): number | null {
  if (!prev) return null;
  return ((curr - prev) / prev) * 100;
}

// ─── actions helpers ────────────────────────────────────────────────────────

/** Leads for a row — the SUM of Meta's two lead action keys.
 *
 * `actions["lead"]` (off-Facebook pixel/CAPI Lead event) and
 * `actions["onsite_conversion.lead"]` (native Instant Form submission) are
 * distinct CAPTURE CHANNELS, not two names for the same number. A campaign
 * with "Website + Instant forms" conversion locations legitimately populates
 * both on one row, so the total is their sum.
 *
 * This was `a ?? b` — first-key-wins — which silently dropped the second
 * channel on any mixed-mechanism row. It read as correct because the pilot
 * account populates only `onsite_conversion.lead`, where the two agree.
 * Kept deliberately in lockstep with the backend's
 * `meta_ads/services/leads.py::leads_from_actions`: two different
 * reconciliation semantics across the BE/FE seam is a drift bug waiting to
 * happen, and the backend is the one that had to be fixed first.
 */
export function rowLeads(row: AdsInsightsRow): number {
  const a = row.actions ?? {};
  return (a["lead"] ?? 0) + (a["onsite_conversion.lead"] ?? 0);
}

export function rowAction(row: AdsInsightsRow, key: string): number {
  return row.actions?.[key] ?? 0;
}

/** True when ANY row carries a purchase value → a ROAS tile is meaningful.
 *  On the pilot (lead-gen) account this is always false, so no dead ROAS. */
export function seriesHasPurchaseValue(rows: AdsInsightsRow[]): boolean {
  return rows.some((r) => Object.keys(r.action_values ?? {}).length > 0);
}

// ─── Objective-aware KPI model ──────────────────────────────────────────────

export type Objective =
  | "OUTCOME_LEADS"
  | "OUTCOME_TRAFFIC"
  | "OUTCOME_ENGAGEMENT"
  | "OUTCOME_AWARENESS"
  | "OUTCOME_SALES"
  | string;

/** The dominant objective across campaigns (most frequent). Drives which
 *  objective-specific KPI tiles the overview renders. */
export function dominantObjective(campaigns: AdsCampaign[]): Objective | null {
  const counts = new Map<string, number>();
  for (const c of campaigns) {
    if (!c.objective) continue;
    counts.set(c.objective, (counts.get(c.objective) ?? 0) + 1);
  }
  let best: string | null = null;
  let bestN = 0;
  for (const [obj, n] of counts) {
    if (n > bestN) {
      best = obj;
      bestN = n;
    }
  }
  return best;
}

