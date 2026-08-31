/**
 * Financeiro — Financial hub page for Orbity.
 *
 * Sections (tabs):
 *   1. Visao Geral — cash-flow summary cards for the selected month
 *   2. Contratos    — list + full CRUD
 *   3. Despesas     — list + full CRUD
 *   4. Receitas     — list + full CRUD
 *
 * Every section ships all four states: loading / empty / error / success.
 *
 * Nav: registered under route key "financeiro" — requires a status_pagina
 * row with page_key = "financeiro" (see return note).
 */
import { useState } from "react";
import { format } from "date-fns";
import {
  DollarSign,
  TrendingUp,
  TrendingDown,
  BarChart3,
  FileText,
  Receipt,
  Banknote,
  Plus,
  Pencil,
  Trash2,
  Loader2,
  AlertCircle,
  X,
  CheckCircle2,
  Clock,
  AlertTriangle,
  XCircle,
} from "lucide-react";
import {
  useCashFlow,
  useContracts,
  useCreateContract,
  useUpdateContract,
  useDeleteContract,
  useExpenses,
  useCreateExpense,
  useUpdateExpense,
  useDeleteExpense,
  useRevenues,
  useCreateRevenue,
  useUpdateRevenue,
  useDeleteRevenue,
  type Contract,
  type Expense,
  type Revenue,
  type ContractStatus,
  type ExpenseRecurrence,
  type RevenueStatus,
  type ContractCreate,
  type ExpenseCreate,
  type RevenueCreate,
} from "@/hooks/useFinancial";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmtCurrency(value: number): string {
  return value.toLocaleString("pt-BR", {
    style: "currency",
    currency: "BRL",
  });
}

function fmtDate(dateStr: string): string {
  try {
    return new Date(dateStr + "T00:00:00").toLocaleDateString("pt-BR");
  } catch {
    return dateStr;
  }
}

type TabKey = "overview" | "contracts" | "expenses" | "revenues";

// ---------------------------------------------------------------------------
// Sub-components: state renderers
// ---------------------------------------------------------------------------

function LoadingState({ label }: { label: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 gap-3">
      <Loader2 className="h-7 w-7 animate-spin text-primary" />
      <p className="text-sm text-muted-foreground">{label}</p>
    </div>
  );
}

function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 gap-3 text-destructive">
      <AlertCircle className="h-7 w-7" />
      <p className="text-sm font-medium">Erro ao carregar dados</p>
      <p className="text-xs text-muted-foreground max-w-sm text-center">{message}</p>
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
// Overview / Cash-flow tab
// ---------------------------------------------------------------------------

