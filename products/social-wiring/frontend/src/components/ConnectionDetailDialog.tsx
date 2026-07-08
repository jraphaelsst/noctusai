/**
 * ConnectionDetailDialog — per-WAHA-connection manage modal.
 *
 * Extracted from @/pages/Conexao to be shared by:
 *   - ClienteModal (Contas tab → WhatsApp section)
 *   - Conexoes page (WhatsApp card section)
 *
 * Shows QR pairing, session actions, auto-reply toggle, authorized numbers,
 * and bound-chat selection for one WhatsApp connection line.
 */
import { useState, useEffect, useRef, useCallback } from "react";
import { toast } from "sonner";
import {
  Bot,
  CheckCircle2,
  CircleAlert,
  Clipboard,
  Eye,
  EyeOff,
  Hash,
  Loader2,
  MessageSquare,
  Pencil,
  Plus,
  Power,
  RefreshCw,
  Save,
  Smartphone,
  Trash2,
  X,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";

import {
  useWhatsAppConnectionMutations,
  useWhatsAppConnectionStatus,
  useWhatsAppConnectionQr,
  useWhatsAppConnectionActions,
  useRevealApiKey,
  useConnectionChats,
  useToggleAutoReply,
  type UpdateConnectionBody,
  type WhatsAppConnectionLine,
} from "@/hooks/useWhatsAppConnections";

// ─── Status badge ──────────────────────────────────────────────────────────────
function StatusBadge({
  status,
  paired,
}: {
  status: string | null;
  paired: boolean;
}) {
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

// ─── Copy-to-clipboard button ──────────────────────────────────────────────────
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

// ─── QR panel ─────────────────────────────────────────────────────────────────
function QrPanel({ connectionId }: { connectionId: string }) {
  const { data: qr } = useWhatsAppConnectionQr(connectionId, true);
  return (
    <div
      className="flex flex-col items-center gap-2 rounded-md border bg-muted/10 p-4"
      data-testid="qr-panel"
    >
      {qr?.scannable && qr.png_base64 ? (
        <>
          <img
            src={`data:image/png;base64,${qr.png_base64}`}
            alt="QR code para parear o WhatsApp"
            className="h-52 w-52 rounded-md border bg-white p-2"
            data-testid="qr-image"
          />
          <p className="text-center text-xs text-muted-foreground">
            WhatsApp → Aparelhos conectados → Conectar aparelho. Atualiza
            sozinho.
          </p>
        </>
      ) : (
        <div
          className="flex h-52 w-52 flex-col items-center justify-center gap-2 text-sm text-muted-foreground"
          data-testid="qr-loading"
        >
          <Loader2 className="h-5 w-5 animate-spin" />
          {qr?.status ? `Aguardando QR (${qr.status})` : "Gerando QR..."}
        </div>
      )}
    </div>
  );
}

// ─── Read-only info row ────────────────────────────────────────────────────────
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
      <div className="flex min-w-0 items-center gap-1.5 rounded-md border bg-muted/30 px-2.5 py-1.5">
        <code
          className="min-w-0 flex-1 break-all text-xs font-mono"
          data-testid={testId}
        >
          {value}
        </code>
        {copyable && <CopyButton value={value} />}
      </div>
    </div>
  );
}

