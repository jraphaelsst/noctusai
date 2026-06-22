/**
 * Conexão page — a LISTING of WhatsApp (WAHA) sessions. Click a session row to
 * open a MODAL that views + manages that session (status, QR pairing,
 * start / restart / logout, label edit, delete). "Nova conexão" opens a
 * minimal create form (Nome + API key only); on success the QR dialog opens
 * automatically so the user can scan without an extra step.
 *
 * Backend derives session_name, base_url, and webhook_url — these are shown
 * as read-only info in the detail dialog, not editable by the user.
 *
 * One row = one connection "line" the user owns. Per-user isolated. All data +
 * mutations come from the product `/api/whatsapp/connections` router via the
 * `useWhatsAppConnections` hooks; this page is presentation only.
 */
import { useState, useEffect, useRef } from "react";
import { toast } from "sonner";
import {
  CheckCircle2,
  ChevronRight,
  CircleAlert,
  Clipboard,
  Eye,
  EyeOff,
  Loader2,
  Pencil,
  Plus,
  Power,
  RefreshCw,
  Save,
  Smartphone,
  Trash2,
  X,
} from "lucide-react";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";

import {
  useWhatsAppConnections,
  useWhatsAppConnectionMutations,
  useWhatsAppConnectionStatus,
  useWhatsAppConnectionQr,
  useWhatsAppConnectionActions,
  useRevealApiKey,
  type CreateConnectionBody,
  type UpdateConnectionBody,
  type WhatsAppConnectionLine,
} from "@/hooks/useWhatsAppConnections";

// ─── Status badge ───────────────────────────────────────────────────────────
function StatusBadge({ status, paired }: { status: string | null; paired: boolean }) {
  if (paired) {
    return (
      <Badge variant="default" className="gap-1">
        <CheckCircle2 className="h-3 w-3" />
        {status ?? "WORKING"}
      </Badge>
    );
  }
  return (
    <Badge variant="secondary" className="gap-1">
      <CircleAlert className="h-3 w-3" />
      {status ?? "desconectado"}
    </Badge>
  );
}

// ─── Copy-to-clipboard button ────────────────────────────────────────────────
function CopyButton({ value }: { value: string }) {
  const [copied, setCopied] = useState(false);
  const onClick = () => {
    navigator.clipboard.writeText(value).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };
  return (
    <Button
      type="button"
      variant="ghost"
      size="icon"
      className="h-7 w-7 shrink-0"
      onClick={onClick}
      aria-label="Copiar"
    >
      <Clipboard className="h-3.5 w-3.5" />
      {copied && <span className="sr-only">Copiado</span>}
    </Button>
  );
}

// ─── Create form (Nome + API key only) ───────────────────────────────────────
interface CreateFormState {
  label: string;
  api_key: string;
}

