/**
 * MarcaModal — tabbed sheet for one marca.
 *
 * Tab "Contas"
 *   · Edit name / kind / notes
 *   · Integration accounts scoped to this marca (seed IntegrationCard)
 *   · WhatsApp connections scoped to this marca
 *
 * Tab "Chat"
 *   · Connection picker (WA connections for this marca)
 *   · WhatsAppChatWindow — live two-pane chat
 *
 * Inputs:
 *   marca   — Marca object (already loaded by the parent Marcas page)
 *   open    — Dialog open state
 *   onClose — called when the dialog requests close
 */
import { useEffect, useState } from "react";
import type { LucideIcon } from "lucide-react";
import {
  AlertCircle,
  CheckCircle2,
  Clock,
  HardDrive,
  Instagram,
  Loader2,
  Mail,
  Network,
  Plus,
  Settings2,
  Share2,
  Smartphone,
  Trash2,
  Wifi,
  Youtube,
} from "lucide-react";
import { toast } from "sonner";
import { useNavigate } from "react-router-dom";

// Seed organs
import {
  IntegrationCard,
  IntegrationCardModal,
  getProviderConfig,
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
import { ConnectionDetailDialog } from "@/components/ConnectionDetailDialog";
import {
  useClientWhatsAppConnections,
  useWhatsAppConnectionMutations,
  useWhatsAppConnectionStatus,
  type WhatsAppConnectionLine,
} from "@/hooks/useWhatsAppConnections";
import {
  useIntegrationAccounts,
  useCreateAccount,
  useUpdateAccount,
  useDeleteAccount,
  useSyncAccount,
  useStartYouTubeOAuth,
  useStartProviderOAuth,
  type IntegrationAccount,
  type IntegrationStatus,
} from "@/hooks/useIntegrationAccounts";
import {
  useUpdateMarca,
  useDeleteMarca,
  type Marca,
} from "@/hooks/useMarcas";
import {
  useMailchimpConnection,
  useUpsertMailchimpConnection,
  type MailchimpConnection,
} from "@/hooks/useMailchimp";
import { WhatsAppChatWindow } from "@/components/WhatsAppChatWindow";
import { useActiveAccountStore } from "@/state/useActiveAccount";

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

// ─── Provider catalog ────────────────────────────────────────────────────────

type ConnectKind = "oauth" | "manual" | "soon";

interface ProviderDef {
  id: string;
  label: string;
  icon: LucideIcon;
  connectKind: ConnectKind;
}

const PROVIDER_CATALOG: ProviderDef[] = [
  { id: "youtube",      label: "YouTube",      icon: Youtube,   connectKind: "oauth"  },
  { id: "gmail",        label: "Gmail",        icon: Mail,      connectKind: "oauth"  },
  { id: "google_drive", label: "Google Drive", icon: HardDrive, connectKind: "oauth"  },
  { id: "n8n",          label: "n8n",          icon: Network,   connectKind: "manual" },
  { id: "meta",         label: "Meta",         icon: Share2,    connectKind: "oauth"  },
  { id: "instagram",    label: "Instagram",    icon: Instagram, connectKind: "oauth"  },
  { id: "mailchimp",    label: "Mailchimp",    icon: Mail,      connectKind: "manual" },
];

// ─── N8n inline connect form ──────────────────────────────────────────────────
//
// v2 field-set (2026-07-16): base_url + api_key (both required) replace the
// old webhook_url + optional-api_key shape — see
// app/services/integration_providers.py for why (a webhook_url is one
// workflow's trigger URL; it cannot list anything via the n8n public API).
// Scope is narrow by design: this form only connects the account. The
// client's n8n tag is set separately, on the n8n page's own Configurações
// subtab (PUT /api/n8n/settings, app/modules/n8n/) — that module writes
// channel_info directly and owns the whole lifecycle, so it never touches
// this generic integration_accounts create path.

function N8nConnectForm({
  marcaId,
  onCancel,
  onConnected,
}: {
  marcaId: string;
  onCancel: () => void;
  onConnected: () => void;
}) {
  const [label, setLabel] = useState("n8n");
  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const createAccount = useCreateAccount();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!baseUrl.trim()) {
      toast.error("URL da instância é obrigatória.");
      return;
    }
    if (!apiKey.trim()) {
      toast.error("API Key é obrigatória.");
      return;
    }
    try {
      await createAccount.mutateAsync({
        provider: "n8n",
        account_label: label.trim() || "n8n",
        credential: { base_url: baseUrl.trim(), api_key: apiKey.trim() },
        marca_id: marcaId,
      });
      toast.success("n8n conectado com sucesso.");
      onConnected();
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Falha ao conectar n8n.");
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="mt-2 space-y-2 rounded-md border bg-muted/20 p-3"
      data-testid="n8n-connect-form"
    >
      <div className="space-y-1">
        <Label htmlFor="n8n-label" className="text-xs">Label</Label>
        <Input
          id="n8n-label"
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          className="h-7 text-xs"
          disabled={createAccount.isPending}
        />
      </div>
      <div className="space-y-1">
        <Label htmlFor="n8n-base-url" className="text-xs">URL da instância *</Label>
        <Input
          id="n8n-base-url"
          value={baseUrl}
          onChange={(e) => setBaseUrl(e.target.value)}
          placeholder="https://n8n.example.com"
          className="h-7 text-xs font-mono"
          disabled={createAccount.isPending}
          data-testid="n8n-base-url"
        />
      </div>
      <div className="space-y-1">
        <Label htmlFor="n8n-apikey" className="text-xs">API Key *</Label>
        <Input
          id="n8n-apikey"
          type="password"
          value={apiKey}
          onChange={(e) => setApiKey(e.target.value)}
          placeholder="••••••••"
          className="h-7 text-xs"
          disabled={createAccount.isPending}
          data-testid="n8n-api-key"
        />
      </div>
      <div className="flex gap-2 pt-1">
        <Button
          type="button"
          size="sm"
          variant="ghost"
          className="h-7 text-xs"
          onClick={onCancel}
          disabled={createAccount.isPending}
        >
          Cancelar
        </Button>
        <Button
          type="submit"
          size="sm"
          className="h-7 text-xs"
          disabled={createAccount.isPending || !baseUrl.trim() || !apiKey.trim()}
          data-testid="n8n-connect-submit"
        >
          {createAccount.isPending && <Loader2 className="mr-1.5 h-3 w-3 animate-spin" />}
          Conectar
        </Button>
      </div>
    </form>
  );
}