function OverviewTab({ month }: { month: string }) {
  // `isFetching` (not `isLoading`) drives the subtle "Atualizando" badge
  // below — placeholderData keeps the previous month's totals on screen
  // during a month change (the selector lives outside this component and
  // updates instantly), but these summary cards carry no visible date, so
  // a plain flip with zero signal would silently show the wrong month's
  // figures under the newly-selected month.
  const { data, isPending, isFetching, error, refetch } = useCashFlow(month);

  if (isPending && !data) return <LoadingState label="Carregando fluxo de caixa..." />;
  if (error) return <ErrorState message={error.message} onRetry={() => refetch()} />;
  if (!data) return <EmptyState label="Sem dados para este mes" />;

  const netPositive = data.net >= 0;

  const cards = [
    {
      label: "Receitas pagas",
      value: data.paid_revenues,
      icon: TrendingUp,
      color: "text-green-600",
      bg: "bg-green-50 dark:bg-green-950/30",
      border: "border-green-200 dark:border-green-900",
    },
    {
      label: "Despesas pagas",
      value: data.paid_expenses,
      icon: TrendingDown,
      color: "text-red-600",
      bg: "bg-red-50 dark:bg-red-950/30",
      border: "border-red-200 dark:border-red-900",
    },
    {
      label: "Resultado liquido",
      value: data.net,
      icon: BarChart3,
      color: netPositive ? "text-green-600" : "text-red-600",
      bg: netPositive
        ? "bg-green-50 dark:bg-green-950/30"
        : "bg-red-50 dark:bg-red-950/30",
      border: netPositive
        ? "border-green-200 dark:border-green-900"
        : "border-red-200 dark:border-red-900",
    },
    {
      label: "Receitas pendentes",
      value: data.pending_revenues,
      icon: Clock,
      color: "text-yellow-600",
      bg: "bg-yellow-50 dark:bg-yellow-950/30",
      border: "border-yellow-200 dark:border-yellow-900",
    },
    {
      label: "Receitas em atraso",
      value: data.overdue_revenues,
      icon: AlertTriangle,
      color: "text-orange-600",
      bg: "bg-orange-50 dark:bg-orange-950/30",
      border: "border-orange-200 dark:border-orange-900",
    },
  ];

  return (
    <div className="space-y-2">
      {isFetching && (
        <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <Loader2 className="w-3.5 h-3.5 animate-spin" /> Atualizando...
        </span>
      )}
      <div
        className={`grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-4 transition-opacity ${isFetching ? "opacity-60" : ""}`}
      >
        {cards.map((card) => {
          const Icon = card.icon;
          return (
            <div
              key={card.label}
              className={`rounded-lg border ${card.border} ${card.bg} p-5 flex flex-col gap-2`}
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-muted-foreground">{card.label}</span>
                <Icon className={`h-4 w-4 ${card.color}`} />
              </div>
              <p className={`text-xl font-bold ${card.color}`}>{fmtCurrency(card.value)}</p>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Contracts tab
// ---------------------------------------------------------------------------

const CONTRACT_STATUS_LABELS: Record<ContractStatus, string> = {
  active: "Ativo",
  paused: "Pausado",
  ended: "Encerrado",
};

const CONTRACT_STATUS_COLORS: Record<ContractStatus, string> = {
  active: "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400",
  paused: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400",
  ended: "bg-gray-100 text-gray-600 dark:bg-gray-900/30 dark:text-gray-400",
};

function ContractDialog({
  open,
  editing,
  onClose,
}: {
  open: boolean;
  editing: Contract | null;
  onClose: () => void;
}) {
  const createMut = useCreateContract();
  const updateMut = useUpdateContract();

  const [form, setForm] = useState<ContractCreate>({
    title: editing?.title ?? "",
    monthly_value: editing?.monthly_value ?? 0,
    billing_day: editing?.billing_day ?? 1,
    start_date: editing?.start_date ?? "",
    end_date: editing?.end_date ?? "",
    status: editing?.status ?? "active",
    notes: editing?.notes ?? "",
  });

  if (!open) return null;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const payload = {
      ...form,
      end_date: form.end_date || undefined,
      notes: form.notes || undefined,
    };
    if (editing) {
      await updateMut.mutateAsync({ id: editing.id, ...payload });
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
            {editing ? "Editar contrato" : "Novo contrato"}
          </h2>
          <button
            onClick={onClose}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-muted transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium text-foreground">Titulo *</label>
            <input
              type="text"
              required
              value={form.title}
              onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
              className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-sm font-medium text-foreground">Valor mensal (R$) *</label>
              <input
                type="number"
                min="0"
                step="0.01"
                required
                value={form.monthly_value}
                onChange={(e) =>
                  setForm((f) => ({ ...f, monthly_value: parseFloat(e.target.value) || 0 }))
                }
                className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-foreground">Dia de cobranca</label>
              <input
                type="number"
                min="1"
                max="31"
                value={form.billing_day}
                onChange={(e) =>
                  setForm((f) => ({ ...f, billing_day: parseInt(e.target.value) || 1 }))
                }
                className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-sm font-medium text-foreground">Inicio *</label>
              <input
                type="date"
                required
                value={form.start_date}
                onChange={(e) => setForm((f) => ({ ...f, start_date: e.target.value }))}
                className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-foreground">Termino</label>
              <input
                type="date"
                value={form.end_date ?? ""}
                onChange={(e) => setForm((f) => ({ ...f, end_date: e.target.value }))}
                className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </div>
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-foreground">Status</label>
            <select
              value={form.status}
              onChange={(e) =>
                setForm((f) => ({ ...f, status: e.target.value as ContractStatus }))
              }
              className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <option value="active">Ativo</option>
              <option value="paused">Pausado</option>
              <option value="ended">Encerrado</option>
            </select>
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-foreground">Notas</label>
            <textarea
              rows={2}
              value={form.notes ?? ""}
              onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
              className="flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring resize-none"
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
                "Salvar alteracoes"
              ) : (
                "Criar contrato"
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function ContractsTab() {
  const { data, isPending, error, refetch } = useContracts();
  const deleteMut = useDeleteContract();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<Contract | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<Contract | null>(null);

  if (isPending && !data) return <LoadingState label="Carregando contratos..." />;
  if (error) return <ErrorState message={error.message} onRetry={() => refetch()} />;

  const items = data?.items ?? [];

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <button
          onClick={() => { setEditing(null); setDialogOpen(true); }}
          className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
        >
          <Plus className="h-4 w-4" />
          Novo contrato
        </button>
      </div>

      {items.length === 0 ? (
        <EmptyState
          label="Nenhum contrato encontrado"
          onAdd={() => { setEditing(null); setDialogOpen(true); }}
        />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-border bg-muted/50">
              <tr>
                <th className="px-4 py-3 font-medium text-muted-foreground">Titulo</th>
                <th className="px-4 py-3 font-medium text-muted-foreground hidden sm:table-cell">Valor/mes</th>
                <th className="px-4 py-3 font-medium text-muted-foreground hidden md:table-cell">Inicio</th>
                <th className="px-4 py-3 font-medium text-muted-foreground">Status</th>
                <th className="px-4 py-3 font-medium text-muted-foreground">Acoes</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {items.map((contract) => (
                <tr key={contract.id} className="bg-card hover:bg-muted/20 transition-colors">
                  <td className="px-4 py-3 font-medium text-foreground">
                    <div className="max-w-[240px] truncate">{contract.title}</div>
                    {contract.notes && (
                      <div className="text-xs text-muted-foreground truncate max-w-[200px]">{contract.notes}</div>
                    )}
                  </td>
                  <td className="px-4 py-3 text-foreground hidden sm:table-cell">
                    {fmtCurrency(contract.monthly_value)}
                  </td>
                  <td className="px-4 py-3 text-foreground hidden md:table-cell">
                    {fmtDate(contract.start_date)}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${CONTRACT_STATUS_COLORS[contract.status]}`}
                    >
                      {CONTRACT_STATUS_LABELS[contract.status]}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => { setEditing(contract); setDialogOpen(true); }}
                        className="rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
                        title="Editar"
                      >
                        <Pencil className="h-4 w-4" />
                      </button>
                      <button
                        onClick={() => setConfirmDelete(contract)}
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

      <ContractDialog
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
            <h2 className="mb-2 text-lg font-semibold text-foreground">Remover contrato</h2>
            <p className="mb-6 text-sm text-muted-foreground">
              Tem certeza que deseja remover o contrato{" "}
              <strong className="text-foreground">{confirmDelete.title}</strong>? Esta acao nao pode ser desfeita.
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
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Removendo...
                  </>
                ) : (
                  "Confirmar remocao"
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Expenses tab
// ---------------------------------------------------------------------------

const RECURRENCE_LABELS: Record<ExpenseRecurrence, string> = {
  none: "Unica",
  monthly: "Mensal",
  installment: "Parcelada",
};

function ExpenseDialog({
  open,
  editing,
  onClose,
}: {
  open: boolean;
  editing: Expense | null;
  onClose: () => void;
}) {
  const createMut = useCreateExpense();
  const updateMut = useUpdateExpense();

  const [form, setForm] = useState<ExpenseCreate>({
    description: editing?.description ?? "",
    amount: editing?.amount ?? 0,
    due_date: editing?.due_date ?? "",
    category: editing?.category ?? "other",
    paid: editing?.paid ?? false,
    recurrence: editing?.recurrence ?? "none",
    installments_total: editing?.installments_total ?? undefined,
    installment_n: editing?.installment_n ?? undefined,
  });

  if (!open) return null;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const payload = {
      ...form,
      installments_total: form.installments_total || undefined,
      installment_n: form.installment_n || undefined,
    };
    if (editing) {
      await updateMut.mutateAsync({ id: editing.id, ...payload });
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
            {editing ? "Editar despesa" : "Nova despesa"}
          </h2>
          <button
            onClick={onClose}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-muted transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium text-foreground">Descricao *</label>
            <input
              type="text"
              required
              value={form.description}
              onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
              className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-sm font-medium text-foreground">Valor (R$) *</label>
              <input
                type="number"
                min="0.01"
                step="0.01"
                required
                value={form.amount}
                onChange={(e) =>
                  setForm((f) => ({ ...f, amount: parseFloat(e.target.value) || 0 }))
                }
                className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-foreground">Vencimento *</label>
              <input
                type="date"
                required
                value={form.due_date}
                onChange={(e) => setForm((f) => ({ ...f, due_date: e.target.value }))}
                className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-sm font-medium text-foreground">Categoria</label>
              <input
                type="text"
                value={form.category ?? ""}
                onChange={(e) => setForm((f) => ({ ...f, category: e.target.value }))}
                className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                placeholder="other"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-foreground">Recorrencia</label>
              <select
                value={form.recurrence}
                onChange={(e) =>
                  setForm((f) => ({ ...f, recurrence: e.target.value as ExpenseRecurrence }))
                }
                className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <option value="none">Unica</option>
                <option value="monthly">Mensal</option>
                <option value="installment">Parcelada</option>
              </select>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="paid"
              checked={form.paid}
              onChange={(e) => setForm((f) => ({ ...f, paid: e.target.checked }))}
              className="h-4 w-4 rounded border-input accent-primary"
            />
            <label htmlFor="paid" className="text-sm font-medium text-foreground">
              Paga
            </label>
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
                "Salvar alteracoes"
              ) : (
                "Criar despesa"
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function ExpensesTab() {
  const { data, isPending, error, refetch } = useExpenses();
  const deleteMut = useDeleteExpense();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<Expense | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<Expense | null>(null);

  if (isPending && !data) return <LoadingState label="Carregando despesas..." />;
  if (error) return <ErrorState message={error.message} onRetry={() => refetch()} />;

  const items = data?.items ?? [];

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <button
          onClick={() => { setEditing(null); setDialogOpen(true); }}
          className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
        >
          <Plus className="h-4 w-4" />
          Nova despesa
        </button>
      </div>

      {items.length === 0 ? (
        <EmptyState
          label="Nenhuma despesa encontrada"
          onAdd={() => { setEditing(null); setDialogOpen(true); }}
        />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-border bg-muted/50">
              <tr>
                <th className="px-4 py-3 font-medium text-muted-foreground">Descricao</th>
                <th className="px-4 py-3 font-medium text-muted-foreground hidden sm:table-cell">Valor</th>
                <th className="px-4 py-3 font-medium text-muted-foreground hidden md:table-cell">Vencimento</th>
                <th className="px-4 py-3 font-medium text-muted-foreground">Status</th>
                <th className="px-4 py-3 font-medium text-muted-foreground hidden lg:table-cell">Recorrencia</th>
                <th className="px-4 py-3 font-medium text-muted-foreground">Acoes</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {items.map((expense) => (
                <tr key={expense.id} className="bg-card hover:bg-muted/20 transition-colors">
                  <td className="px-4 py-3 font-medium text-foreground">
                    <div className="max-w-[200px] truncate">{expense.description}</div>
                    <div className="text-xs text-muted-foreground">{expense.category}</div>
                  </td>
                  <td className="px-4 py-3 text-foreground hidden sm:table-cell">
                    {fmtCurrency(expense.amount)}
                  </td>
                  <td className="px-4 py-3 text-foreground hidden md:table-cell">
                    {fmtDate(expense.due_date)}
                  </td>
                  <td className="px-4 py-3">
                    {expense.paid ? (
                      <span className="inline-flex items-center gap-1 rounded-full bg-green-100 px-2.5 py-0.5 text-xs font-medium text-green-800 dark:bg-green-900/30 dark:text-green-400">
                        <CheckCircle2 className="h-3 w-3" />
                        Paga
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 rounded-full bg-yellow-100 px-2.5 py-0.5 text-xs font-medium text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400">
                        <Clock className="h-3 w-3" />
                        Pendente
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-foreground hidden lg:table-cell">
                    {RECURRENCE_LABELS[expense.recurrence]}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => { setEditing(expense); setDialogOpen(true); }}
                        className="rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
                        title="Editar"
                      >
                        <Pencil className="h-4 w-4" />
                      </button>
                      <button
                        onClick={() => setConfirmDelete(expense)}
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

      <ExpenseDialog
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
            <h2 className="mb-2 text-lg font-semibold text-foreground">Remover despesa</h2>
            <p className="mb-6 text-sm text-muted-foreground">
              Tem certeza que deseja remover a despesa{" "}
              <strong className="text-foreground">{confirmDelete.description}</strong>?
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
                {deleteMut.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                Confirmar remocao
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Revenues tab
// ---------------------------------------------------------------------------

const REVENUE_STATUS_LABELS: Record<RevenueStatus, string> = {
  pending: "Pendente",
  paid: "Paga",
  overdue: "Atrasada",
  canceled: "Cancelada",
};

const REVENUE_STATUS_COLORS: Record<RevenueStatus, string> = {
  pending: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400",
  paid: "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400",
  overdue: "bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400",
  canceled: "bg-gray-100 text-gray-600 dark:bg-gray-900/30 dark:text-gray-400",
};

const REVENUE_STATUS_ICONS: Record<RevenueStatus, React.ElementType> = {
  pending: Clock,
  paid: CheckCircle2,
  overdue: AlertTriangle,
  canceled: XCircle,
};

function RevenueDialog({
  open,
  editing,
  onClose,
}: {
  open: boolean;
  editing: Revenue | null;
  onClose: () => void;
}) {
  const createMut = useCreateRevenue();
  const updateMut = useUpdateRevenue();

  const currentMonth = format(new Date(), "yyyy-MM-01");

  const [form, setForm] = useState<RevenueCreate>({
    reference_month: editing?.reference_month ?? currentMonth,
    amount: editing?.amount ?? 0,
    due_date: editing?.due_date ?? "",
    status: editing?.status ?? "pending",
    client_id: editing?.client_id ?? undefined,
    contract_id: editing?.contract_id ?? undefined,
    paid_at: editing?.paid_at ?? undefined,
  });

  if (!open) return null;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const payload = {
      ...form,
      client_id: form.client_id || undefined,
      contract_id: form.contract_id || undefined,
      paid_at: form.paid_at || undefined,
    };
    if (editing) {
      await updateMut.mutateAsync({ id: editing.id, ...payload });
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
            {editing ? "Editar receita" : "Nova receita"}
          </h2>
          <button
            onClick={onClose}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-muted transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-sm font-medium text-foreground">Valor (R$) *</label>
              <input
                type="number"
                min="0.01"
                step="0.01"
                required
                value={form.amount}
                onChange={(e) =>
                  setForm((f) => ({ ...f, amount: parseFloat(e.target.value) || 0 }))
                }
                className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-foreground">Vencimento *</label>
              <input
                type="date"
                required
                value={form.due_date}
                onChange={(e) => setForm((f) => ({ ...f, due_date: e.target.value }))}
                className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-sm font-medium text-foreground">Mes referencia *</label>
              <input
                type="date"
                required
                value={form.reference_month}
                onChange={(e) => setForm((f) => ({ ...f, reference_month: e.target.value }))}
                className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-foreground">Status</label>
              <select
                value={form.status}
                onChange={(e) =>
                  setForm((f) => ({ ...f, status: e.target.value as RevenueStatus }))
                }
                className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <option value="pending">Pendente</option>
                <option value="paid">Paga</option>
                <option value="overdue">Atrasada</option>
                <option value="canceled">Cancelada</option>
              </select>
            </div>
          </div>
          {form.status === "paid" && (
            <div>
              <label className="mb-1 block text-sm font-medium text-foreground">Data de pagamento</label>
              <input
                type="date"
                value={form.paid_at ?? ""}
                onChange={(e) => setForm((f) => ({ ...f, paid_at: e.target.value }))}
                className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </div>
          )}
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
                "Salvar alteracoes"
              ) : (
                "Criar receita"
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function RevenuesTab() {
  const { data, isPending, error, refetch } = useRevenues();
  const deleteMut = useDeleteRevenue();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<Revenue | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<Revenue | null>(null);

  if (isPending && !data) return <LoadingState label="Carregando receitas..." />;
  if (error) return <ErrorState message={error.message} onRetry={() => refetch()} />;

  const items = data?.items ?? [];

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <button
          onClick={() => { setEditing(null); setDialogOpen(true); }}
          className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
        >
          <Plus className="h-4 w-4" />
          Nova receita
        </button>
      </div>

      {items.length === 0 ? (
        <EmptyState
          label="Nenhuma receita encontrada"
          onAdd={() => { setEditing(null); setDialogOpen(true); }}
        />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-border bg-muted/50">
              <tr>
                <th className="px-4 py-3 font-medium text-muted-foreground">Mes ref.</th>
                <th className="px-4 py-3 font-medium text-muted-foreground hidden sm:table-cell">Valor</th>
                <th className="px-4 py-3 font-medium text-muted-foreground hidden md:table-cell">Vencimento</th>
                <th className="px-4 py-3 font-medium text-muted-foreground">Status</th>
                <th className="px-4 py-3 font-medium text-muted-foreground">Acoes</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {items.map((revenue) => {
                const StatusIcon = REVENUE_STATUS_ICONS[revenue.status];
                return (
                  <tr key={revenue.id} className="bg-card hover:bg-muted/20 transition-colors">
                    <td className="px-4 py-3 font-medium text-foreground">
                      {fmtDate(revenue.reference_month)}
                    </td>
                    <td className="px-4 py-3 text-foreground hidden sm:table-cell">
                      {fmtCurrency(revenue.amount)}
                    </td>
                    <td className="px-4 py-3 text-foreground hidden md:table-cell">
                      {fmtDate(revenue.due_date)}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ${REVENUE_STATUS_COLORS[revenue.status]}`}
                      >
                        <StatusIcon className="h-3 w-3" />
                        {REVENUE_STATUS_LABELS[revenue.status]}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => { setEditing(revenue); setDialogOpen(true); }}
                          className="rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
                          title="Editar"
                        >
                          <Pencil className="h-4 w-4" />
                        </button>
                        <button
                          onClick={() => setConfirmDelete(revenue)}
                          className="rounded-md p-1.5 text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition-colors"
                          title="Remover"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <RevenueDialog
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
            <h2 className="mb-2 text-lg font-semibold text-foreground">Remover receita</h2>
            <p className="mb-6 text-sm text-muted-foreground">
              Tem certeza que deseja remover esta receita? Esta acao nao pode ser desfeita.
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
                {deleteMut.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                Confirmar remocao
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
  { key: "overview", label: "Visao Geral", icon: BarChart3 },
  { key: "contracts", label: "Contratos", icon: FileText },
  { key: "expenses", label: "Despesas", icon: Receipt },
  { key: "revenues", label: "Receitas", icon: Banknote },
];

export default function Financeiro() {
  const [activeTab, setActiveTab] = useState<TabKey>("overview");
  const [selectedMonth, setSelectedMonth] = useState<string>(
    format(new Date(), "yyyy-MM"),
  );

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <DollarSign className="h-6 w-6 text-primary" />
          <div>
            <h1 className="text-2xl font-bold text-foreground">Financeiro</h1>
            <p className="text-sm text-muted-foreground">
              Contratos, despesas, receitas e fluxo de caixa
            </p>
          </div>
        </div>
        {activeTab === "overview" && (
          <div className="flex items-center gap-2">
            <label className="text-sm font-medium text-muted-foreground">Mes</label>
            <input
              type="month"
              value={selectedMonth}
              onChange={(e) => setSelectedMonth(e.target.value)}
              className="flex h-9 rounded-md border border-input bg-background px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
          </div>
        )}
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
        {activeTab === "overview" && <OverviewTab month={selectedMonth} />}
        {activeTab === "contracts" && <ContractsTab />}
        {activeTab === "expenses" && <ExpensesTab />}
        {activeTab === "revenues" && <RevenuesTab />}
      </div>
    </div>
  );
}
