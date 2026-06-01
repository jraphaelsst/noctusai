/**
 * Conexão page — a LISTING of WhatsApp (WAHA) sessions. Click a session row to
 * open a MODAL that views + edits + manages that session (status, QR pairing,
 * start / restart / unlink / webhook, edit fields, delete). "Nova conexão"
 * opens the same modal in create mode.
 *
 * One row = one connection "line" the user owns: a WAHA server URL + session +
 * API key (stored encrypted; the key is write-only). Per-user isolated. All
 * data + mutations come from the product `/api/whatsapp/connections` router via
 * the `useWhatsAppConnections` hooks; this page is presentation only.
 */
import { useState } from "react";
import { toast } from "sonner";
import {
  CheckCircle2,
  ChevronRight,
  CircleAlert,
  Link as LinkIcon,
  Loader2,
  Plus,
  Power,
  RefreshCw,
  Save,
  Smartphone,
  Trash2,
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
  type CreateConnectionBody,
  type UpdateConnectionBody,
  type WhatsAppConnectionLine,
} from "@/hooks/useWhatsAppConnections";

// Default inbound webhook (Docker-internal: WAHA → social-wiring over
// noctus-net by the compose service name `social-wiring` on its house port).
const DEFAULT_WEBHOOK_URL = "http://social-wiring:8011/api/whatsapp/webhook";

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

// ─── Shared form fields ──────────────────────────────────────────────────────
interface FormState {
  label: string;
  base_url: string;
  session_name: string;
  api_key: string;
  webhook_url: string;
}

function FormFields({
  form,
  set,
  isCreate,
  disabled,
}: {
  form: FormState;
  set: (patch: Partial<FormState>) => void;
  isCreate: boolean;
  disabled: boolean;
}) {
  return (
    <div className="grid gap-3">
      <div className="grid gap-1.5">
        <Label htmlFor="conn-label">Nome *</Label>
        <Input
          id="conn-label"
          value={form.label}
          onChange={(e) => set({ label: e.target.value })}
          placeholder="Ex: Atendimento SP"
          disabled={disabled}
        />
      </div>
      <div className="grid gap-1.5">
        <Label htmlFor="conn-apikey">
          API key {isCreate ? "*" : "(opcional — só para trocar)"}
        </Label>
        <Input
          id="conn-apikey"
          type="password"
          value={form.api_key}
          onChange={(e) => set({ api_key: e.target.value })}
          placeholder={isCreate ? "X-Api-Key da sessão WAHA" : "••••••••"}
          disabled={disabled}
          autoComplete="off"
        />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="grid gap-1.5">
          <Label htmlFor="conn-session">Sessão</Label>
          <Input
            id="conn-session"
            value={form.session_name}
            onChange={(e) => set({ session_name: e.target.value })}
            placeholder="default"
            disabled={disabled}
          />
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="conn-baseurl">Servidor WAHA</Label>
          <Input
            id="conn-baseurl"
            value={form.base_url}
            onChange={(e) => set({ base_url: e.target.value })}
            placeholder="(padrão do sistema)"
            disabled={disabled}
          />
        </div>
      </div>
      <p className="text-xs text-muted-foreground">
        Deixe o servidor em branco para usar o WAHA padrão do sistema.
      </p>
      <div className="grid gap-1.5">
        <Label htmlFor="conn-webhook">Webhook de entrada (opcional)</Label>
        <Input
          id="conn-webhook"
          value={form.webhook_url}
          onChange={(e) => set({ webhook_url: e.target.value })}
          placeholder={DEFAULT_WEBHOOK_URL}
          disabled={disabled}
        />
      </div>
    </div>
  );
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
  onSubmit: (form: FormState) => void;
  pending: boolean;
}) {
  const [form, setForm] = useState<FormState>({
    label: "",
    base_url: "",
    session_name: "default",
    api_key: "",
    webhook_url: "",
  });
  const set = (patch: Partial<FormState>) => setForm((f) => ({ ...f, ...patch }));
  const canSubmit = form.label.trim() && form.api_key.trim() && !pending;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Nova conexão</DialogTitle>
          <DialogDescription>
            Conecte uma sessão WAHA informando a API key. Abra a linha depois
            para escanear o QR.
          </DialogDescription>
        </DialogHeader>
        <FormFields form={form} set={set} isCreate disabled={pending} />
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={pending}>
            Cancelar
          </Button>
          <Button onClick={() => onSubmit(form)} disabled={!canSubmit}>
            {pending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Criar conexão
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
    <div className="flex flex-col items-center gap-2 rounded-md border bg-muted/10 p-4">
      {qr?.scannable && qr.png_base64 ? (
        <>
          <img
            src={`data:image/png;base64,${qr.png_base64}`}
            alt="QR code para parear o WhatsApp"
            className="h-52 w-52 rounded-md border bg-white p-2"
          />
          <p className="text-center text-xs text-muted-foreground">
            WhatsApp → Aparelhos conectados → Conectar aparelho. Atualiza sozinho.
          </p>
        </>
      ) : (
        <div className="flex h-52 w-52 flex-col items-center justify-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" />
          {qr?.status ? `Aguardando QR (${qr.status})` : "Gerando QR..."}
        </div>
      )}
    </div>
  );
}