// ─── Create modal ────────────────────────────────────────────────────────────
function CreateConnectionDialog({
  open,
  onOpenChange,
  onSubmit,
  pending,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmit: (form: CreateFormState) => void;
  pending: boolean;
}) {
  const [form, setForm] = useState<CreateFormState>({ label: "", api_key: "" });
  const set = (patch: Partial<CreateFormState>) => setForm((f) => ({ ...f, ...patch }));
  const canSubmit = form.label.trim() && form.api_key.trim() && !pending;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Nova conexão WhatsApp</DialogTitle>
          <DialogDescription>
            Informe um nome e a API key. O QR code abre automaticamente para
            você parear o WhatsApp.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-3">
          <div className="grid gap-1.5">
            <Label htmlFor="conn-label">Nome *</Label>
            <Input
              id="conn-label"
              value={form.label}
              onChange={(e) => set({ label: e.target.value })}
              placeholder="Ex: Atendimento SP"
              disabled={pending}
              data-testid="create-conn-label"
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="conn-apikey">API key *</Label>
            <Input
              id="conn-apikey"
              type="password"
              value={form.api_key}
              onChange={(e) => set({ api_key: e.target.value })}
              placeholder="X-Api-Key da instância WAHA"
              disabled={pending}
              autoComplete="off"
              data-testid="create-conn-apikey"
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={pending}>
            Cancelar
          </Button>
          <Button
            onClick={() => onSubmit(form)}
            disabled={!canSubmit}
            data-testid="create-conn-submit"
          >
            {pending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Criar e conectar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─── QR panel (inside the detail modal) ──────────────────────────────────────
function QrPanel({ connectionId }: { connectionId: string }) {
  const { data: qr } = useWhatsAppConnectionQr(connectionId, true);
  return (
    <div className="flex flex-col items-center gap-2 rounded-md border bg-muted/10 p-4" data-testid="qr-panel">
      {qr?.scannable && qr.png_base64 ? (
        <>
          <img
            src={`data:image/png;base64,${qr.png_base64}`}
            alt="QR code para parear o WhatsApp"
            className="h-52 w-52 rounded-md border bg-white p-2"
            data-testid="qr-image"
          />
          <p className="text-center text-xs text-muted-foreground">
            WhatsApp → Aparelhos conectados → Conectar aparelho. Atualiza sozinho.
          </p>
        </>
      ) : (
        <div className="flex h-52 w-52 flex-col items-center justify-center gap-2 text-sm text-muted-foreground" data-testid="qr-loading">
          <Loader2 className="h-5 w-5 animate-spin" />
          {qr?.status ? `Aguardando QR (${qr.status})` : "Gerando QR..."}
        </div>
      )}
    </div>
  );
}

// ─── Read-only info row ───────────────────────────────────────────────────────
function ReadOnlyField({
  label,
  value,
  copyable,
  testId,
}: {
  label: string;
  value: string | null | undefined;
  copyable?: boolean;
  testId?: string;
}) {
  if (!value) return null;
  return (
    <div className="grid gap-1">
      <span className="text-xs font-medium text-muted-foreground">{label}</span>
      <div className="flex items-center gap-1.5 rounded-md border bg-muted/30 px-2.5 py-1.5">
        <code className="flex-1 truncate text-xs font-mono" data-testid={testId}>
          {value}
        </code>
        {copyable && <CopyButton value={value} />}
      </div>
    </div>
  );
}

// ─── Detail / manage modal (per session) ─────────────────────────────────────
function ConnectionDetailDialog({
  line,
  onClose,
  onRequestDelete,
  autoStart,
}: {
  line: WhatsAppConnectionLine;
  onClose: () => void;
  onRequestDelete: (line: WhatsAppConnectionLine) => void;
  /** When true (just-created flow) trigger start immediately on mount. */
  autoStart?: boolean;
}) {
  const { data: status } = useWhatsAppConnectionStatus(line.id);
  const { start, restart, logout } = useWhatsAppConnectionActions();
  const { update } = useWhatsAppConnectionMutations();
  const reveal = useRevealApiKey();

  // Label edit + optional api_key rotation
  const [editLabel, setEditLabel] = useState(line.label);
  const [editApiKey, setEditApiKey] = useState("");
  // API-key field UX: masked by default → eye reveals the stored key, pencil
  // switches to edit (rotate) mode. The plaintext key lives only in local
  // state while revealed; never cached.
  const [keyMode, setKeyMode] = useState<"hidden" | "revealed" | "editing">("hidden");
  const [revealedKey, setRevealedKey] = useState<string | null>(null);

  const onToggleReveal = async () => {
    if (keyMode === "revealed") {
      setKeyMode("hidden");
      return;
    }
    try {
      const res =
        revealedKey != null
          ? { api_key: revealedKey }
          : await reveal.mutateAsync(line.id);
      setRevealedKey(res.api_key);
      setKeyMode("revealed");
    } catch (e: any) {
      toast.error(e?.message ?? "Falha ao revelar a API key");
    }
  };

  const startEditingKey = () => {
    setKeyMode("editing");
    setEditApiKey("");
    setRevealedKey(null);
  };

  const cancelEditingKey = () => {
    setKeyMode("hidden");
    setEditApiKey("");
  };

  const paired = !!status?.paired;

  // Trigger restart on first render when autoStart=true and not already paired
  const [startFired, setStartFired] = useState(false);
  if (autoStart && !startFired && !restart.isPending) {
    setStartFired(true);
    restart.mutate(line.id);
  }

  // Auto-recovery: when unpaired and status flips to FAILED or STOPPED,
  // fire restart ONCE. Re-arms after a non-failed status is observed.
  const autoRecoveryFiredRef = useRef(false);
  const liveStatus = status?.status;
  useEffect(() => {
    if (paired) return;
    const isFailed = liveStatus === "FAILED" || liveStatus === "STOPPED";
    if (isFailed && !autoRecoveryFiredRef.current && !restart.isPending && !start.isPending) {
      autoRecoveryFiredRef.current = true;
      restart.mutate(line.id);
    }
    // Re-arm when a non-failed status is observed (e.g. SCAN_QR_CODE, STARTING)
    if (!isFailed && liveStatus != null) {
      autoRecoveryFiredRef.current = false;
    }
  }, [liveStatus, paired, restart.isPending, start.isPending]);

  const run = (mut: typeof start, ok: string) =>
    mut.mutate(line.id, {
      onSuccess: () => toast.success(ok),
      onError: (e: any) => toast.error(e?.message ?? "Falha"),
    });

  const onSave = () => {
    const body: UpdateConnectionBody = { label: editLabel.trim() };
    if (editApiKey.trim()) body.api_key = editApiKey.trim();
    update.mutate(
      { id: line.id, body },
      {
        onSuccess: () => {
          toast.success("Conexão atualizada");
          onClose();
        },
        onError: (e: any) => toast.error(e?.message ?? "Falha ao salvar"),
      },
    );
  };

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Smartphone className="h-5 w-5" />
            {line.label}
          </DialogTitle>
          <DialogDescription className="flex items-center gap-2">
            <StatusBadge status={status?.status ?? null} paired={paired} />
            <span className="text-xs">
              {paired
                ? `Conectado: ${status?.me_name ?? status?.me_id ?? "—"}`
                : "Não pareado — escaneie o QR abaixo"}
            </span>
          </DialogDescription>
        </DialogHeader>

        {status?.error && (
          <div className="rounded-md border border-destructive/40 bg-destructive/5 p-2 text-xs text-destructive">
            {status.error}
          </div>
        )}

        {/* ── QR pairing — while unpaired ── */}
        {!paired && (
          <div className="space-y-2">
            {(autoStart && restart.isPending) ? (
              <div className="flex h-52 items-center justify-center gap-2 rounded-md border bg-muted/10 p-4 text-sm text-muted-foreground" data-testid="qr-starting">
                <Loader2 className="h-5 w-5 animate-spin" />
                Iniciando sessão…
              </div>
            ) : (
              <QrPanel connectionId={line.id} />
            )}
            <div className="flex justify-center">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => run(restart, "Nova sessão gerada — escaneie o QR")}
                disabled={restart.isPending}
                data-testid="btn-start"
              >
                {restart.isPending ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <RefreshCw className="mr-2 h-4 w-4" />
                )}
                Gerar nova sessão / QR
              </Button>
            </div>
          </div>
        )}

        {/* ── Paired success ── */}
        {paired && (
          <div className="flex items-center gap-2 rounded-md border border-emerald-500/40 bg-emerald-50/60 px-3 py-2 text-sm text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-400" data-testid="paired-success">
            <CheckCircle2 className="h-4 w-4 shrink-0" />
            <span>
              WhatsApp pareado
              {status?.me_name || status?.me_id
                ? ` — ${status?.me_name ?? status?.me_id}`
                : ""}
            </span>
          </div>
        )}

        <Separator />

        {/* ── Read-only derived info ── */}
        <div className="grid gap-2">
          <ReadOnlyField
            label="Sessão (derivado)"
            value={line.session_name}
            testId="detail-session-name"
          />
          <ReadOnlyField
            label="Webhook de entrada"
            value={line.webhook_url}
            copyable
            testId="detail-webhook-url"
          />
        </div>

        <Separator />

        {/* ── Editable fields ── */}
        <div className="grid gap-3">
          <div className="grid gap-1.5">
            <Label htmlFor="edit-label">Nome</Label>
            <Input
              id="edit-label"
              value={editLabel}
              onChange={(e) => setEditLabel(e.target.value)}
              disabled={update.isPending}
              data-testid="edit-conn-label"
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="edit-apikey">
              API key{" "}
              <span className="text-xs font-normal text-muted-foreground">
                {keyMode === "editing" ? "(digite a nova chave)" : "(toque no lápis para trocar)"}
              </span>
            </Label>
            {keyMode === "editing" ? (
              <div className="flex items-center gap-1.5">
                <Input
                  id="edit-apikey"
                  type="text"
                  value={editApiKey}
                  onChange={(e) => setEditApiKey(e.target.value)}
                  placeholder="Nova API key (X-Api-Key da instância WAHA)"
                  disabled={update.isPending}
                  autoComplete="off"
                  autoFocus
                  className="font-mono"
                  data-testid="edit-conn-apikey"
                />
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="h-9 w-9 shrink-0"
                  onClick={cancelEditingKey}
                  disabled={update.isPending}
                  aria-label="Cancelar edição da API key"
                  data-testid="btn-apikey-cancel"
                >
                  <X className="h-4 w-4" />
                </Button>
              </div>
            ) : (
              <div className="flex items-center gap-1.5">
                <Input
                  id="edit-apikey"
                  type="text"
                  readOnly
                  value={keyMode === "revealed" ? revealedKey ?? "" : "••••••••"}
                  className="font-mono"
                  data-testid="edit-conn-apikey-display"
                />
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="h-9 w-9 shrink-0"
                  onClick={onToggleReveal}
                  disabled={reveal.isPending}
                  aria-label={keyMode === "revealed" ? "Ocultar API key" : "Mostrar API key"}
                  data-testid="btn-apikey-reveal"
                >
                  {reveal.isPending ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : keyMode === "revealed" ? (
                    <EyeOff className="h-4 w-4" />
                  ) : (
                    <Eye className="h-4 w-4" />
                  )}
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="h-9 w-9 shrink-0"
                  onClick={startEditingKey}
                  aria-label="Editar API key"
                  data-testid="btn-apikey-edit"
                >
                  <Pencil className="h-4 w-4" />
                </Button>
              </div>
            )}
          </div>
        </div>

        {/* ── Session actions ── */}
        <div className="flex flex-wrap gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => run(restart, "Sessão reiniciada")}
            disabled={restart.isPending}
            data-testid="btn-restart"
          >
            <RefreshCw className="mr-2 h-4 w-4" />
            Reiniciar
          </Button>
          {paired && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => run(logout, "Conta desvinculada")}
              disabled={logout.isPending}
              data-testid="btn-logout"
            >
              <Power className="mr-2 h-4 w-4" />
              Desvincular
            </Button>
          )}
        </div>

        <DialogFooter className="flex-row justify-between sm:justify-between">
          <Button
            variant="ghost"
            className="text-destructive"
            onClick={() => onRequestDelete(line)}
            data-testid="btn-delete"
          >
            <Trash2 className="mr-2 h-4 w-4" />
            Excluir
          </Button>
          <Button
            onClick={onSave}
            disabled={update.isPending || !editLabel.trim()}
            data-testid="btn-save"
          >
            {update.isPending ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Save className="mr-2 h-4 w-4" />
            )}
            Salvar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─── One clickable session row ───────────────────────────────────────────────
