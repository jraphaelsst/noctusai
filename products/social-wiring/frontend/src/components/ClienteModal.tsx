/**
 * ClienteModal — tabbed sheet for one cliente.
 *
 * Tab "Contas"
 *   · Edit name / kind / notes
 *   · Integration accounts scoped to this cliente (seed IntegrationCard)
 *   · WhatsApp connections scoped to this cliente
 *
 * Tab "Chat"
 *   · Connection picker (WA connections for this cliente)
 *   · WhatsAppChatWindow — live two-pane chat
 *
 * Inputs:
 *   client  — Cliente object (already loaded by the parent Clientes page)
 *   open    — Dialog open state
 *   onClose — called when the dialog requests close
 */
import { useEffect, useState } from "react";
import {
  AlertCircle,
  Loader2,
  Plus,
  Settings2,
  Smartphone,
  Trash2,
  Wifi,
} from "lucide-react";
import { toast } from "sonner";

// Seed organs
import {
  IntegrationCard,
  IntegrationCardModal,
  type IntegrationAccount as LibIntegrationAccount,
} from "@noctusai/lib";

// UI
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";

// Domain imports
import { ConnectionDetailDialog } from "@/pages/Conexao";
import {
  useClientWhatsAppConnections,
  useWhatsAppConnectionMutations,
  useWhatsAppConnectionStatus,
  type WhatsAppConnectionLine,
} from "@/hooks/useWhatsAppConnections";
import {
  useIntegrationAccounts,
  useUpdateAccount,
  useSetDefaultAccount,
  useDeleteAccount,
  useSyncAccount,
  useStartYouTubeOAuth,
  type IntegrationAccount,
  type IntegrationStatus,
} from "@/hooks/useIntegrationAccounts";
import {
  useUpdateClient,
  useDeleteClient,
  type Client,
} from "@/hooks/useClients";
import { WhatsAppChatWindow } from "@/components/WhatsAppChatWindow";

// ─── Type helpers ─────────────────────────────────────────────────────────────

function toLibAccount(acc: IntegrationAccount): LibIntegrationAccount {
  return acc as unknown as LibIntegrationAccount;
}

function wahaStatusToIntegration(
  status: string | null | undefined,
  paired: boolean,
): IntegrationStatus {
  if (paired) return "validated";
  switch (status) {
    case "WORKING":    return "validated";
    case "SCAN_QR_CODE": return "wiring";
    case "STARTING":   return "validating";
    case "FAILED":     return "error";
    case "STOPPED":    return "disconnected";
    default:           return "disconnected";
  }
}

// ─── WA connection card (polls live status) ───────────────────────────────────