// ─── Mailchimp inline connect form (manual API-key) ───────────────────────────

function MailchimpConnectForm({
  marcaId,
  connection,
  onCancel,
  onConnected,
}: {
  marcaId: string;
  connection: MailchimpConnection | null;
  onCancel: () => void;
  onConnected: () => void;
}) {
  const [apiKey, setApiKey] = useState("");
  const [serverPrefix, setServerPrefix] = useState(connection?.server_prefix ?? "");
  const [audienceId, setAudienceId] = useState(connection?.audience_id ?? "");
  const upsert = useUpsertMailchimpConnection();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!apiKey.trim()) {
      toast.error("API key é obrigatória.");
      return;
    }
    try {
      await upsert.mutateAsync({
        api_key: apiKey.trim(),
        server_prefix: serverPrefix.trim() || undefined,
        audience_id: audienceId.trim() || undefined,
        marca_id: marcaId,
      });
      toast.success("Mailchimp conectado com sucesso.");
      onConnected();
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Falha ao conectar Mailchimp.");
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="mt-2 space-y-2 rounded-md border bg-muted/20 p-3"
      data-testid="mailchimp-connect-form"
    >
      <div className="space-y-1">
        <Label htmlFor="mc-apikey" className="text-xs">API Key *</Label>
        <Input
          id="mc-apikey"
          type="password"
          value={apiKey}
          onChange={(e) => setApiKey(e.target.value)}
          placeholder="••••••••-us6"
          className="h-7 text-xs font-mono"
          disabled={upsert.isPending}
          data-testid="mailchimp-api-key"
        />
      </div>
      <div className="space-y-1">
        <Label htmlFor="mc-prefix" className="text-xs">Server prefix (opcional)</Label>
        <Input
          id="mc-prefix"
          value={serverPrefix}
          onChange={(e) => setServerPrefix(e.target.value)}
          placeholder="us6"
          className="h-7 text-xs font-mono"
          disabled={upsert.isPending}
          data-testid="mailchimp-server-prefix"
        />
      </div>
      <div className="space-y-1">
        <Label htmlFor="mc-audience" className="text-xs">Audience ID (opcional)</Label>
        <Input
          id="mc-audience"
          value={audienceId}
          onChange={(e) => setAudienceId(e.target.value)}
          placeholder="a1b2c3d4e5"
          className="h-7 text-xs font-mono"
          disabled={upsert.isPending}
          data-testid="mailchimp-audience-id"
        />
      </div>
      <div className="flex gap-2 pt-1">
        <Button
          type="button"
          size="sm"
          variant="ghost"
          className="h-7 text-xs"
          onClick={onCancel}
          disabled={upsert.isPending}
        >
          Cancelar
        </Button>
        <Button
          type="submit"
          size="sm"
          className="h-7 text-xs"
          disabled={upsert.isPending || !apiKey.trim()}
          data-testid="mailchimp-connect-submit"
        >
          {upsert.isPending && <Loader2 className="mr-1.5 h-3 w-3 animate-spin" />}
          {connection?.connected ? "Salvar" : "Conectar"}
        </Button>
      </div>
    </form>
  );
}

