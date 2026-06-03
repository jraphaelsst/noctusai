/**
 * Trafego — Meta Ads / Tráfego module for Orbity.
 *
 * Tabs:
 *   1. Campanhas      — dashboard list with situation chips, filters,
 *                       create/edit/delete, aggregate summary card, Sync button.
 *   2. Contas         — ad accounts list + connect/edit/disconnect.
 *
 * Every section ships all four states: loading / empty / error / success.
 *
 * Nav route keys:
 *   "trafego"            — this page (Campanhas + Contas as inner tabs)
 *
 * Requires status_pagina rows:
 *   page_key = "trafego"
 */
import { useState } from "react";
import { format, subMonths } from "date-fns";
import {
  Target,
  Plus,
  Pencil,
  Trash2,
  Loader2,
  AlertCircle,
  FileText,
  RefreshCw,
  Megaphone,
  BarChart3,
  TrendingUp,
  Users,
  X,
  CheckCircle2,
  AlertTriangle,
  XCircle,
} from "lucide-react";
import {
  useAdAccounts,
  useCreateAdAccount,
  useUpdateAdAccount,
  useDeleteAdAccount,
  useCampaigns,
  useCreateCampaign,
  useUpdateCampaign,
  useDeleteCampaign,
  useUpdateSituation,
  useSyncCampaigns,
  useSpendLeadsAggregate,
  type AdAccount,
  type AdAccountStatus,
  type AdAccountCreate,
  type Campaign,
  type CampaignStatus,
  type CampaignCreate,
  type CampaignUpdate,
  type SituationLiteral,
  type CampaignFilters,
} from "@/hooks/useMetaAds";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmtCurrency(value: number): string {
  return value.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

type TabKey = "campanhas" | "contas";

// ---------------------------------------------------------------------------
// Shared state renderers
// ---------------------------------------------------------------------------

function LoadingState({ label }: { label: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 gap-3">
      <Loader2 className="h-7 w-7 animate-spin text-primary" />
      <p className="text-sm text-muted-foreground">{label}</p>
    </div>
  );
}

function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div className="flex flex-col items-center justify-center py-16 gap-3 text-destructive">
      <AlertCircle className="h-7 w-7" />
      <p className="text-sm font-medium">Erro ao carregar dados</p>
      <p className="text-xs text-muted-foreground max-w-sm text-center">
        {message}
      </p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-1 rounded-md border border-destructive/30 bg-destructive/10 px-4 py-1.5 text-xs font-medium text-destructive hover:bg-destructive/20 transition-colors"
        >
          Tentar novamente
        </button>
      )}
    </div>
  );
}

