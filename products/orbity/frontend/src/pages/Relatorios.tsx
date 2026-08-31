/**
 * Relatorios — Reports hub page for Orbity.
 *
 * Tabs:
 *   1. Lista       — table of all reports (name, client, period, status, public link)
 *                    with full CRUD (create / edit / delete)
 *   2. Detalhes    — selected report detail: Generate snapshot button, snapshot
 *                    aggregated payload, snapshots history, shareable public link
 *
 * All four states (loading / empty / error / success) are covered in every section.
 *
 * Nav: route key "relatorios" — requires a status_pagina row with page_key = "relatorios".
 * status_pagina keys surfaced: ["relatorios"]
 */
import { useState } from "react";
import {
  FileBarChart2,
  Plus,
  Pencil,
  Trash2,
  Loader2,
  AlertCircle,
  FileText,
  X,
  Link2,
  Zap,
  CheckCircle2,
  Clock,
  ChevronLeft,
  History,
  Copy,
  Check,
} from "lucide-react";
import {
  useReports,
  useCreateReport,
  useUpdateReport,
  useDeleteReport,
  useReportSnapshots,
  useGenerateSnapshot,
  type Report,
  type ReportCreate,
  type ReportStatus,
} from "@/hooks/useRelatorios";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmtDate(dateStr: string): string {
  try {
    return new Date(dateStr + "T00:00:00").toLocaleDateString("pt-BR");
  } catch {
    return dateStr;
  }
}

function fmtDateTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString("pt-BR");
  } catch {
    return iso;
  }
}

function buildPublicUrl(publicToken: string): string {
  // Use the API public endpoint (works without auth)
  const base = window.location.origin;
  return `${base}/api/reports/public/${publicToken}`;
}

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
// Status badge
// ---------------------------------------------------------------------------

const STATUS_LABELS: Record<ReportStatus, string> = {
  draft: "Rascunho",
  published: "Publicado",
};

const STATUS_COLORS: Record<ReportStatus, string> = {
  draft: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400",
  published: "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400",
};

const STATUS_ICONS: Record<ReportStatus, React.ElementType> = {
  draft: Clock,
  published: CheckCircle2,
};