// ─── Mailchimp provider row (per-marca, separate endpoint) ───────────────────

/**
 * Mailchimp is NOT an IntegrationAccount — its connection lives on the dedicated
 * /api/mailchimp/connection endpoint scoped by client_id. This row renders the
 * connected indicator (with re-configure) OR the manual connect affordance +
 * inline form, mirroring the greyed-row chrome used by the other providers.
 */
function MailchimpProviderRow({
  marcaId,
  icon: ProviderIcon,
  label,
}: {
  marcaId: string;
  icon: LucideIcon;
  label: string;
}) {
  const { data: connection, isLoading } = useMailchimpConnection(marcaId);
  const [formOpen, setFormOpen] = useState(false);
  const connected = !!connection?.connected;

  const subtitle = connected
    ? [connection?.audience_name, connection?.server_prefix]
        .filter(Boolean)
        .join(" · ")
    : null;

  return (
    <div className="space-y-1">
      <div
        className={
          connected
            ? "flex items-center justify-between rounded-lg border bg-card px-3 py-2.5"
            : "flex items-center justify-between rounded-lg border border-dashed bg-muted/20 px-3 py-2.5 opacity-70"
        }
        data-testid="provider-row-mailchimp"
      >
        <div className="flex items-center gap-2.5 min-w-0">
          <ProviderIcon
            className={`h-4 w-4 shrink-0 ${connected ? "text-primary" : "text-muted-foreground"}`}
          />
          <div className="min-w-0">
            <span
              className={`block text-sm font-medium truncate ${connected ? "text-foreground" : "text-muted-foreground"}`}
            >
              {label}
            </span>
            {subtitle && (
              <span className="block text-xs text-muted-foreground truncate">
                {subtitle}
              </span>
            )}
          </div>
        </div>

        {isLoading ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />
        ) : connected ? (
          <div className="flex items-center gap-2">
            <span className="flex items-center gap-1 text-xs text-primary">
              <CheckCircle2 className="h-3.5 w-3.5" />
              Conectado
            </span>
            <Button
              size="sm"
              variant="ghost"
              className="h-7 text-xs"
              onClick={() => setFormOpen((p) => !p)}
              data-testid="mailchimp-reconfigure-btn"
            >
              Reconfigurar
            </Button>
          </div>
        ) : (
          <Button
            size="sm"
            variant="outline"
            className="h-7 text-xs"
            onClick={() => setFormOpen((p) => !p)}
            data-testid="connect-btn-mailchimp"
          >
            <Plus className="h-3.5 w-3.5 mr-1" />
            Conectar
          </Button>
        )}
      </div>

      {formOpen && (
        <MailchimpConnectForm
          marcaId={marcaId}
          connection={connection ?? null}
          onCancel={() => setFormOpen(false)}
          onConnected={() => setFormOpen(false)}
        />
      )}
    </div>
  );
}

