/**
 * Conexão page — manage MULTIPLE WhatsApp (WAHA) connections from one place,
 * without the WAHA dashboard.
 *
 * Each row is one connection "line" the user owns: a WAHA server URL +
 * session + API key (stored encrypted; the key is write-only). Per line you
 * can scan a QR to pair, see live status, start / restart / unlink the
 * session, wire the inbound webhook, and edit or delete the line. "Nova
 * conexão" wires another session to another WhatsApp.
 *
 * All data + mutations come from the product `/api/whatsapp/connections`
 * router via the `useWhatsAppConnections` hooks; this page is presentation.
 */
import { useState } from "react";
import { toast } from "sonner";
import {
  CheckCircle2,
  CircleAlert,
  Link as LinkIcon,
  Loader2,
  Pencil,
  Plus,
  Power,
  QrCode,
  RefreshCw,
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

// Default inbound webhook (Docker-internal: waha ↔ app share the network).
const DEFAULT_WEBHOOK_URL = "http://app:8010/api/whatsapp/webhook";

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

// ─── Create / edit form ─────────────────────────────────────────────────────
interface FormState {
  label: string;
  base_url: string;
  session_name: string;
  api_key: string;
  webhook_url: string;
}

function ConnectionFormDialog({
  open,
  onOpenChange,
  mode,
  line,
  onSubmit,
  pending,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  mode: "create" | "edit";
  line?: WhatsAppConnectionLine;
  onSubmit: (form: FormState) => void;
  pending: boolean;
}) {
  const [form, setForm] = useState<FormState>(() => ({
    label: line?.label ?? "",
    base_url: line?.base_url ?? "",
    session_name: line?.session_name ?? "default",
    api_key: "",
    webhook_url: line?.webhook_url ?? "",
  }));

  const set = (patch: Partial<FormState>) => setForm((f) => ({ ...f, ...patch }));

  const isCreate = mode === "create";
  const canSubmit =
    form.label.trim().length > 0 &&
    (!isCreate || form.api_key.trim().length > 0) &&
    !pending;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{isCreate ? "Nova conexão" : "Editar conexão"}</DialogTitle>
          <DialogDescription>
            {isCreate
              ? "Conecte uma sessão WAHA informando a API key. Escaneie o QR depois de criar."
              : "Atualize os dados da linha. Deixe a API key em branco para manter a atual."}
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-3 py-2">
          <div className="grid gap-1.5">
            <Label htmlFor="conn-label">Nome *</Label>
            <Input
              id="conn-label"
              value={form.label}
              onChange={(e) => set({ label: e.target.value })}
              placeholder="Ex: Atendimento SP"
              disabled={pending}
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
              disabled={pending}
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
                disabled={pending}
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="conn-baseurl">Servidor WAHA</Label>
              <Input
                id="conn-baseurl"
                value={form.base_url}
                onChange={(e) => set({ base_url: e.target.value })}
                placeholder="(padrão do sistema)"
                disabled={pending}
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
              disabled={pending}
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={pending}>
            Cancelar
          </Button>
          <Button onClick={() => onSubmit(form)} disabled={!canSubmit}>
            {pending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {isCreate ? "Criar conexão" : "Salvar"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─── Per-line QR ─────────────────────────────────────────────────────────────
function QrPanel({ connectionId }: { connectionId: string }) {
  const { data: qr } = useWhatsAppConnectionQr(connectionId, true);
  return (
    <div className="flex flex-col items-center gap-2 rounded-md border bg-muted/10 p-4">
      {qr?.scannable && qr.png_base64 ? (
        <>
          <img
            src={`data:image/png;base64,${qr.png_base64}`}
            alt="QR code para parear o WhatsApp"
            className="h-56 w-56 rounded-md border bg-white p-2"
          />
          <p className="text-xs text-muted-foreground">
            WhatsApp → Aparelhos conectados → Conectar aparelho. Atualiza sozinho.
          </p>
        </>
      ) : (
        <div className="flex h-56 w-56 flex-col items-center justify-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" />
          {qr?.status ? `Aguardando QR (${qr.status})` : "Gerando QR..."}
        </div>
      )}
    </div>
  );
}

// ─── One connection line ─────────────────────────────────────────────────────
function ConnectionRow({ line }: { line: WhatsAppConnectionLine }) {
  const { data: status } = useWhatsAppConnectionStatus(line.id);
  const { start, restart, logout, configureWebhook } = useWhatsAppConnectionActions();
  const { update, remove } = useWhatsAppConnectionMutations();

  const [showQr, setShowQr] = useState(false);
  const [editing, setEditing] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const paired = !!status?.paired;

  const onStart = () =>
    start.mutate(line.id, {
      onSuccess: () => {
        setShowQr(true);
        toast.success("Sessão iniciada — escaneie o QR");
      },
      onError: (e: any) => toast.error(e?.message ?? "Falha ao iniciar"),
    });

  const onRestart = () =>
    restart.mutate(line.id, {
      onSuccess: () => toast.success("Sessão reiniciada"),
      onError: (e: any) => toast.error(e?.message ?? "Falha ao reiniciar"),
    });

  const onLogout = () =>
    logout.mutate(line.id, {
      onSuccess: () => toast.success("Conta desvinculada"),
      onError: (e: any) => toast.error(e?.message ?? "Falha ao desvincular"),
    });

  const onWireWebhook = () => {
    const url = line.webhook_url || DEFAULT_WEBHOOK_URL;
    configureWebhook.mutate(
      { id: line.id, url },
      {
        onSuccess: (r) => toast.success(`Webhook conectado (${r.events.length} eventos)`),
        onError: (e: any) => toast.error(e?.message ?? "Falha ao conectar webhook"),
      },
    );
  };

  const onEditSubmit = (form: FormState) => {
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
          setEditing(false);
          toast.success("Conexão atualizada");
        },
        onError: (e: any) => toast.error(e?.message ?? "Falha ao salvar"),
      },
    );
  };

  const onDelete = () =>
    remove.mutate(line.id, {
      onSuccess: () => toast.success("Conexão removida"),
      onError: (e: any) => toast.error(e?.message ?? "Falha ao remover"),
    });

  return (
    <Card>
      <CardContent className="space-y-3 p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <Smartphone className="h-4 w-4 text-muted-foreground" />
              <span className="truncate font-medium">{line.label}</span>
              <StatusBadge status={status?.status ?? null} paired={paired} />
            </div>
            <div className="mt-0.5 truncate text-xs text-muted-foreground">
              {paired ? (
                <span>
                  Conectado: <strong>{status?.me_name ?? status?.me_id ?? "—"}</strong>
                </span>
              ) : (
                <span>Não pareado</span>
              )}
              {" · "}
              <code className="font-mono">{line.session_name}</code>
              {" @ "}
              <span className="break-all">{line.base_url}</span>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-1">
            {!paired && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => setShowQr((v) => !v)}
                title="Mostrar QR"
              >
                <QrCode className="h-4 w-4" />
              </Button>
            )}
            <Button
              variant="ghost"
              size="icon"
              onClick={onRestart}
              disabled={restart.isPending}
              title="Reiniciar sessão"
            >
              {restart.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <RefreshCw className="h-4 w-4" />
              )}
            </Button>
            <Button
              variant="ghost"
              size="icon"
              onClick={onWireWebhook}
              disabled={configureWebhook.isPending}
              title="Conectar webhook"
            >
              {configureWebhook.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <LinkIcon className="h-4 w-4" />
              )}
            </Button>
            <Button variant="ghost" size="icon" onClick={() => setEditing(true)} title="Editar">
              <Pencil className="h-4 w-4" />
            </Button>
            {paired && (
              <Button
                variant="ghost"
                size="icon"
                onClick={onLogout}
                disabled={logout.isPending}
                title="Desvincular conta"
              >
                <Power className="h-4 w-4" />
              </Button>
            )}
            <Button
              variant="ghost"
              size="icon"
              className="text-destructive"
              onClick={() => setConfirmDelete(true)}
              title="Excluir conexão"
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          </div>
        </div>

        {status?.error && (
          <div className="rounded-md border border-destructive/40 bg-destructive/5 p-2 text-xs text-destructive">
            {status.error}
          </div>
        )}

        {!paired && showQr && (
          <>
            <Separator />
            <div className="flex flex-col items-center gap-2">
              <QrPanel connectionId={line.id} />
              <Button
                variant="ghost"
                size="sm"
                onClick={onStart}
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
          </>
        )}
      </CardContent>

      {editing && (
        <ConnectionFormDialog
          open={editing}
          onOpenChange={setEditing}
          mode="edit"
          line={line}
          onSubmit={onEditSubmit}
          pending={update.isPending}
        />
      )}

      <AlertDialog open={confirmDelete} onOpenChange={setConfirmDelete}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Excluir "{line.label}"?</AlertDialogTitle>
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
    </Card>
  );
}

