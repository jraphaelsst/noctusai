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
import { useState } from "react";
import { toast } from "sonner";
import {
  CheckCircle2,
  ChevronRight,
  CircleAlert,
  Loader2,
  Plus,
  Smartphone,
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
  type CreateConnectionBody,
  type WhatsAppConnectionLine,
} from "@/hooks/useWhatsAppConnections";
import { ConnectionDetailDialog } from "@/components/ConnectionDetailDialog";

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
  // `isPending`, not `isLoading` — v5's `isLoading` goes FALSE mid-refetch
  // and would unmount this list on every background refresh (this page
  // polls connection status). → KB § PATTERNS/frontend/lying-loading-state.md
  const { data: lines, isPending } = useWhatsAppConnections();
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
      {isPending ? (
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