// ─── WA connection card (polls live status) ───────────────────────────────────

function WaConnectionCard({
  line,
  onOpenDashboard,
  onOpenDetails,
  onDelete,
}: {
  line: WhatsAppConnectionLine;
  /** Card body click — deep-links into the WhatsApp chat page (or falls
   * back to the detail dialog when no dashboardRoute is configured). */
  onOpenDashboard: (l: WhatsAppConnectionLine) => void;
  /** Secondary "detalhes" affordance — always opens the QR/config dialog. */
  onOpenDetails: (l: WhatsAppConnectionLine) => void;
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
    marca_id: null,
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
      <IntegrationCard
        account={libAccount}
        onOpenModal={() => onOpenDashboard(line)}
        onOpenDetails={() => onOpenDetails(line)}
      />
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
  marcaId,
  onCreated,
  onClose,
}: {
  marcaId: string;
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
      const line = await create.mutateAsync({ label: label.trim(), api_key: apiKey.trim(), marca_id: marcaId });
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
            Esta conexão será vinculada a esta marca.
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

function ContasTab({ client }: { client: Marca }) {
  // Edit form state
  const [name, setName] = useState(client.name);
  const [kind, setKind] = useState(client.kind ?? "");
  const [notes, setNotes] = useState(client.notes ?? "");
  const [editSaving, setEditSaving] = useState(false);

  const updateMarca = useUpdateMarca();
  const deleteMarca = useDeleteMarca();

  // Deep-link navigation — a connected card's body click pre-selects this
  // client/account in the shared store, then routes into the provider's own
  // dashboard (per ProviderCardConfig.dashboardRoute).
  const navigate = useNavigate();
  const setActiveMarca = useActiveAccountStore((s) => s.setActiveMarca);
  const setActiveAccount = useActiveAccountStore((s) => s.setActiveAccount);

  useEffect(() => {
    setName(client.name);
    setKind(client.kind ?? "");
    setNotes(client.notes ?? "");
  }, [client.id, client.name, client.kind, client.notes]);

  async function handleSave() {
    setEditSaving(true);
    try {
      await updateMarca.mutateAsync({ id: client.id, name: name.trim() || undefined, kind: kind || null, notes: notes || null });
      toast.success("Marca atualizada.");
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
  } = useIntegrationAccounts({ marcaId: client.id });

  const updateAcc = useUpdateAccount();
  const deleteAcc = useDeleteAccount();
  const syncAcc = useSyncAccount();
  const youtubeOAuth = useStartYouTubeOAuth();
  const gmailOAuth = useStartProviderOAuth("gmail");
  const driveOAuth = useStartProviderOAuth("google_drive");
  const metaOAuth = useStartProviderOAuth("meta");

  const [busyAccId, setBusyAccId] = useState<string | null>(null);
  const [n8nFormOpen, setN8nFormOpen] = useState(false);

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

  /**
   * Card-body click for a connected IntegrationCard. Deep-links into the
   * provider's own dashboard with this client/account pre-selected — falls
   * back to opening the (still-reachable via the details icon) detail modal
   * for providers without a dashboardRoute (gmail, google_drive, n8n).
   */
  function handleAccOpen(acc: IntegrationAccount) {
    const dashboardRoute = getProviderConfig(acc.provider)?.dashboardRoute;
    if (dashboardRoute) {
      setActiveMarca(client.id);
      // Key the pre-selection under the account's OWN provider — the page we
      // are about to navigate to reads only its own slot. (setActiveClient
      // clears every slot first, so the order here matters.)
      setActiveAccount(acc.provider, acc.id);
      navigate(dashboardRoute);
    } else {
      setOpenIntAccount(acc);
    }
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

  /**
   * WA card-body click — deep-links into the WhatsApp chat page with this
   * client/connection pre-selected; falls back to the QR/config dialog if
   * whatsapp has no dashboardRoute configured.
   */
  function handleWaOpen(line: WhatsAppConnectionLine) {
    const dashboardRoute = getProviderConfig("whatsapp")?.dashboardRoute;
    if (dashboardRoute) {
      setActiveMarca(client.id);
      // A WhatsApp connection id is not an integration_accounts.id at all —
      // it keys `whatsapp` explicitly so WhatsAppChat can find it and no
      // other page can mistake it for one of theirs.
      setActiveAccount("whatsapp", line.id);
      navigate(dashboardRoute);
    } else {
      setOpenWaLine(line);
    }
  }

  return (
    <div className="space-y-6 pt-4 pb-2 overflow-y-auto flex-1" data-testid="contas-tab">
      {/* ── Edit marca ─────────────────────────────────────────────────── */}
      <section className="space-y-3">
        <div className="flex items-center gap-2 text-sm font-semibold text-muted-foreground uppercase tracking-wide">
          <Settings2 className="h-3.5 w-3.5" /> Dados da marca
        </div>
        <div className="space-y-3 pl-1">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="clt-name">Nome</Label>
              <Input
                id="clt-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Nome da marca"
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
              placeholder="Observações sobre a marca..."
              className="resize-none h-20"
            />
          </div>
          <div className="flex justify-end gap-2">
            <Button
              size="sm"
              onClick={handleSave}
              disabled={editSaving || updateMarca.isPending}
            >
              {(editSaving || updateMarca.isPending) && (
                <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />
              )}
              Salvar
            </Button>
          </div>
        </div>
      </section>

      <Separator />

      {/* ── All-providers integration grid ────────────────────────────────── */}
      <section className="space-y-2" data-testid="integrations-grid">
        <div className="flex items-center gap-2 text-sm font-semibold text-muted-foreground uppercase tracking-wide">
          <Wifi className="h-3.5 w-3.5" /> Integrações
        </div>

        {loadingInt ? (
          <div className="space-y-2 pl-1">
            <Skeleton className="h-14 w-full rounded-lg" />
            <Skeleton className="h-14 w-full rounded-lg" />
            <Skeleton className="h-14 w-full rounded-lg" />
          </div>
        ) : errorInt ? (
          <div className="flex items-center gap-2 text-xs text-destructive pl-1 py-2">
            <AlertCircle className="h-4 w-4" /> Erro ao carregar integrações.
          </div>
        ) : (
          <div className="grid gap-1.5 pl-1">
            {PROVIDER_CATALOG.map((provider) => {
              const accounts = intAccounts.filter((a) => a.provider === provider.id);
              const ProviderIcon = provider.icon;

              // Mailchimp uses a dedicated per-marca endpoint
              // (/api/mailchimp/connection), not the IntegrationAccounts store.
              if (provider.id === "mailchimp") {
                return (
                  <MailchimpProviderRow
                    key={provider.id}
                    marcaId={client.id}
                    icon={ProviderIcon}
                    label={provider.label}
                  />
                );
              }

              // If accounts exist — show IntegrationCard rows
              if (accounts.length > 0) {
                return (
                  <div key={provider.id} className="space-y-1.5">
                    {accounts.map((acc) => (
                      <IntegrationCard
                        key={acc.id}
                        account={toLibAccount(acc)}
                        busy={busyAccId === acc.id}
                        onSave={(patch) => handleAccSave(acc.id, patch as Record<string, string | null>)}
                        onDelete={() => handleAccDelete(acc.id)}
                        onSync={() => handleAccSync(acc.id)}
                        onOpenModal={() => handleAccOpen(acc)}
                        onOpenDetails={() => setOpenIntAccount(acc)}
                      />
                    ))}
                  </div>
                );
              }

              // No accounts — show greyed row with connect affordance
              return (
                <div key={provider.id} className="space-y-1">
                  <div
                    className="flex items-center justify-between rounded-lg border border-dashed bg-muted/20 px-3 py-2.5 opacity-70"
                    data-testid={`provider-row-${provider.id}`}
                  >
                    <div className="flex items-center gap-2.5 min-w-0">
                      <ProviderIcon className="h-4 w-4 shrink-0 text-muted-foreground" />
                      <span className="text-sm font-medium text-muted-foreground truncate">
                        {provider.label}
                      </span>
                    </div>

                    {provider.connectKind === "soon" && (
                      <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                        <Clock className="h-3.5 w-3.5" />
                        em breve
                      </div>
                    )}

                    {provider.connectKind === "oauth" && (
                      <div className="flex items-center gap-1.5">
                        <Button
                          size="sm"
                          variant="outline"
                          className="h-7 text-xs"
                          disabled={
                            (provider.id === "youtube" && youtubeOAuth.isPending) ||
                            (provider.id === "gmail" && gmailOAuth.isPending) ||
                            (provider.id === "google_drive" && driveOAuth.isPending) ||
                            ((provider.id === "meta" || provider.id === "instagram") && metaOAuth.isPending)
                          }
                          onClick={() => {
                            const opts = { marcaId: client.id };
                            if (provider.id === "youtube") {
                              youtubeOAuth.mutate(opts, {
                                onError: (e: unknown) => toast.error(e instanceof Error ? e.message : "Falha."),
                              });
                            } else if (provider.id === "gmail") {
                              gmailOAuth.mutate(opts, {
                                onError: (e: unknown) => toast.error(e instanceof Error ? e.message : "Falha."),
                              });
                            } else if (provider.id === "google_drive") {
                              driveOAuth.mutate(opts, {
                                onError: (e: unknown) => toast.error(e instanceof Error ? e.message : "Falha."),
                              });
                            } else if (provider.id === "meta" || provider.id === "instagram") {
                              // This app uses Facebook Login for Business — Instagram is
                              // reached THROUGH the Facebook/Meta connection (a linked Page),
                              // so the Instagram button runs the same Meta OAuth.
                              metaOAuth.mutate(opts, {
                                onError: (e: unknown) => toast.error(e instanceof Error ? e.message : "Falha."),
                              });
                            }
                          }}
                          data-testid={`connect-btn-${provider.id}`}
                        >
                          {((provider.id === "youtube" && youtubeOAuth.isPending) ||
                            (provider.id === "gmail" && gmailOAuth.isPending) ||
                            (provider.id === "google_drive" && driveOAuth.isPending) ||
                            ((provider.id === "meta" || provider.id === "instagram") && metaOAuth.isPending)) ? (
                            <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" />
                          ) : (
                            <Plus className="h-3.5 w-3.5 mr-1" />
                          )}
                          Conectar
                        </Button>
                      </div>
                    )}

                    {provider.connectKind === "manual" && (
                      <Button
                        size="sm"
                        variant="outline"
                        className="h-7 text-xs"
                        onClick={() => setN8nFormOpen((prev) => !prev)}
                        data-testid={`connect-btn-${provider.id}`}
                      >
                        <Plus className="h-3.5 w-3.5 mr-1" />
                        Conectar
                      </Button>
                    )}
                  </div>

                  {/* n8n inline form */}
                  {provider.id === "n8n" && n8nFormOpen && (
                    <N8nConnectForm
                      marcaId={client.id}
                      onCancel={() => setN8nFormOpen(false)}
                      onConnected={() => setN8nFormOpen(false)}
                    />
                  )}
                </div>
              );
            })}
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
                onOpenDashboard={handleWaOpen}
                onOpenDetails={setOpenWaLine}
                onDelete={handleDeleteWa}
              />
            ))}
          </div>
        )}
      </section>

      {/* ── Add WA dialog ────────────────────────────────────────────────── */}
      {addWaOpen && (
        <AddWaConnectionDialog
          marcaId={client.id}
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

function ChatTab({ client }: { client: Marca }) {
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

// ─── MarcaModal ───────────────────────────────────────────────────────────────

interface MarcaModalProps {
  client: Marca;
  open: boolean;
  onClose: () => void;
  /** If true, opens on the Chat tab instead of Contas (default: "contas") */
  defaultTab?: "contas" | "chat";
}

export function MarcaModal({
  client,
  open,
  onClose,
  defaultTab = "contas",
}: MarcaModalProps) {
  const [tab, setTab] = useState(defaultTab);

  // Reset tab when switching clients
  useEffect(() => {
    setTab(defaultTab);
  }, [client.id, defaultTab]);

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent
        className="max-w-2xl h-[80vh] flex flex-col p-0 gap-0 overflow-hidden"
        data-testid="marca-modal"
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

export default MarcaModal;