// ─── Page ────────────────────────────────────────────────────────────────────
export default function ConexaoPage() {
  const { data: lines, isLoading } = useWhatsAppConnections();
  const { create } = useWhatsAppConnectionMutations();
  const [creating, setCreating] = useState(false);

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
        toast.success("Conexão criada — abra o QR para parear");
      },
      onError: (e: any) => toast.error(e?.message ?? "Falha ao criar conexão"),
    });
  };

  return (
    <div className="container max-w-3xl space-y-6 py-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Conexões WhatsApp</h1>
          <p className="text-sm text-muted-foreground">
            Gerencie várias sessões WAHA aqui — API key e QR code, sem abrir o
            painel do WAHA.
          </p>
        </div>
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
              Clique em "Nova conexão", informe a API key da sua sessão WAHA e
              escaneie o QR para parear um WhatsApp.
            </CardDescription>
          </CardHeader>
        </Card>
      ) : (
        <div className="space-y-3">
          {lines.map((line) => (
            <ConnectionRow key={line.id} line={line} />
          ))}
        </div>
      )}

      {creating && (
        <ConnectionFormDialog
          open={creating}
          onOpenChange={setCreating}
          mode="create"
          onSubmit={onCreateSubmit}
          pending={create.isPending}
        />
      )}
    </div>
  );
}