function ConnectionRow({
  line,
  onSelect,
}: {
  line: WhatsAppConnectionLine;
  onSelect: (line: WhatsAppConnectionLine) => void;
}) {
  const { data: status } = useWhatsAppConnectionStatus(line.id);
  const paired = !!status?.paired;
  return (
    <button
      type="button"
      onClick={() => onSelect(line)}
      className="flex w-full items-center gap-3 rounded-lg border bg-card p-3 text-left transition hover:bg-muted/40"
    >
      <Smartphone className="h-5 w-5 shrink-0 text-muted-foreground" />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="truncate font-medium">{line.label}</span>
          <StatusBadge status={status?.status ?? null} paired={paired} />
        </div>
        <div className="truncate text-xs text-muted-foreground">
          {paired ? (
            <span>Conectado: {status?.me_name ?? status?.me_id ?? "—"}</span>
          ) : (
            <span>Não pareado</span>
          )}
          {" · "}
          <code className="font-mono">{line.session_name}</code>
        </div>
      </div>
      <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
    </button>
  );
}

// ─── WhatsApp connections — exported so Conexoes.tsx can embed it ────────────
/**
 * WhatsAppConnections renders the full WAHA session management UI without the
 * outer page container. Import this into Conexoes.tsx to embed under a section
 * heading.
 */