function EmptyState({ label, onAdd }: { label: string; onAdd?: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 gap-3">
      <FileText className="h-8 w-8 text-muted-foreground/40" />
      <p className="text-sm text-muted-foreground">{label}</p>
      {onAdd && (
        <button
          onClick={onAdd}
          className="mt-1 inline-flex items-center gap-1.5 rounded-md bg-primary px-4 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
        >
          <Plus className="h-3.5 w-3.5" />
          Adicionar
        </button>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Situation chip
// ---------------------------------------------------------------------------

const SITUATION_LABEL: Record<SituationLiteral, string> = {
  "on-track": "No Prazo",
  attention: "Atenção",
  off: "Fora do Prazo",
};

const SITUATION_COLORS: Record<SituationLiteral, string> = {
  "on-track":
    "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400",
  attention:
    "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400",
  off: "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400",
};

const SITUATION_ICONS: Record<SituationLiteral, React.ElementType> = {
  "on-track": CheckCircle2,
  attention: AlertTriangle,
  off: XCircle,
};

function SituationChip({ value }: { value: SituationLiteral }) {
  const Icon = SITUATION_ICONS[value];
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ${SITUATION_COLORS[value]}`}
    >
      <Icon className="h-3 w-3" />
      {SITUATION_LABEL[value]}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Campaign status badge
// ---------------------------------------------------------------------------

const CAMPAIGN_STATUS_LABEL: Record<CampaignStatus, string> = {
  active: "Ativa",
  paused: "Pausada",
  archived: "Arquivada",
  deleted: "Deletada",
};

const CAMPAIGN_STATUS_COLORS: Record<CampaignStatus, string> = {
  active:
    "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400",
  paused:
    "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400",
  archived: "bg-gray-100 text-gray-600 dark:bg-gray-900/30 dark:text-gray-400",
  deleted: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
};

// ---------------------------------------------------------------------------
// Ad account status badge
// ---------------------------------------------------------------------------

const AD_ACCOUNT_STATUS_LABEL: Record<AdAccountStatus, string> = {
  active: "Ativa",
  paused: "Pausada",
  disconnected: "Desconectada",
  error: "Erro",
};

const AD_ACCOUNT_STATUS_COLORS: Record<AdAccountStatus, string> = {
  active:
    "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400",
  paused:
    "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400",
  disconnected:
    "bg-gray-100 text-gray-600 dark:bg-gray-900/30 dark:text-gray-400",
  error: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
};

// ---------------------------------------------------------------------------
// Aggregate summary card
// ---------------------------------------------------------------------------

function AggregateCard() {
  const today = new Date();
  const periodEnd = format(today, "yyyy-MM-dd");
  const periodStart = format(subMonths(today, 1), "yyyy-MM-dd");

  const { data, isLoading, error } = useSpendLeadsAggregate(
    periodStart,
    periodEnd,
  );

  if (isLoading) {
    return (
      <div className="rounded-lg border border-border bg-card p-5 flex items-center gap-3">
        <Loader2 className="h-5 w-5 animate-spin text-primary" />
        <span className="text-sm text-muted-foreground">
          Carregando resumo...
        </span>
      </div>
    );
  }

  if (error || !data) {
    return null;
  }

  const cards = [
    {
      label: "Investimento Total",
      value: fmtCurrency(data.total_spend),
      icon: TrendingUp,
      color: "text-blue-600",
      bg: "bg-blue-50 dark:bg-blue-950/30",
      border: "border-blue-200 dark:border-blue-900",
    },
    {
      label: "Total de Leads",
      value: String(data.total_leads),
      icon: Users,
      color: "text-green-600",
      bg: "bg-green-50 dark:bg-green-950/30",
      border: "border-green-200 dark:border-green-900",
    },
    {
      label: "CPL Médio",
      value:
        data.total_leads > 0
          ? fmtCurrency(data.total_spend / data.total_leads)
          : "—",
      icon: BarChart3,
      color: "text-purple-600",
      bg: "bg-purple-50 dark:bg-purple-950/30",
      border: "border-purple-200 dark:border-purple-900",
    },
  ];

  return (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
      {cards.map((card) => {
        const Icon = card.icon;
        return (
          <div
            key={card.label}
            className={`rounded-lg border ${card.border} ${card.bg} p-5 flex flex-col gap-2`}
          >
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-muted-foreground">
                {card.label}
              </span>
              <Icon className={`h-4 w-4 ${card.color}`} />
            </div>
            <p className={`text-xl font-bold ${card.color}`}>{card.value}</p>
            <p className="text-xs text-muted-foreground">Últimos 30 dias</p>
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Campaign dialog (create / edit)
// ---------------------------------------------------------------------------

interface CampaignDialogProps {
  open: boolean;
  editing: Campaign | null;
  adAccounts: AdAccount[];
  onClose: () => void;
}

function CampaignDialog({
  open,
  editing,
  adAccounts,
  onClose,
}: CampaignDialogProps) {
  const createMut = useCreateCampaign();
  const updateMut = useUpdateCampaign();

  const [form, setForm] = useState<
    CampaignCreate & { id?: string }
  >({
    ad_account_id: editing?.ad_account_id ?? adAccounts[0]?.id ?? "",
    external_campaign_id: editing?.external_campaign_id ?? "",
    name: editing?.name ?? "",
    objective: editing?.objective ?? "",
    status: editing?.status ?? "active",
    daily_budget: editing?.daily_budget ?? undefined,
    result_metric: editing?.result_metric ?? "",
    situation: editing?.situation ?? "on-track",
  });

  if (!open) return null;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const payload = {
      ...form,
      objective: form.objective || undefined,
      result_metric: form.result_metric || undefined,
      daily_budget: form.daily_budget ?? undefined,
    };
    if (editing) {
      const updatePayload: CampaignUpdate = {
        id: editing.id,
        name: payload.name,
        objective: payload.objective,
        status: payload.status,
        daily_budget: payload.daily_budget,
        result_metric: payload.result_metric,
        situation: payload.situation,
      };
      await updateMut.mutateAsync(updatePayload);
    } else {
      await createMut.mutateAsync(payload);
    }
    onClose();
  }

  const isPending = createMut.isPending || updateMut.isPending;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={onClose}
    >
      <div
        className="w-full max-w-[calc(100vw-2rem)] sm:max-w-lg rounded-lg border border-border bg-card p-6 shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-foreground">
            {editing ? "Editar campanha" : "Nova campanha"}
          </h2>
          <button
            onClick={onClose}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-muted transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          {!editing && (
            <div>
              <label className="mb-1 block text-sm font-medium text-foreground">
                Conta de Anúncio *
              </label>
              <select
                required
                value={form.ad_account_id}
                onChange={(e) =>
                  setForm((f) => ({ ...f, ad_account_id: e.target.value }))
                }
                className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                {adAccounts.map((acc) => (
                  <option key={acc.id} value={acc.id}>
                    {acc.name}
                  </option>
                ))}
              </select>
            </div>
          )}
          {!editing && (
            <div>
              <label className="mb-1 block text-sm font-medium text-foreground">
                ID Externo (Meta) *
              </label>
              <input
                type="text"
                required
                value={form.external_campaign_id}
                onChange={(e) =>
                  setForm((f) => ({
                    ...f,
                    external_campaign_id: e.target.value,
                  }))
                }
                className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                placeholder="ex: 12345678901234"
              />
            </div>
          )}
          <div>
            <label className="mb-1 block text-sm font-medium text-foreground">
              Nome *
            </label>
            <input
              type="text"
              required
              value={form.name}
              onChange={(e) =>
                setForm((f) => ({ ...f, name: e.target.value }))
              }
              className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-sm font-medium text-foreground">
                Objetivo
              </label>
              <input
                type="text"
                value={form.objective ?? ""}
                onChange={(e) =>
                  setForm((f) => ({ ...f, objective: e.target.value }))
                }
                className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                placeholder="ex: LEAD_GENERATION"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-foreground">
                Orçamento Diário (R$)
              </label>
              <input
                type="number"
                min="0"
                step="0.01"
                value={form.daily_budget ?? ""}
                onChange={(e) =>
                  setForm((f) => ({
                    ...f,
                    daily_budget: e.target.value
                      ? parseFloat(e.target.value)
                      : undefined,
                  }))
                }
                className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-sm font-medium text-foreground">
                Status
              </label>
              <select
                value={form.status}
                onChange={(e) =>
                  setForm((f) => ({
                    ...f,
                    status: e.target.value as CampaignStatus,
                  }))
                }
                className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <option value="active">Ativa</option>
                <option value="paused">Pausada</option>
                <option value="archived">Arquivada</option>
              </select>
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-foreground">
                Situação
              </label>
              <select
                value={form.situation}
                onChange={(e) =>
                  setForm((f) => ({
                    ...f,
                    situation: e.target.value as SituationLiteral,
                  }))
                }
                className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <option value="on-track">No Prazo</option>
                <option value="attention">Atenção</option>
                <option value="off">Fora do Prazo</option>
              </select>
            </div>
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-foreground">
              Métrica de Resultado
            </label>
            <input
              type="text"
              value={form.result_metric ?? ""}
              onChange={(e) =>
                setForm((f) => ({ ...f, result_metric: e.target.value }))
              }
              className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              placeholder="ex: leads, conversoes"
            />
          </div>
          <div className="flex justify-end gap-3 pt-1">
            <button
              type="button"
              onClick={onClose}
              className="rounded-md border border-border bg-background px-4 py-2 text-sm text-foreground hover:bg-muted transition-colors"
            >
              Cancelar
            </button>
            <button
              type="submit"
              disabled={isPending}
              className="inline-flex items-center gap-2 rounded-md bg-primary px-5 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isPending ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Salvando...
                </>
              ) : editing ? (
                "Salvar alterações"
              ) : (
                "Criar campanha"
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Campaigns tab
// ---------------------------------------------------------------------------

function CampanhasTab() {
  const [filters, setFilters] = useState<CampaignFilters>({});
  const { data, isLoading, error, refetch } = useCampaigns(filters);
  const { data: accountsData } = useAdAccounts();
  const deleteMut = useDeleteCampaign();
  const situationMut = useUpdateSituation();
  const syncMut = useSyncCampaigns();

  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<Campaign | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<Campaign | null>(null);

  const adAccounts = accountsData?.items ?? [];
  const campaigns = data?.items ?? [];

  return (
    <div className="space-y-6">
      {/* Aggregate summary */}
      <AggregateCard />

      {/* Filters row */}
      <div className="flex flex-wrap items-center gap-3">
        <select
          value={filters.situation ?? ""}
          onChange={(e) =>
            setFilters((f) => ({
              ...f,
              situation: (e.target.value as SituationLiteral) || undefined,
            }))
          }
          className="flex h-9 rounded-md border border-input bg-background px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <option value="">Todas as situações</option>
          <option value="on-track">No Prazo</option>
          <option value="attention">Atenção</option>
          <option value="off">Fora do Prazo</option>
        </select>

        <select
          value={filters.ad_account_id ?? ""}
          onChange={(e) =>
            setFilters((f) => ({
              ...f,
              ad_account_id: e.target.value || undefined,
            }))
          }
          className="flex h-9 rounded-md border border-input bg-background px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <option value="">Todas as contas</option>
          {adAccounts.map((acc) => (
            <option key={acc.id} value={acc.id}>
              {acc.name}
            </option>
          ))}
        </select>

        <select
          value={filters.status ?? ""}
          onChange={(e) =>
            setFilters((f) => ({
              ...f,
              status: (e.target.value as CampaignStatus) || undefined,
            }))
          }
          className="flex h-9 rounded-md border border-input bg-background px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <option value="">Todos os status</option>
          <option value="active">Ativa</option>
          <option value="paused">Pausada</option>
          <option value="archived">Arquivada</option>
        </select>

        <div className="ml-auto flex items-center gap-2">
          {adAccounts.length > 0 && (
            <button
              onClick={() => syncMut.mutate(filters.ad_account_id ?? adAccounts[0].id)}
              disabled={syncMut.isPending}
              className="inline-flex items-center gap-2 rounded-md border border-border bg-background px-4 py-2 text-sm font-medium text-foreground hover:bg-muted transition-colors disabled:opacity-50"
            >
              {syncMut.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <RefreshCw className="h-4 w-4" />
              )}
              Sincronizar
            </button>
          )}
          <button
            onClick={() => {
              setEditing(null);
              setDialogOpen(true);
            }}
            disabled={adAccounts.length === 0}
            className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Plus className="h-4 w-4" />
            Nova campanha
          </button>
        </div>
      </div>

      {/* Content */}
      {isLoading ? (
        <LoadingState label="Carregando campanhas..." />
      ) : error ? (
        <ErrorState message={error.message} onRetry={() => refetch()} />
      ) : campaigns.length === 0 ? (
        <EmptyState
          label="Nenhuma campanha encontrada"
          onAdd={
            adAccounts.length > 0
              ? () => {
                  setEditing(null);
                  setDialogOpen(true);
                }
              : undefined
          }
        />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-border bg-muted/50">
              <tr>
                <th className="px-4 py-3 font-medium text-muted-foreground">
                  Campanha
                </th>
                <th className="px-4 py-3 font-medium text-muted-foreground hidden sm:table-cell">
                  Status
                </th>
                <th className="px-4 py-3 font-medium text-muted-foreground">
                  Situação
                </th>
                <th className="px-4 py-3 font-medium text-muted-foreground hidden md:table-cell">
                  Orçamento/dia
                </th>
                <th className="px-4 py-3 font-medium text-muted-foreground">
                  Ações
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {campaigns.map((campaign) => (
                <tr
                  key={campaign.id}
                  className="bg-card hover:bg-muted/20 transition-colors"
                >
                  <td className="px-4 py-3">
                    <div className="font-medium text-foreground max-w-[200px] truncate">
                      {campaign.name}
                    </div>
                    {campaign.objective && (
                      <div className="text-xs text-muted-foreground truncate max-w-[180px]">
                        {campaign.objective}
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-3 hidden sm:table-cell">
                    <span
                      className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${CAMPAIGN_STATUS_COLORS[campaign.status as CampaignStatus]}`}
                    >
                      {CAMPAIGN_STATUS_LABEL[campaign.status as CampaignStatus]}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <select
                      value={campaign.situation}
                      onChange={(e) =>
                        situationMut.mutate({
                          id: campaign.id,
                          situation: e.target.value as SituationLiteral,
                        })
                      }
                      className="appearance-none rounded border-none bg-transparent text-xs font-medium cursor-pointer focus:outline-none"
                      style={{ padding: 0 }}
                      aria-label="Situação da campanha"
                    >
                      <option value="on-track">No Prazo</option>
                      <option value="attention">Atenção</option>
                      <option value="off">Fora do Prazo</option>
                    </select>
                    <span className="sr-only">
                      <SituationChip value={campaign.situation as SituationLiteral} />
                    </span>
                    <SituationChip
                      value={campaign.situation as SituationLiteral}
                    />
                  </td>
                  <td className="px-4 py-3 text-foreground hidden md:table-cell">
                    {campaign.daily_budget != null
                      ? fmtCurrency(campaign.daily_budget)
                      : "—"}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => {
                          setEditing(campaign);
                          setDialogOpen(true);
                        }}
                        className="rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
                        title="Editar"
                      >
                        <Pencil className="h-4 w-4" />
                      </button>
                      <button
                        onClick={() => setConfirmDelete(campaign)}
                        className="rounded-md p-1.5 text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition-colors"
                        title="Remover"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <CampaignDialog
        open={dialogOpen}
        editing={editing}
        adAccounts={adAccounts}
        onClose={() => setDialogOpen(false)}
      />

      {confirmDelete && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
          onClick={() => setConfirmDelete(null)}
        >
          <div
            className="w-full max-w-[calc(100vw-2rem)] sm:max-w-md rounded-lg border border-border bg-card p-6 shadow-lg"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="mb-2 text-lg font-semibold text-foreground">
              Remover campanha
            </h2>
            <p className="mb-6 text-sm text-muted-foreground">
              Tem certeza que deseja remover a campanha{" "}
              <strong className="text-foreground">{confirmDelete.name}</strong>?
              Esta ação não pode ser desfeita.
            </p>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setConfirmDelete(null)}
                className="rounded-md border border-border bg-background px-4 py-2 text-sm text-foreground hover:bg-muted transition-colors"
              >
                Cancelar
              </button>
              <button
                onClick={() => {
                  deleteMut.mutate(confirmDelete.id, {
                    onSettled: () => setConfirmDelete(null),
                  });
                }}
                disabled={deleteMut.isPending}
                className="inline-flex items-center gap-2 rounded-md bg-destructive px-5 py-2 text-sm font-medium text-destructive-foreground hover:bg-destructive/90 transition-colors disabled:opacity-50"
              >
                {deleteMut.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : null}
                Confirmar remoção
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Ad account dialog (connect / edit)
// ---------------------------------------------------------------------------

interface AdAccountDialogProps {
  open: boolean;
  editing: AdAccount | null;
  onClose: () => void;
}

function AdAccountDialog({ open, editing, onClose }: AdAccountDialogProps) {
  const createMut = useCreateAdAccount();
  const updateMut = useUpdateAdAccount();

  const [form, setForm] = useState<AdAccountCreate & { id?: string }>({
    external_account_id: editing?.external_account_id ?? "",
    name: editing?.name ?? "",
    status: editing?.status ?? "active",
    client_id: editing?.client_id ?? undefined,
  });

  if (!open) return null;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (editing) {
      await updateMut.mutateAsync({
        id: editing.id,
        name: form.name,
        status: form.status,
        client_id: form.client_id || undefined,
      });
    } else {
      await createMut.mutateAsync({
        external_account_id: form.external_account_id,
        name: form.name,
        status: form.status,
        client_id: form.client_id || undefined,
      });
    }
    onClose();
  }

  const isPending = createMut.isPending || updateMut.isPending;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={onClose}
    >
      <div
        className="w-full max-w-[calc(100vw-2rem)] sm:max-w-lg rounded-lg border border-border bg-card p-6 shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-foreground">
            {editing ? "Editar conta de anúncio" : "Conectar conta de anúncio"}
          </h2>
          <button
            onClick={onClose}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-muted transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          {!editing && (
            <div>
              <label className="mb-1 block text-sm font-medium text-foreground">
                ID da Conta (Meta) *
              </label>
              <input
                type="text"
                required
                value={form.external_account_id}
                onChange={(e) =>
                  setForm((f) => ({
                    ...f,
                    external_account_id: e.target.value,
                  }))
                }
                className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                placeholder="ex: act_123456789"
              />
            </div>
          )}
          <div>
            <label className="mb-1 block text-sm font-medium text-foreground">
              Nome *
            </label>
            <input
              type="text"
              required
              value={form.name}
              onChange={(e) =>
                setForm((f) => ({ ...f, name: e.target.value }))
              }
              className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-foreground">
              Status
            </label>
            <select
              value={form.status}
              onChange={(e) =>
                setForm((f) => ({
                  ...f,
                  status: e.target.value as AdAccountStatus,
                }))
              }
              className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <option value="active">Ativa</option>
              <option value="paused">Pausada</option>
              <option value="disconnected">Desconectada</option>
            </select>
          </div>
          <div className="flex justify-end gap-3 pt-1">
            <button
              type="button"
              onClick={onClose}
              className="rounded-md border border-border bg-background px-4 py-2 text-sm text-foreground hover:bg-muted transition-colors"
            >
              Cancelar
            </button>
            <button
              type="submit"
              disabled={isPending}
              className="inline-flex items-center gap-2 rounded-md bg-primary px-5 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isPending ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Salvando...
                </>
              ) : editing ? (
                "Salvar alterações"
              ) : (
                "Conectar conta"
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Ad accounts tab
// ---------------------------------------------------------------------------

function ContasTab() {
  const { data, isLoading, error, refetch } = useAdAccounts();
  const deleteMut = useDeleteAdAccount();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<AdAccount | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<AdAccount | null>(null);

  const accounts = data?.items ?? [];

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <button
          onClick={() => {
            setEditing(null);
            setDialogOpen(true);
          }}
          className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
        >
          <Plus className="h-4 w-4" />
          Conectar conta
        </button>
      </div>

      {isLoading ? (
        <LoadingState label="Carregando contas de anúncio..." />
      ) : error ? (
        <ErrorState message={error.message} onRetry={() => refetch()} />
      ) : accounts.length === 0 ? (
        <EmptyState
          label="Nenhuma conta de anúncio conectada"
          onAdd={() => {
            setEditing(null);
            setDialogOpen(true);
          }}
        />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-border bg-muted/50">
              <tr>
                <th className="px-4 py-3 font-medium text-muted-foreground">
                  Nome
                </th>
                <th className="px-4 py-3 font-medium text-muted-foreground hidden sm:table-cell">
                  ID Externo
                </th>
                <th className="px-4 py-3 font-medium text-muted-foreground">
                  Status
                </th>
                <th className="px-4 py-3 font-medium text-muted-foreground hidden md:table-cell">
                  Conectado em
                </th>
                <th className="px-4 py-3 font-medium text-muted-foreground">
                  Ações
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {accounts.map((account) => (
                <tr
                  key={account.id}
                  className="bg-card hover:bg-muted/20 transition-colors"
                >
                  <td className="px-4 py-3 font-medium text-foreground">
                    <div className="max-w-[200px] truncate">{account.name}</div>
                  </td>
                  <td className="px-4 py-3 text-muted-foreground hidden sm:table-cell font-mono text-xs">
                    {account.external_account_id}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${AD_ACCOUNT_STATUS_COLORS[account.status as AdAccountStatus]}`}
                    >
                      {AD_ACCOUNT_STATUS_LABEL[account.status as AdAccountStatus]}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-foreground hidden md:table-cell text-sm">
                    {new Date(account.connected_at).toLocaleDateString("pt-BR")}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => {
                          setEditing(account);
                          setDialogOpen(true);
                        }}
                        className="rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
                        title="Editar"
                      >
                        <Pencil className="h-4 w-4" />
                      </button>
                      <button
                        onClick={() => setConfirmDelete(account)}
                        className="rounded-md p-1.5 text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition-colors"
                        title="Desconectar"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <AdAccountDialog
        open={dialogOpen}
        editing={editing}
        onClose={() => setDialogOpen(false)}
      />

      {confirmDelete && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
          onClick={() => setConfirmDelete(null)}
        >
          <div
            className="w-full max-w-[calc(100vw-2rem)] sm:max-w-md rounded-lg border border-border bg-card p-6 shadow-lg"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="mb-2 text-lg font-semibold text-foreground">
              Desconectar conta
            </h2>
            <p className="mb-6 text-sm text-muted-foreground">
              Tem certeza que deseja desconectar a conta{" "}
              <strong className="text-foreground">{confirmDelete.name}</strong>?
              As campanhas vinculadas serão mantidas.
            </p>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setConfirmDelete(null)}
                className="rounded-md border border-border bg-background px-4 py-2 text-sm text-foreground hover:bg-muted transition-colors"
              >
                Cancelar
              </button>
              <button
                onClick={() => {
                  deleteMut.mutate(confirmDelete.id, {
                    onSettled: () => setConfirmDelete(null),
                  });
                }}
                disabled={deleteMut.isPending}
                className="inline-flex items-center gap-2 rounded-md bg-destructive px-5 py-2 text-sm font-medium text-destructive-foreground hover:bg-destructive/90 transition-colors disabled:opacity-50"
              >
                {deleteMut.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : null}
                Confirmar desconexão
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

const TABS: { key: TabKey; label: string; icon: React.ElementType }[] = [
  { key: "campanhas", label: "Campanhas", icon: Megaphone },
  { key: "contas", label: "Contas de Anúncio", icon: Target },
];

export default function Trafego() {
  const [activeTab, setActiveTab] = useState<TabKey>("campanhas");

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Target className="h-6 w-6 text-primary" />
        <div>
          <h1 className="text-2xl font-bold text-foreground">Tráfego</h1>
          <p className="text-sm text-muted-foreground">
            Campanhas Meta Ads, contas de anúncio e métricas de tráfego pago
          </p>
        </div>
      </div>

      {/* Tabs */}
      <div className="border-b border-border">
        <nav className="flex gap-0 -mb-px">
          {TABS.map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              onClick={() => setActiveTab(key)}
              className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
                activeTab === key
                  ? "border-primary text-primary"
                  : "border-transparent text-muted-foreground hover:text-foreground hover:border-border"
              }`}
            >
              <Icon className="h-4 w-4" />
              <span className="hidden sm:inline">{label}</span>
            </button>
          ))}
        </nav>
      </div>

      {/* Tab content */}
      <div>
        {activeTab === "campanhas" && <CampanhasTab />}
        {activeTab === "contas" && <ContasTab />}
      </div>
    </div>
  );
}