function WaConnectionCard({
  line,
  onOpen,
  onDelete,
}: {
  line: WhatsAppConnectionLine;
  onOpen: (l: WhatsAppConnectionLine) => void;
  onDelete: (l: WhatsAppConnectionLine) => void;
}) {
  const { data: status } = useWhatsAppConnectionStatus(line.id);
  const integrationStatus = wahaStatusToIntegration(
    status?.status ?? null,
    !!status?.paired,
  );

  const libAccount = {
    id: line.id,
    provider: "whatsapp",
    account_label: line.label,
    is_default: false,
    client_id: null,
    status: integrationStatus,
    channel_info: {
      session: line.session_name,
      phone: status?.me_id ?? null,
      webhook_url: line.webhook_url,
    },
    metadata: {},
    last_synced_at: null,
  } as unknown as LibIntegrationAccount;

  return (
    <div className="relative group">
      <IntegrationCard account={libAccount} onOpenModal={() => onOpen(line)} />
      <button
        type="button"
        onClick={(e) => { e.stopPropagation(); onDelete(line); }}
        className="absolute right-8 top-2 rounded-md p-1 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100 focus-visible:opacity-100 hover:text-destructive"
        aria-label={`Excluir conexão ${line.label}`}
      >
        <Trash2 className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}

// ─── "Nova conexão WA" mini-dialog ────────────────────────────────────────────

function AddWaConnectionDialog({
  clientId,
  onCreated,
  onClose,
}: {
  clientId: string;
  onCreated: (line: WhatsAppConnectionLine) => void;
  onClose: () => void;
}) {
  const [label, setLabel] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [error, setError] = useState<string | null>(null);

  const { create } = useWhatsAppConnectionMutations();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!label.trim() || !apiKey.trim()) {
      setError("Label e API Key são obrigatórios.");
      return;
    }
    try {
      const line = await create.mutateAsync({ label: label.trim(), api_key: apiKey.trim(), client_id: clientId });
      toast.success("Conexão criada. Escaneie o QR para parear.");
      onCreated(line);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Erro ao criar conexão.");
    }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>Nova conexão WhatsApp</DialogTitle>
          <DialogDescription>
            Esta conexão será vinculada a este cliente.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4 pt-2">
          <div className="space-y-1.5">
            <Label htmlFor="wac-label">Label</Label>
            <Input
              id="wac-label"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="Ex: WhatsApp Vendas"
              autoFocus
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="wac-key">WAHA API Key</Label>
            <Input
              id="wac-key"
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="••••••••"
            />
          </div>
          {error && (
            <p className="text-xs text-destructive flex items-center gap-1">
              <AlertCircle className="h-3 w-3" /> {error}
            </p>
          )}
          <div className="flex justify-end gap-2 pt-1">
            <Button type="button" variant="ghost" onClick={onClose} disabled={create.isPending}>
              Cancelar
            </Button>
            <Button type="submit" disabled={create.isPending}>
              {create.isPending && <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />}
              Criar
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// ─── Tab: Contas ──────────────────────────────────────────────────────────────

function ContasTab({ client }: { client: Client }) {
  // Edit form state
  const [name, setName] = useState(client.name);
  const [kind, setKind] = useState(client.kind ?? "");
  const [notes, setNotes] = useState(client.notes ?? "");
  const [editSaving, setEditSaving] = useState(false);

  const updateClient = useUpdateClient();
  const deleteClient = useDeleteClient();

  useEffect(() => {
    setName(client.name);
    setKind(client.kind ?? "");
    setNotes(client.notes ?? "");
  }, [client.id, client.name, client.kind, client.notes]);

  async function handleSave() {
    setEditSaving(true);
    try {
      await updateClient.mutateAsync({ id: client.id, name: name.trim() || undefined, kind: kind || null, notes: notes || null });
      toast.success("Cliente atualizado.");
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Falha ao salvar.");
    } finally {
      setEditSaving(false);
    }
  }

  // Integration accounts
  const {
    data: intAccounts = [],
    isLoading: loadingInt,
    isError: errorInt,
  } = useIntegrationAccounts({ clientId: client.id });

  const updateAcc = useUpdateAccount();
  const setDefault = useSetDefaultAccount();
  const deleteAcc = useDeleteAccount();
  const syncAcc = useSyncAccount();
  const youtubeOAuth = useStartYouTubeOAuth();

  function handleConnectYouTube() {
    youtubeOAuth.mutate(
      { clientId: client.id },
      {
        onError: (e: unknown) =>
          toast.error(e instanceof Error ? e.message : "Falha ao iniciar conexão."),
      },
    );
  }
  const [busyAccId, setBusyAccId] = useState<string | null>(null);

  const [openIntAccount, setOpenIntAccount] = useState<IntegrationAccount | null>(null);

  async function handleAccSave(id: string, patch: Record<string, string | null>) {
    setBusyAccId(id);
    try {
      await updateAcc.mutateAsync({ id, ...patch } as any);
      toast.success("Conta atualizada.");
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Falha ao salvar.");
    } finally {
      setBusyAccId(null);
    }
  }
  async function handleAccSetDefault(id: string) {
    setBusyAccId(id);
    try { await setDefault.mutateAsync(id); toast.success("Padrão atualizado."); }
    catch (err: unknown) { toast.error(err instanceof Error ? err.message : "Falha."); }
    finally { setBusyAccId(null); }
  }
  async function handleAccDelete(id: string) {
    setBusyAccId(id);
    try { await deleteAcc.mutateAsync(id); toast.success("Conta excluída."); setOpenIntAccount(null); }
    catch (err: unknown) { toast.error(err instanceof Error ? err.message : "Falha."); }
    finally { setBusyAccId(null); }
  }
  async function handleAccSync(id: string) {
    setBusyAccId(id);
    try { await syncAcc.mutateAsync(id); toast.success("Sincronização iniciada."); }
    catch (err: unknown) { toast.error(err instanceof Error ? err.message : "Falha."); }
    finally { setBusyAccId(null); }
  }

  // WhatsApp connections
  const {
    data: waConnections = [],
    isLoading: loadingWa,
    isError: errorWa,
  } = useClientWhatsAppConnections(client.id);

  const [openWaLine, setOpenWaLine] = useState<WhatsAppConnectionLine | null>(null);
  const [addWaOpen, setAddWaOpen] = useState(false);
  const [newWaLine, setNewWaLine] = useState<WhatsAppConnectionLine | null>(null);

  const { remove: removeWa } = useWhatsAppConnectionMutations();

  function handleDeleteWa(line: WhatsAppConnectionLine) {
    removeWa.mutate(line.id, {
      onSuccess: () => toast.success("Conexão excluída."),
      onError: (e: unknown) => toast.error(e instanceof Error ? e.message : "Falha ao excluir."),
    });
  }

  return (
    <div className="space-y-6 pt-4 pb-2 overflow-y-auto flex-1" data-testid="contas-tab">
      {/* ── Edit cliente ─────────────────────────────────────────────────── */}
      <section className="space-y-3">
        <div className="flex items-center gap-2 text-sm font-semibold text-muted-foreground uppercase tracking-wide">
          <Settings2 className="h-3.5 w-3.5" /> Dados do cliente
        </div>
        <div className="space-y-3 pl-1">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="clt-name">Nome</Label>
              <Input
                id="clt-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Nome do cliente"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="clt-kind">Tipo</Label>
              <Select value={kind || "__none__"} onValueChange={(v) => setKind(v === "__none__" ? "" : v)}>
                <SelectTrigger id="clt-kind">
                  <SelectValue placeholder="Tipo..." />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">Nenhum</SelectItem>
                  <SelectItem value="empresa">Empresa</SelectItem>
                  <SelectItem value="pessoa_fisica">Pessoa física</SelectItem>
                  <SelectItem value="parceiro">Parceiro</SelectItem>
                  <SelectItem value="outro">Outro</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="clt-notes">Notas</Label>
            <Textarea
              id="clt-notes"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Observações sobre o cliente..."
              className="resize-none h-20"
            />
          </div>
          <div className="flex justify-end gap-2">
            <Button
              size="sm"
              onClick={handleSave}
              disabled={editSaving || updateClient.isPending}
            >
              {(editSaving || updateClient.isPending) && (
                <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />
              )}
              Salvar
            </Button>
          </div>
        </div>
      </section>

      <Separator />

      {/* ── Integration accounts ──────────────────────────────────────────── */}
      <section className="space-y-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-sm font-semibold text-muted-foreground uppercase tracking-wide">
            <Wifi className="h-3.5 w-3.5" /> Integrações
          </div>
          <Button
            size="sm"
            variant="outline"
            onClick={handleConnectYouTube}
            disabled={youtubeOAuth.isPending}
            className="h-7 text-xs"
          >
            {youtubeOAuth.isPending ? (
              <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" />
            ) : (
              <Plus className="h-3.5 w-3.5 mr-1" />
            )}
            Conectar YouTube
          </Button>
        </div>
        {loadingInt ? (
          <div className="space-y-2 pl-1">
            <Skeleton className="h-16 w-full rounded-lg" />
            <Skeleton className="h-16 w-full rounded-lg" />
          </div>
        ) : errorInt ? (
          <div className="flex items-center gap-2 text-xs text-destructive pl-1 py-2">
            <AlertCircle className="h-4 w-4" /> Erro ao carregar integrações.
          </div>
        ) : intAccounts.length === 0 ? (
          <p className="text-xs text-muted-foreground pl-1 py-2">
            Nenhuma integração vinculada a este cliente.
          </p>
        ) : (
          <div className="grid gap-2 pl-1">
            {intAccounts.map((acc) => (
              <IntegrationCard
                key={acc.id}
                account={toLibAccount(acc)}
                busy={busyAccId === acc.id}
                onSave={(patch) => handleAccSave(acc.id, patch as Record<string, string | null>)}
                onDelete={() => handleAccDelete(acc.id)}
                onSetDefault={() => handleAccSetDefault(acc.id)}
                onSync={() => handleAccSync(acc.id)}
                onOpenModal={() => setOpenIntAccount(acc)}
              />
            ))}
          </div>
        )}
      </section>

      <Separator />

      {/* ── WhatsApp connections ──────────────────────────────────────────── */}
      <section className="space-y-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-sm font-semibold text-muted-foreground uppercase tracking-wide">
            <Smartphone className="h-3.5 w-3.5" /> WhatsApp
          </div>
          <Button
            size="sm"
            variant="outline"
            onClick={() => setAddWaOpen(true)}
            className="h-7 text-xs"
          >
            <Plus className="h-3.5 w-3.5 mr-1" /> Nova conexão
          </Button>
        </div>
        {loadingWa ? (
          <div className="space-y-2 pl-1">
            <Skeleton className="h-16 w-full rounded-lg" />
          </div>
        ) : errorWa ? (
          <div className="flex items-center gap-2 text-xs text-destructive pl-1 py-2">
            <AlertCircle className="h-4 w-4" /> Erro ao carregar conexões WA.
          </div>
        ) : waConnections.length === 0 ? (
          <p className="text-xs text-muted-foreground pl-1 py-2">
            Nenhuma conexão WhatsApp vinculada.
          </p>
        ) : (
          <div className="grid gap-2 pl-1">
            {waConnections.map((line) => (
              <WaConnectionCard
                key={line.id}
                line={line}
                onOpen={setOpenWaLine}
                onDelete={handleDeleteWa}
              />
            ))}
          </div>
        )}
      </section>

      {/* ── Add WA dialog ────────────────────────────────────────────────── */}
      {addWaOpen && (
        <AddWaConnectionDialog
          clientId={client.id}
          onCreated={(line) => {
            setAddWaOpen(false);
            setNewWaLine(line);
          }}
          onClose={() => setAddWaOpen(false)}
        />
      )}

      {/* ── WA connection detail (QR + config) ───────────────────────────── */}
      {(openWaLine ?? newWaLine) && (
        <ConnectionDetailDialog
          line={(openWaLine ?? newWaLine)!}
          autoStart={!!newWaLine && !openWaLine}
          onClose={() => {
            setOpenWaLine(null);
            setNewWaLine(null);
          }}
          onRequestDelete={(l) => {
            handleDeleteWa(l);
            setOpenWaLine(null);
            setNewWaLine(null);
          }}
        />
      )}

      {/* ── Integration account modal ─────────────────────────────────────── */}
      <IntegrationCardModal
        account={openIntAccount ? toLibAccount(openIntAccount) : null}
        onClose={() => setOpenIntAccount(null)}
      />
    </div>
  );
}

// ─── Tab: Chat ────────────────────────────────────────────────────────────────

function ChatTab({ client }: { client: Client }) {
  const {
    data: waConnections = [],
    isLoading,
    isError,
  } = useClientWhatsAppConnections(client.id);

  const [selectedId, setSelectedId] = useState<string>("");

  // Auto-select first connection when the list loads
  useEffect(() => {
    if (!selectedId && waConnections.length > 0) {
      setSelectedId(waConnections[0].id);
    }
  }, [waConnections, selectedId]);

  const selectedLine = waConnections.find((l) => l.id === selectedId);

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-3 text-muted-foreground">
        <Loader2 className="h-6 w-6 animate-spin" />
        <p className="text-xs">Carregando conexões...</p>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-2 text-muted-foreground">
        <AlertCircle className="h-6 w-6 text-destructive" />
        <p className="text-xs">Erro ao carregar conexões WhatsApp.</p>
      </div>
    );
  }

  if (waConnections.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-2 text-muted-foreground p-6">
        <Smartphone className="h-10 w-10 opacity-20" />
        <p className="text-sm font-medium">Nenhuma conexão WhatsApp</p>
        <p className="text-xs text-center">
          Adicione uma conexão na aba "Contas" para iniciar uma conversa.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col flex-1 min-h-0 pt-2" data-testid="chat-tab">
      {/* Connection picker — only shown when there are 2+ connections */}
      {waConnections.length > 1 && (
        <div className="flex items-center gap-2 pb-2 border-b mb-0">
          <Smartphone className="h-4 w-4 text-muted-foreground flex-shrink-0" />
          <Select value={selectedId} onValueChange={setSelectedId}>
            <SelectTrigger className="h-8 text-xs flex-1">
              <SelectValue placeholder="Selecione uma conexão..." />
            </SelectTrigger>
            <SelectContent>
              {waConnections.map((l) => (
                <SelectItem key={l.id} value={l.id} className="text-xs">
                  {l.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}

      {selectedLine ? (
        <WhatsAppChatWindow
          connectionId={selectedLine.id}
          autoReplyEnabled={selectedLine.auto_reply_enabled}
          className="mt-1"
        />
      ) : (
        <div className="flex flex-col items-center justify-center flex-1 text-muted-foreground gap-2">
          <Smartphone className="h-8 w-8 opacity-20" />
          <p className="text-xs">Selecione uma conexão acima.</p>
        </div>
      )}
    </div>
  );
}

// ─── ClienteModal ─────────────────────────────────────────────────────────────

interface ClienteModalProps {
  client: Client;
  open: boolean;
  onClose: () => void;
  /** If true, opens on the Chat tab instead of Contas (default: "contas") */
  defaultTab?: "contas" | "chat";
}

export function ClienteModal({
  client,
  open,
  onClose,
  defaultTab = "contas",
}: ClienteModalProps) {
  const [tab, setTab] = useState(defaultTab);

  // Reset tab when switching clients
  useEffect(() => {
    setTab(defaultTab);
  }, [client.id, defaultTab]);

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent
        className="max-w-2xl h-[80vh] flex flex-col p-0 gap-0 overflow-hidden"
        data-testid="cliente-modal"
      >
        {/* Header */}
        <DialogHeader className="px-6 pt-5 pb-3 border-b">
          <DialogTitle className="text-base font-semibold">{client.name}</DialogTitle>
          <DialogDescription className="text-xs">
            {client.kind ? `${client.kind} · ` : ""}slug: {client.slug}
          </DialogDescription>
        </DialogHeader>

        {/* Tabs */}
        <Tabs
          value={tab}
          onValueChange={(v) => setTab(v as "contas" | "chat")}
          className="flex flex-col flex-1 min-h-0 px-6"
        >
          <TabsList className="w-fit mt-3 mb-0">
            <TabsTrigger value="contas">Contas</TabsTrigger>
            <TabsTrigger value="chat">Chat</TabsTrigger>
          </TabsList>

          <TabsContent value="contas" className="flex-1 overflow-y-auto mt-0 data-[state=inactive]:hidden">
            <ContasTab client={client} />
          </TabsContent>

          <TabsContent value="chat" className="flex flex-col flex-1 min-h-0 mt-0 data-[state=inactive]:hidden">
            <ChatTab client={client} />
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}

export default ClienteModal;