function StatusBadge({ status }: { status: ReportStatus }) {
  const Icon = STATUS_ICONS[status];
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ${STATUS_COLORS[status]}`}
    >
      <Icon className="h-3 w-3" />
      {STATUS_LABELS[status]}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Copy-to-clipboard button
// ---------------------------------------------------------------------------

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  function handleCopy() {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  return (
    <button
      onClick={handleCopy}
      className="inline-flex items-center gap-1.5 rounded-md border border-border bg-background px-2.5 py-1.5 text-xs text-muted-foreground hover:bg-muted transition-colors"
      title="Copiar link"
    >
      {copied ? (
        <>
          <Check className="h-3.5 w-3.5 text-green-600" />
          Copiado
        </>
      ) : (
        <>
          <Copy className="h-3.5 w-3.5" />
          Copiar
        </>
      )}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Report dialog (create / edit)
// ---------------------------------------------------------------------------

interface ReportDialogProps {
  open: boolean;
  editing: Report | null;
  onClose: () => void;
}

function ReportDialog({ open, editing, onClose }: ReportDialogProps) {
  const createMut = useCreateReport();
  const updateMut = useUpdateReport();

  const today = new Date().toISOString().slice(0, 10);

  const [form, setForm] = useState<ReportCreate>({
    name: editing?.name ?? "",
    period_start: editing?.period_start ?? today,
    period_end: editing?.period_end ?? today,
    client_id: editing?.client_id ?? undefined,
    status: editing?.status ?? "draft",
    expires_at: editing?.expires_at ?? undefined,
  });

  if (!open) return null;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const payload: ReportCreate = {
      ...form,
      client_id: form.client_id || undefined,
      expires_at: form.expires_at || undefined,
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
            {editing ? "Editar relatório" : "Novo relatório"}
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
            <label className="mb-1 block text-sm font-medium text-foreground">
              Nome do relatório *
            </label>
            <input
              type="text"
              required
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              placeholder="Ex: Relatório Q2 2026 – Cliente ACME"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-sm font-medium text-foreground">
                Período — início *
              </label>
              <input
                type="date"
                required
                value={form.period_start}
                onChange={(e) => setForm((f) => ({ ...f, period_start: e.target.value }))}
                className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-foreground">
                Período — fim *
              </label>
              <input
                type="date"
                required
                value={form.period_end}
                onChange={(e) => setForm((f) => ({ ...f, period_end: e.target.value }))}
                className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-sm font-medium text-foreground">Status</label>
              <select
                value={form.status}
                onChange={(e) =>
                  setForm((f) => ({ ...f, status: e.target.value as ReportStatus }))
                }
                className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <option value="draft">Rascunho</option>
                <option value="published">Publicado</option>
              </select>
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-foreground">
                Expira em
              </label>
              <input
                type="datetime-local"
                value={form.expires_at ? form.expires_at.slice(0, 16) : ""}
                onChange={(e) =>
                  setForm((f) => ({
                    ...f,
                    expires_at: e.target.value ? e.target.value + ":00Z" : undefined,
                  }))
                }
                className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </div>
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-foreground">
              ID do cliente (UUID, opcional)
            </label>
            <input
              type="text"
              value={form.client_id ?? ""}
              onChange={(e) =>
                setForm((f) => ({ ...f, client_id: e.target.value || undefined }))
              }
              className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              placeholder="Deixe em branco para sem cliente"
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
                "Criar relatório"
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Reports list tab
// ---------------------------------------------------------------------------

interface ListTabProps {
  onSelectReport: (report: Report) => void;
}

function ListTab({ onSelectReport }: ListTabProps) {
  const { data, isPending, error, refetch } = useReports();
  const deleteMut = useDeleteReport();

  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<Report | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<Report | null>(null);

  if (isPending && !data) return <LoadingState label="Carregando relatórios..." />;
  if (error) return <ErrorState message={error.message} onRetry={() => refetch()} />;

  const items = Array.isArray(data) ? data : [];

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
          Novo relatório
        </button>
      </div>

      {items.length === 0 ? (
        <EmptyState
          label="Nenhum relatório encontrado"
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
                <th className="px-4 py-3 font-medium text-muted-foreground">Nome</th>
                <th className="px-4 py-3 font-medium text-muted-foreground hidden md:table-cell">
                  Período
                </th>
                <th className="px-4 py-3 font-medium text-muted-foreground">Status</th>
                <th className="px-4 py-3 font-medium text-muted-foreground hidden lg:table-cell">
                  Link público
                </th>
                <th className="px-4 py-3 font-medium text-muted-foreground">Ações</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {items.map((report) => {
                const publicUrl = buildPublicUrl(report.public_token);
                return (
                  <tr
                    key={report.id}
                    className="bg-card hover:bg-muted/20 transition-colors cursor-pointer"
                    onClick={() => onSelectReport(report)}
                  >
                    <td className="px-4 py-3">
                      <div className="font-medium text-foreground max-w-[200px] truncate">
                        {report.name}
                      </div>
                      {report.client_id && (
                        <div className="text-xs text-muted-foreground truncate max-w-[180px]">
                          Cliente: {report.client_id}
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-3 text-foreground hidden md:table-cell whitespace-nowrap">
                      {fmtDate(report.period_start)} – {fmtDate(report.period_end)}
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={report.status as ReportStatus} />
                    </td>
                    <td className="px-4 py-3 hidden lg:table-cell">
                      {report.status === "published" ? (
                        <div className="flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
                          <Link2 className="h-3.5 w-3.5 text-muted-foreground" />
                          <span className="text-xs text-muted-foreground truncate max-w-[160px]">
                            {publicUrl}
                          </span>
                          <CopyButton text={publicUrl} />
                        </div>
                      ) : (
                        <span className="text-xs text-muted-foreground italic">
                          Publique para gerar link
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => {
                            setEditing(report);
                            setDialogOpen(true);
                          }}
                          className="rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
                          title="Editar"
                        >
                          <Pencil className="h-4 w-4" />
                        </button>
                        <button
                          onClick={() => setConfirmDelete(report)}
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

      <ReportDialog
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
            <h2 className="mb-2 text-lg font-semibold text-foreground">Remover relatório</h2>
            <p className="mb-6 text-sm text-muted-foreground">
              Tem certeza que deseja remover o relatório{" "}
              <strong className="text-foreground">{confirmDelete.name}</strong>? Esta ação não
              pode ser desfeita.
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
                  "Confirmar remoção"
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
// Snapshot payload renderer
// ---------------------------------------------------------------------------

interface SnapshotPayload {
  leads?: number | Record<string, unknown>;
  revenues?: number | Record<string, unknown>;
  expenses?: number | Record<string, unknown>;
  [key: string]: unknown;
}

function PayloadCard({ label, value }: { label: string; value: unknown }) {
  const display =
    typeof value === "number"
      ? value.toLocaleString("pt-BR", { minimumFractionDigits: 0 })
      : typeof value === "object"
      ? JSON.stringify(value, null, 2)
      : String(value ?? "—");

  return (
    <div className="rounded-lg border border-border bg-muted/30 p-4">
      <p className="text-xs font-medium text-muted-foreground mb-1">{label}</p>
      {typeof value === "object" ? (
        <pre className="text-xs text-foreground overflow-auto max-h-32 whitespace-pre-wrap">
          {display}
        </pre>
      ) : (
        <p className="text-xl font-bold text-foreground">{display}</p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Report detail tab
// ---------------------------------------------------------------------------

interface DetailTabProps {
  report: Report;
  onBack: () => void;
}

function DetailTab({ report, onBack }: DetailTabProps) {
  const { data: snapshots, isPending, error, refetch } = useReportSnapshots(report.id);
  const generateMut = useGenerateSnapshot();
  const updateMut = useUpdateReport();
  const [editDialogOpen, setEditDialogOpen] = useState(false);

  const publicUrl = buildPublicUrl(report.public_token);

  const latestSnapshot =
    Array.isArray(snapshots) && snapshots.length > 0 ? snapshots[0] : null;

  const payload = latestSnapshot?.payload as SnapshotPayload | undefined;

  return (
    <div className="space-y-6">
      {/* Back + header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex items-center gap-3">
          <button
            onClick={onBack}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-muted transition-colors"
            title="Voltar à lista"
          >
            <ChevronLeft className="h-5 w-5" />
          </button>
          <div>
            <h2 className="text-xl font-bold text-foreground">{report.name}</h2>
            <p className="text-sm text-muted-foreground">
              {fmtDate(report.period_start)} – {fmtDate(report.period_end)}
            </p>
          </div>
          <StatusBadge status={report.status as ReportStatus} />
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => setEditDialogOpen(true)}
            className="inline-flex items-center gap-2 rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground hover:bg-muted transition-colors"
          >
            <Pencil className="h-4 w-4" />
            Editar
          </button>
          <button
            onClick={() => generateMut.mutate(report.id)}
            disabled={generateMut.isPending}
            className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {generateMut.isPending ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Gerando...
              </>
            ) : (
              <>
                <Zap className="h-4 w-4" />
                Gerar snapshot
              </>
            )}
          </button>
        </div>
      </div>

      {/* Public link */}
      <div className="rounded-lg border border-border bg-card p-4">
        <div className="flex items-center gap-2 mb-2">
          <Link2 className="h-4 w-4 text-muted-foreground" />
          <span className="text-sm font-medium text-foreground">Link público</span>
        </div>
        {report.status === "published" ? (
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <code className="flex-1 rounded bg-muted px-3 py-1.5 text-xs text-foreground break-all">
              {publicUrl}
            </code>
            <CopyButton text={publicUrl} />
          </div>
        ) : (
          <div className="flex items-center gap-3">
            <p className="text-sm text-muted-foreground italic">
              Relatório em rascunho — publique para ativar o link.
            </p>
            <button
              onClick={() => updateMut.mutate({ id: report.id, status: "published" })}
              disabled={updateMut.isPending}
              className="inline-flex items-center gap-1.5 rounded-md bg-green-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-green-700 transition-colors disabled:opacity-50"
            >
              {updateMut.isPending ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <CheckCircle2 className="h-3.5 w-3.5" />
              )}
              Publicar agora
            </button>
          </div>
        )}
      </div>

      {/* Latest snapshot payload */}
      <div>
        <h3 className="text-base font-semibold text-foreground mb-3">
          Dados do último snapshot
        </h3>
        {isPending && !snapshots ? (
          <LoadingState label="Carregando snapshots..." />
        ) : error ? (
          <ErrorState message={error.message} onRetry={() => refetch()} />
        ) : !latestSnapshot ? (
          <div className="rounded-lg border border-dashed border-border p-8 text-center">
            <FileBarChart2 className="h-8 w-8 text-muted-foreground/40 mx-auto mb-2" />
            <p className="text-sm text-muted-foreground">
              Nenhum snapshot gerado ainda. Clique em "Gerar snapshot" para agregar os dados
              do período.
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            <p className="text-xs text-muted-foreground">
              Gerado em {fmtDateTime(latestSnapshot.generated_at)}
            </p>
            {payload && (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {payload.leads !== undefined && (
                  <PayloadCard label="Leads" value={payload.leads} />
                )}
                {payload.revenues !== undefined && (
                  <PayloadCard label="Receitas" value={payload.revenues} />
                )}
                {payload.expenses !== undefined && (
                  <PayloadCard label="Despesas" value={payload.expenses} />
                )}
                {Object.entries(payload)
                  .filter(([k]) => !["leads", "revenues", "expenses"].includes(k))
                  .map(([k, v]) => (
                    <PayloadCard key={k} label={k} value={v} />
                  ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Snapshots history */}
      {Array.isArray(snapshots) && snapshots.length > 1 && (
        <div>
          <div className="flex items-center gap-2 mb-3">
            <History className="h-4 w-4 text-muted-foreground" />
            <h3 className="text-base font-semibold text-foreground">Histórico de snapshots</h3>
          </div>
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-border bg-muted/50">
                <tr>
                  <th className="px-4 py-3 font-medium text-muted-foreground">ID</th>
                  <th className="px-4 py-3 font-medium text-muted-foreground">Gerado em</th>
                  <th className="px-4 py-3 font-medium text-muted-foreground hidden md:table-cell">
                    Campos
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {snapshots.map((snap, idx) => (
                  <tr key={snap.id} className="bg-card hover:bg-muted/20 transition-colors">
                    <td className="px-4 py-3 text-foreground font-mono text-xs">
                      {snap.id.slice(0, 8)}…
                      {idx === 0 && (
                        <span className="ml-2 rounded-full bg-primary/10 px-2 py-0.5 text-xs text-primary">
                          atual
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-foreground">
                      {fmtDateTime(snap.generated_at)}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground hidden md:table-cell text-xs">
                      {Object.keys(snap.payload).join(", ") || "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <ReportDialog
        open={editDialogOpen}
        editing={report}
        onClose={() => setEditDialogOpen(false)}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

type TabKey = "lista" | "detalhes";

export default function Relatorios() {
  const [activeTab, setActiveTab] = useState<TabKey>("lista");
  const [selectedReport, setSelectedReport] = useState<Report | null>(null);

  function handleSelectReport(report: Report) {
    setSelectedReport(report);
    setActiveTab("detalhes");
  }

  function handleBack() {
    setActiveTab("lista");
    setSelectedReport(null);
  }

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="flex items-center gap-3">
        <FileBarChart2 className="h-6 w-6 text-primary" />
        <div>
          <h1 className="text-2xl font-bold text-foreground">Relatórios</h1>
          <p className="text-sm text-muted-foreground">
            Crie, gere e compartilhe relatórios analíticos com seus clientes
          </p>
        </div>
      </div>

      {/* Tab bar — only show when not in detail view */}
      {activeTab === "lista" && (
        <div className="border-b border-border">
          <nav className="flex gap-0 -mb-px">
            <button
              onClick={() => setActiveTab("lista")}
              className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
                activeTab === "lista"
                  ? "border-primary text-primary"
                  : "border-transparent text-muted-foreground hover:text-foreground hover:border-border"
              }`}
            >
              <FileText className="h-4 w-4" />
              <span className="hidden sm:inline">Lista de relatórios</span>
              <span className="sm:hidden">Lista</span>
            </button>
          </nav>
        </div>
      )}

      {/* Content */}
      {activeTab === "lista" && <ListTab onSelectReport={handleSelectReport} />}
      {activeTab === "detalhes" && selectedReport && (
        <DetailTab report={selectedReport} onBack={handleBack} />
      )}
    </div>
  );
}