export function WhatsAppConnections() {
  const { data: lines, isLoading } = useWhatsAppConnections();
  const { create, remove } = useWhatsAppConnectionMutations();
  const [creating, setCreating] = useState(false);
  // selected = a connection to view/manage (normal select)
  const [selected, setSelected] = useState<WhatsAppConnectionLine | null>(null);
  // justCreated = connection freshly created → auto-start QR in detail dialog
  const [justCreated, setJustCreated] = useState<WhatsAppConnectionLine | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<WhatsAppConnectionLine | null>(null);

  const onCreateSubmit = (form: CreateFormState) => {
    const body: CreateConnectionBody = {
      label: form.label.trim(),
      api_key: form.api_key.trim(),
    };
    create.mutate(body, {
      onSuccess: (newLine) => {
        setCreating(false);
        // Auto-open QR flow immediately
        setJustCreated(newLine);
        toast.success("Conexão criada — escaneie o QR para parear");
      },
      onError: (e: any) => toast.error(e?.message ?? "Falha ao criar conexão"),
    });
  };

  const onDelete = () => {
    if (!confirmDelete) return;
    const id = confirmDelete.id;
    remove.mutate(id, {
      onSuccess: () => toast.success("Conexão removida"),
      onError: (e: any) => toast.error(e?.message ?? "Falha ao remover"),
    });
    setConfirmDelete(null);
  };

  const closeJustCreated = () => setJustCreated(null);
  const closeSelected = () => setSelected(null);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <p className="text-sm text-muted-foreground">
          Clique numa sessão para ver e gerenciar — QR code, reiniciar ou desvincular.
        </p>
        <Button onClick={() => setCreating(true)} data-testid="btn-nova-conexao">
          <Plus className="mr-2 h-4 w-4" />
          Nova conexão
        </Button>
      </div>

      {/* ── Loading ── */}
      {isLoading ? (
        <div className="flex items-center justify-center py-16" data-testid="loading-connections">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      ) : !lines || lines.length === 0 ? (
        /* ── Empty ── */
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Nenhuma conexão ainda</CardTitle>
            <CardDescription>
              Clique em "Nova conexão", informe o nome e a API key — o QR code
              abre automaticamente para parear seu WhatsApp.
            </CardDescription>
          </CardHeader>
          <CardContent />
        </Card>
      ) : (
        /* ── List ── */
        <div className="space-y-2">
          {lines.map((line) => (
            <ConnectionRow key={line.id} line={line} onSelect={setSelected} />
          ))}
        </div>
      )}

      {/* ── Create dialog ── */}
      {creating && (
        <CreateConnectionDialog
          open={creating}
          onOpenChange={setCreating}
          onSubmit={onCreateSubmit}
          pending={create.isPending}
        />
      )}

      {/* ── Just-created QR flow ── */}
      {justCreated && (
        <ConnectionDetailDialog
          line={justCreated}
          onClose={closeJustCreated}
          onRequestDelete={(line) => {
            closeJustCreated();
            setConfirmDelete(line);
          }}
          autoStart
        />
      )}

      {/* ── Normal detail view ── */}
      {selected && !justCreated && (
        <ConnectionDetailDialog
          line={selected}
          onClose={closeSelected}
          onRequestDelete={(line) => {
            closeSelected();
            setConfirmDelete(line);
          }}
        />
      )}

      <AlertDialog open={!!confirmDelete} onOpenChange={(o) => !o && setConfirmDelete(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Excluir "{confirmDelete?.label}"?</AlertDialogTitle>
            <AlertDialogDescription>
              A linha e sua API key serão removidas. A sessão no WAHA não é
              encerrada — use "Desvincular" antes se quiser deslogar a conta.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction onClick={onDelete}>Excluir</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

// ─── Standalone page wrapper (for /conexao direct route) ──────────────────────
export default function ConexaoPage() {
  return (
    <div className="container max-w-3xl space-y-6 py-6">
      <div>
        <h1 className="text-2xl font-semibold">Conexões WhatsApp</h1>
      </div>
      <WhatsAppConnections />
    </div>
  );
}