// ─── Authorized-numbers chip editor ───────────────────────────────────────────
function AuthorizedNumbersEditor({
  lineId,
  initialNumbers,
}: {
  lineId: string;
  initialNumbers: string[];
}) {
  const [numbers, setNumbers] = useState<string[]>(initialNumbers);
  const [newNum, setNewNum] = useState("");
  const [saving, setSaving] = useState(false);
  const { update } = useWhatsAppConnectionMutations();

  const addNumber = useCallback(() => {
    const n = newNum.trim();
    if (!n || numbers.includes(n)) return;
    setNumbers((prev) => [...prev, n]);
    setNewNum("");
  }, [newNum, numbers]);

  const removeNumber = (n: string) =>
    setNumbers((prev) => prev.filter((x) => x !== n));

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      e.preventDefault();
      addNumber();
    }
  };

  const save = async () => {
    setSaving(true);
    try {
      await update.mutateAsync({
        id: lineId,
        body: { authorized_numbers: numbers },
      });
      toast.success("Números autorizados salvos");
    } catch (e: any) {
      toast.error(e?.message ?? "Falha ao salvar números");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-2" data-testid="authorized-numbers-editor">
      <div className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
        <Hash className="h-3.5 w-3.5" />
        Números autorizados
      </div>

      {numbers.length > 0 ? (
        <div className="flex flex-wrap gap-1.5">
          {numbers.map((n) => (
            <span
              key={n}
              className="inline-flex items-center gap-1 rounded-full border bg-muted px-2.5 py-0.5 text-xs font-mono"
              data-testid="number-chip"
            >
              {n}
              <button
                type="button"
                onClick={() => removeNumber(n)}
                className="ml-0.5 rounded-full hover:text-destructive"
                aria-label={`Remover ${n}`}
              >
                <X className="h-3 w-3" />
              </button>
            </span>
          ))}
        </div>
      ) : (
        <p
          className="text-xs text-muted-foreground italic"
          data-testid="numbers-empty-hint"
        >
          Vazio = todos os números são permitidos.
        </p>
      )}

      <div className="flex gap-2">
        <Input
          value={newNum}
          onChange={(e) => setNewNum(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="+55119XXXXXXXX"
          className="h-8 font-mono text-xs"
          disabled={saving}
          data-testid="number-input"
        />
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={addNumber}
          disabled={!newNum.trim() || saving}
          className="h-8"
          data-testid="btn-add-number"
        >
          <Plus className="h-3.5 w-3.5" />
        </Button>
      </div>

      <Button
        size="sm"
        variant="outline"
        onClick={save}
        disabled={saving}
        className="h-8"
        data-testid="btn-save-numbers"
      >
        {saving ? (
          <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
        ) : (
          <Save className="mr-1.5 h-3.5 w-3.5" />
        )}
        Salvar números
      </Button>
    </div>
  );
}

// ─── Bound-chats picker ────────────────────────────────────────────────────────
function BoundChatsEditor({
  lineId,
  initialChats,
}: {
  lineId: string;
  initialChats: { chat_id: string; label: string }[];
}) {
  const [chats, setChats] = useState(initialChats);
  const [selectedDropdown, setSelectedDropdown] = useState("");
  const [manualId, setManualId] = useState("");
  const [saving, setSaving] = useState(false);
  const { update } = useWhatsAppConnectionMutations();

  const {
    data: availableChats,
    isLoading: chatsLoading,
    isError: chatsError,
  } = useConnectionChats(lineId);

  const addFromDropdown = useCallback(() => {
    if (!selectedDropdown || !availableChats) return;
    const found = availableChats.find((c) => c.chat_id === selectedDropdown);
    if (!found) return;
    if (chats.some((c) => c.chat_id === selectedDropdown)) return;
    setChats((prev) => [
      ...prev,
      { chat_id: found.chat_id, label: found.contact },
    ]);
    setSelectedDropdown("");
  }, [selectedDropdown, availableChats, chats]);

  const addManually = useCallback(() => {
    const id = manualId.trim();
    if (!id || chats.some((c) => c.chat_id === id)) return;
    setChats((prev) => [...prev, { chat_id: id, label: id }]);
    setManualId("");
  }, [manualId, chats]);

  const removeChat = (chatId: string) =>
    setChats((prev) => prev.filter((c) => c.chat_id !== chatId));

  const onManualKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      e.preventDefault();
      addManually();
    }
  };

  const save = async () => {
    setSaving(true);
    try {
      await update.mutateAsync({ id: lineId, body: { bound_chats: chats } });
      toast.success("Chats vinculados salvos");
    } catch (e: any) {
      toast.error(e?.message ?? "Falha ao salvar chats");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-2" data-testid="bound-chats-editor">
      <div className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
        <MessageSquare className="h-3.5 w-3.5" />
        Chats vinculados
      </div>

      {chats.length > 0 ? (
        <div className="flex flex-wrap gap-1.5">
          {chats.map((c) => (
            <span
              key={c.chat_id}
              className="inline-flex items-center gap-1 rounded-full border bg-muted px-2.5 py-0.5 text-xs"
              data-testid="chat-chip"
            >
              <span className="max-w-[140px] truncate">{c.label}</span>
              <button
                type="button"
                onClick={() => removeChat(c.chat_id)}
                className="ml-0.5 rounded-full hover:text-destructive"
                aria-label={`Remover chat ${c.label}`}
              >
                <X className="h-3 w-3" />
              </button>
            </span>
          ))}
        </div>
      ) : (
        <p
          className="text-xs text-muted-foreground italic"
          data-testid="chats-empty-hint"
        >
          Vazio = todos os chats são escutados.
        </p>
      )}

      <div className="flex gap-2">
        {chatsLoading ? (
          <div className="flex h-9 flex-1 items-center gap-2 rounded-md border px-3 text-xs text-muted-foreground">
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            Carregando chats…
          </div>
        ) : chatsError ? (
          <div className="flex h-9 flex-1 items-center rounded-md border border-destructive/30 px-3 text-xs text-destructive">
            Erro ao carregar chats.
          </div>
        ) : availableChats && availableChats.length > 0 ? (
          <>
            <Select
              value={selectedDropdown}
              onValueChange={setSelectedDropdown}
              disabled={saving}
            >
              <SelectTrigger
                className="h-9 flex-1 text-xs"
                data-testid="chat-dropdown"
              >
                <SelectValue placeholder="Selecionar chat da lista…" />
              </SelectTrigger>
              <SelectContent>
                {availableChats
                  .filter((c) => !chats.some((s) => s.chat_id === c.chat_id))
                  .map((c) => (
                    <SelectItem
                      key={c.chat_id}
                      value={c.chat_id}
                      className="text-xs"
                    >
                      {c.contact}
                    </SelectItem>
                  ))}
              </SelectContent>
            </Select>
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={addFromDropdown}
              disabled={!selectedDropdown || saving}
              className="h-9"
              data-testid="btn-add-chat-dropdown"
            >
              <Plus className="h-3.5 w-3.5" />
            </Button>
          </>
        ) : (
          <p className="h-9 flex-1 content-center text-xs text-muted-foreground">
            Nenhum chat disponível — use entrada manual abaixo.
          </p>
        )}
      </div>

      <div className="flex gap-2">
        <Input
          value={manualId}
          onChange={(e) => setManualId(e.target.value)}
          onKeyDown={onManualKeyDown}
          placeholder="JID manual (ex: 5511912345678@s.whatsapp.net)"
          className="h-8 font-mono text-xs"
          disabled={saving}
          data-testid="manual-chat-input"
        />
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={addManually}
          disabled={!manualId.trim() || saving}
          className="h-8"
          data-testid="btn-add-chat-manual"
        >
          <Plus className="h-3.5 w-3.5" />
        </Button>
      </div>

      <Button
        size="sm"
        variant="outline"
        onClick={save}
        disabled={saving}
        className="h-8"
        data-testid="btn-save-chats"
      >
        {saving ? (
          <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
        ) : (
          <Save className="mr-1.5 h-3.5 w-3.5" />
        )}
        Salvar chats
      </Button>
    </div>
  );
}

// ─── ConnectionSettingsPanel (exported — shared body: dialog + inline subtab) ─
/**
 * ConnectionSettingsPanel — the actual WhatsApp connection management UI
 * (status, QR pairing, session actions, auto-reply, editable fields,
 * authorized numbers, bound chats). Extracted from the pre-Wave-5
 * `ConnectionDetailDialog` body so the SAME markup + hooks render in two
 * contexts without duplicating any WAHA logic:
 *   - inside a modal — `ConnectionDetailDialog` below (ClienteModal / Conexoes)
 *   - inline as a page subtab — `pages/WhatsAppChat.tsx` "Configurações"
 *
 * Uses plain heading markup (`<h2>`/`<p>`), not `DialogTitle`/`DialogDescription`
 * — those Radix primitives read from Dialog's React context and throw when
 * rendered outside a `<Dialog>` root, which the inline subtab case requires.
 * `DialogHeader`/`DialogFooter` (plain styled `<div>`s, no Radix context) stay
 * safe to reuse in both places.
 */
export function ConnectionSettingsPanel({
  line,
  onRequestDelete,
  onSaved,
  autoStart,
}: {
  line: WhatsAppConnectionLine;
  onRequestDelete: (line: WhatsAppConnectionLine) => void;
  /** Called after a successful Save — the Dialog wrapper passes its `onClose`
   *  here to preserve the modal-closes-on-save behaviour; the inline subtab
   *  passes nothing (just the success toast, panel stays open). */
  onSaved?: () => void;
  /** When true (just-created flow) trigger start immediately on mount. */
  autoStart?: boolean;
}) {
  const { data: status } = useWhatsAppConnectionStatus(line.id);
  const { start, restart, logout } = useWhatsAppConnectionActions();
  const { update } = useWhatsAppConnectionMutations();
  const reveal = useRevealApiKey();
  const toggleAutoReply = useToggleAutoReply();

  const [editLabel, setEditLabel] = useState(line.label);
  const [editApiKey, setEditApiKey] = useState("");
  const [keyMode, setKeyMode] = useState<"hidden" | "revealed" | "editing">(
    "hidden",
  );
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

  const [startFired, setStartFired] = useState(false);
  if (autoStart && !startFired && !restart.isPending) {
    setStartFired(true);
    restart.mutate(line.id);
  }

  const autoRecoveryFiredRef = useRef(false);
  const liveStatus = status?.status;
  useEffect(() => {
    if (paired) return;
    const isFailed =
      liveStatus === "FAILED" || liveStatus === "STOPPED";
    if (
      isFailed &&
      !autoRecoveryFiredRef.current &&
      !restart.isPending &&
      !start.isPending
    ) {
      autoRecoveryFiredRef.current = true;
      restart.mutate(line.id);
    }
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
          onSaved?.();
        },
        onError: (e: any) => toast.error(e?.message ?? "Falha ao salvar"),
      },
    );
  };

  return (
    <>
      <DialogHeader>
        <h2 className="flex items-center gap-2 text-lg font-semibold leading-none tracking-tight">
          <Smartphone className="h-5 w-5" />
          {line.label}
        </h2>
        <p className="flex items-center gap-2 text-sm text-muted-foreground">
          <StatusBadge status={status?.status ?? null} paired={paired} />
          <span className="text-xs">
            {paired
              ? `Conectado: ${status?.me_name ?? status?.me_id ?? "—"}`
              : "Não pareado — escaneie o QR abaixo"}
          </span>
        </p>
      </DialogHeader>

      {status?.error && (
        <div className="rounded-md border border-destructive/40 bg-destructive/5 p-2 text-xs text-destructive">
          {status.error}
        </div>
      )}

      {/* QR pairing — while unpaired */}
      {!paired && (
        <div className="space-y-2 px-6 pt-5">
          {autoStart && restart.isPending ? (
            <div
              className="flex h-52 items-center justify-center gap-2 rounded-md border bg-muted/10 p-4 text-sm text-muted-foreground"
              data-testid="qr-starting"
            >
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

      {/* Paired success */}
      {paired && (
        <div
          className="mx-6 mt-5 flex items-center gap-2 rounded-md border border-emerald-500/40 bg-emerald-50/60 px-3 py-2 text-sm text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-400"
          data-testid="paired-success"
        >
          <CheckCircle2 className="h-4 w-4 shrink-0" />
          <span>
            WhatsApp pareado
            {status?.me_name || status?.me_id
              ? ` — ${status?.me_name ?? status?.me_id}`
              : ""}
          </span>
        </div>
      )}

      <div className="space-y-6 px-6 py-5">
        {/* Read-only derived info */}
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

          {/* Auto-reply toggle */}
          <div
            className="flex items-center justify-between gap-3"
            data-testid="auto-reply-section"
          >
            <div className="flex items-center gap-2 text-sm">
              <Bot className="h-4 w-4 text-muted-foreground" />
              <div>
                <p className="font-medium">Auto-reply IA</p>
                <p className="text-xs text-muted-foreground">
                  Respostas automáticas via IA para mensagens recebidas.
                </p>
              </div>
            </div>
            <Switch
              checked={line.auto_reply_enabled}
              onCheckedChange={(checked) =>
                toggleAutoReply.mutate(
                  { id: line.id, enabled: checked },
                  {
                    onSuccess: () =>
                      toast.success(
                        checked
                          ? "Auto-reply ativado"
                          : "Auto-reply desativado",
                      ),
                    onError: (e: any) =>
                      toast.error(
                        e?.message ?? "Falha ao atualizar auto-reply",
                      ),
                  },
                )
              }
              disabled={toggleAutoReply.isPending}
              data-testid="auto-reply-switch"
            />
          </div>

          <Separator />

          {/* Editable fields */}
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
                  {keyMode === "editing"
                    ? "(digite a nova chave)"
                    : "(toque no lápis para trocar)"}
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
                    aria-label={
                      keyMode === "revealed" ? "Ocultar API key" : "Mostrar API key"
                    }
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

          {/* Session actions */}
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

          <Separator />

          <AuthorizedNumbersEditor
            lineId={line.id}
            initialNumbers={line.authorized_numbers ?? []}
          />

          <Separator />

          <BoundChatsEditor
            lineId={line.id}
            initialChats={line.bound_chats ?? []}
          />
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
    </>
  );
}

// ─── ConnectionDetailDialog (exported — thin modal wrapper) ──────────────────
/**
 * ConnectionDetailDialog — the Dialog-chrome consumer of `ConnectionSettingsPanel`.
 * Shared by ClienteModal + Conexoes: full QR/config management for one WAHA
 * connection line, presented as a modal.
 */
export function ConnectionDetailDialog({
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
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <ConnectionSettingsPanel
          line={line}
          onRequestDelete={onRequestDelete}
          onSaved={onClose}
          autoStart={autoStart}
        />
      </DialogContent>
    </Dialog>
  );
}