// ─── Detail / edit / manage modal (per session) ──────────────────────────────
function ConnectionDetailDialog({
  line,
  onClose,
  onRequestDelete,
}: {
  line: WhatsAppConnectionLine;
  onClose: () => void;
  onRequestDelete: (line: WhatsAppConnectionLine) => void;
}) {
  const { data: status } = useWhatsAppConnectionStatus(line.id);
  const { start, restart, logout, configureWebhook } = useWhatsAppConnectionActions();
  const { update } = useWhatsAppConnectionMutations();

  const [form, setForm] = useState<FormState>({
    label: line.label,
    base_url: line.base_url,
    session_name: line.session_name,
    api_key: "",
    webhook_url: line.webhook_url ?? "",
  });
  const set = (patch: Partial<FormState>) => setForm((f) => ({ ...f, ...patch }));

  const paired = !!status?.paired;

  // `start` (and its siblings) are mutation OBJECTS (UseMutationResult), not
  // functions — the param is the mutation's own type, not its ReturnType.
  const run = (mut: typeof start, ok: string) =>
    mut.mutate(line.id, {
      onSuccess: () => toast.success(ok),
      onError: (e: any) => toast.error(e?.message ?? "Falha"),
    });

  const onSave = () => {
    const body: UpdateConnectionBody = {
      label: form.label.trim(),
      session_name: form.session_name.trim() || "default",
      base_url: form.base_url.trim() || undefined,
      webhook_url: form.webhook_url.trim() || undefined,
    };
    if (form.api_key.trim()) body.api_key = form.api_key.trim();
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

  const onWireWebhook = () =>
    configureWebhook.mutate(
      { id: line.id, url: form.webhook_url.trim() || DEFAULT_WEBHOOK_URL },
      {
        onSuccess: (r) => toast.success(`Webhook conectado (${r.events.length} eventos)`),
        onError: (e: any) => toast.error(e?.message ?? "Falha ao conectar webhook"),
      },
    );

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
                : "Não pareado"}
            </span>
          </DialogDescription>
        </DialogHeader>

        {status?.error && (
          <div className="rounded-md border border-destructive/40 bg-destructive/5 p-2 text-xs text-destructive">
            {status.error}
          </div>
        )}

        {/* QR pairing — only while unpaired */}
        {!paired && (
          <div className="space-y-2">
            <QrPanel connectionId={line.id} />
            <div className="flex justify-center">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => run(start, "Sessão iniciada — escaneie o QR")}
                disabled={start.isPending}
              >
                {start.isPending ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <RefreshCw className="mr-2 h-4 w-4" />
                )}
                Gerar nova sessão / QR
              </Button>
            </div>
          </div>
        )}

        <Separator />

        {/* Editable fields */}
        <FormFields form={form} set={set} isCreate={false} disabled={update.isPending} />

        {/* Session actions */}
        <div className="flex flex-wrap gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => run(restart, "Sessão reiniciada")}
            disabled={restart.isPending}
          >
            <RefreshCw className="mr-2 h-4 w-4" />
            Reiniciar
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={onWireWebhook}
            disabled={configureWebhook.isPending}
          >
            <LinkIcon className="mr-2 h-4 w-4" />
            Conectar webhook
          </Button>
          {paired && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => run(logout, "Conta desvinculada")}
              disabled={logout.isPending}
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
          >
            <Trash2 className="mr-2 h-4 w-4" />
            Excluir
          </Button>
          <Button onClick={onSave} disabled={update.isPending || !form.label.trim()}>
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
  const [selected, setSelected] = useState<WhatsAppConnectionLine | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<WhatsAppConnectionLine | null>(null);

  const onCreateSubmit = (form: FormState) => {
    const body: CreateConnectionBody = {
      label: form.label.trim(),
      api_key: form.api_key.trim(),
      session_name: form.session_name.trim() || "default",
    };
    if (form.base_url.trim()) body.base_url = form.base_url.trim();
    if (form.webhook_url.trim()) body.webhook_url = form.webhook_url.trim();
    create.mutate(body, {
      onSuccess: () => {
        setCreating(false);
        toast.success("Conexão criada — abra a linha para parear");
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

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <p className="text-sm text-muted-foreground">
          Clique numa sessão para ver, editar e gerenciar — API key e QR code,
          sem abrir o painel do WAHA.
        </p>
        <Button onClick={() => setCreating(true)}>
          <Plus className="mr-2 h-4 w-4" />
          Nova conexão
        </Button>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-16">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      ) : !lines || lines.length === 0 ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Nenhuma conexão ainda</CardTitle>
            <CardDescription>
              Clique em "Nova conexão", informe a API key da sua sessão WAHA;
              depois abra a linha para escanear o QR e parear um WhatsApp.
            </CardDescription>
          </CardHeader>
        </Card>
      ) : (
        <div className="space-y-2">
          {lines.map((line) => (
            <ConnectionRow key={line.id} line={line} onSelect={setSelected} />
          ))}
        </div>
      )}

      {creating && (
        <CreateConnectionDialog
          open={creating}
          onOpenChange={setCreating}
          onSubmit={onCreateSubmit}
          pending={create.isPending}
        />
      )}

      {selected && (
        <ConnectionDetailDialog
          line={selected}
          onClose={() => setSelected(null)}
          onRequestDelete={(line) => {
            setSelected(null);
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
