/**
 * Conexoes — unified connections page.
 *
 * Sections:
 *   1. WhatsApp  — card listing using the IntegrationCard lib organ (styled as
 *                  seed IntegrationCard). Each card's modal opens the rich
 *                  ConnectionDetailDialog from Conexao.tsx with QR+config panels.
 *   2. YouTube   — card listing using the IntegrationCard lib organ, grouped
 *                  by client ("Unassigned" for client_id=null).
 *                  Full card treatment: onSave / onDelete / onSetDefault / onSync
 *                  wired to real mutations. IntegrationCardModal for details.
 *
 * Marca management: "Gerenciar marcas" button opens MarcaManagementModal
 * inline — no new nav route. This keeps the /conexoes page as the single
 * surface for all connection management.
 *
 * YouTube add-account affordance: "Conectar canal" button allows choosing
 * which client the new account attaches to, then triggers OAuth.
 *
 * Active account/client selection is NOT the focus here — that lives in the
 * YouTube Dashboard page via the AccountSwitcher. Conexoes is the management
 * surface; YouTube is the data surface.
 *
 * Handles ?account_created=<id> query param from the OAuth callback.
 */
import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import {
  Link2,
  Loader2,
  Plug,
  Plus,
  Settings2,
  Smartphone,
  Trash2,
  Users,
} from "lucide-react";

import {
  IntegrationCard,
  IntegrationCardModal,
  type IntegrationAccount as LibIntegrationAccount,
  type IntegrationStatus,
} from "@noctusai/lib";

import { Separator } from "@/components/ui/separator";
import { Button } from "@/components/ui/button";

import { ConnectionDetailDialog } from "@/components/ConnectionDetailDialog";
import {
  useWhatsAppConnections,
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
  useAdoptLegacy,
  useStartYouTubeOAuth,
  type IntegrationAccount,
} from "@/hooks/useIntegrationAccounts";
import { useMarcas, type Marca } from "@/hooks/useMarcas";
import { MarcaManagementModal } from "@/components/MarcaManagementModal";
import { InstagramCardSection } from "@/components/InstagramCardSection";

// ─── Type bridge ──────────────────────────────────────────────────────────────
// The lib's IntegrationAccount and the product's IntegrationAccount are
// structurally identical (lib mirrors BE contract). Cast is safe; the lib type
// is the upstream source of truth from 70efce67.
function toLibAccount(acc: IntegrationAccount): LibIntegrationAccount {
  return acc as unknown as LibIntegrationAccount;
}

// ─── WAHA status → seed IntegrationStatus mapping ────────────────────────────
function wahaStatusToIntegration(
  wahaStatus: string | null | undefined,
  paired: boolean,
): IntegrationStatus {
  if (paired) return "validated";
  switch (wahaStatus) {
    case "WORKING":
      return "validated";
    case "SCAN_QR_CODE":
      return "wiring";
    case "STARTING":
      return "validating";
    case "FAILED":
      return "error";
    case "STOPPED":
      return "disconnected";
    default:
      return "disconnected";
  }
}

// ─── Per-connection card (polls live status) ──────────────────────────────────
function WhatsAppConnectionCard({
  line,
  onOpen,
  onDelete,
}: {
  line: WhatsAppConnectionLine;
  onOpen: (line: WhatsAppConnectionLine) => void;
  onDelete: (line: WhatsAppConnectionLine) => void;
}) {
  const { data: status } = useWhatsAppConnectionStatus(line.id);
  const integrationStatus = wahaStatusToIntegration(
    status?.status ?? null,
    !!status?.paired,
  );

  // Cast through unknown: org_id/created_at/updated_at are not available
  // in the WAHA line model; the card only reads provider-indexed fields
  // from channel_info, which we supply correctly.
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
    <div className="relative">
      <IntegrationCard
        account={libAccount}
        onOpenModal={() => onOpen(line)}
      />
      {/* Per-card delete affordance overlaid as icon outside the card */}
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          onDelete(line);
        }}
        className="absolute right-2 top-2 rounded-md p-1 text-muted-foreground opacity-0 transition-opacity hover:text-destructive group-hover:opacity-100 focus-visible:opacity-100"
        aria-label={`Excluir conexão ${line.label}`}
        data-testid="wa-card-delete"
      >
        <Trash2 className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}

// ─── WhatsApp card section ─────────────────────────────────────────────────────
function WhatsAppCardSection() {
  const {
    data: connections,
    isLoading,
    isError,
  } = useWhatsAppConnections();
  const { remove } = useWhatsAppConnectionMutations();

  const [openLine, setOpenLine] = useState<WhatsAppConnectionLine | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<WhatsAppConnectionLine | null>(null);

  const onDelete = (line: WhatsAppConnectionLine) => setDeleteTarget(line);

  const confirmDelete = () => {
    if (!deleteTarget) return;
    remove.mutate(deleteTarget.id, {
      onSuccess: () => {
        toast.success("Conexão excluída");
        setDeleteTarget(null);
      },
      onError: (e: any) => toast.error(e?.message ?? "Falha ao excluir"),
    });
  };

  if (isLoading) {
    return (
      <div className="flex h-24 items-center justify-center gap-2 text-sm text-muted-foreground" data-testid="wa-loading">
        <Loader2 className="h-4 w-4 animate-spin" />
        Carregando conexões WhatsApp…
      </div>
    );
  }

  if (isError) {
    return (
      <div className="rounded-md border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive" data-testid="wa-error">
        Erro ao carregar conexões WhatsApp.
      </div>
    );
  }

  const list = connections ?? [];

  return (
    <div className="space-y-4" data-testid="wa-card-section">
      {list.length === 0 ? (
        <div className="rounded-md border border-dashed bg-muted/20 px-6 py-8 text-center" data-testid="wa-empty">
          <Smartphone className="mx-auto mb-2 h-8 w-8 text-muted-foreground" />
          <p className="text-sm text-muted-foreground">
            Nenhuma conexão WhatsApp configurada.
          </p>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {list.map((line) => (
            <div key={line.id} className="group relative">
              <WhatsAppConnectionCard
                line={line}
                onOpen={setOpenLine}
                onDelete={onDelete}
              />
            </div>
          ))}
        </div>
      )}

      {/* Per-connection detail dialog */}
      {openLine && (
        <ConnectionDetailDialog
          line={openLine}
          onClose={() => setOpenLine(null)}
          onRequestDelete={(l) => {
            setDeleteTarget(l);
            setOpenLine(null);
          }}
        />
      )}

      {/* Delete confirm */}
      {deleteTarget && (
        <div
          role="dialog"
          aria-modal="true"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
          onClick={(e) => e.target === e.currentTarget && setDeleteTarget(null)}
        >
          <div className="w-full max-w-sm rounded-lg border bg-background p-6 shadow-lg">
            <h3 className="mb-2 font-semibold">Excluir conexão?</h3>
            <p className="mb-6 text-sm text-muted-foreground">
              "{deleteTarget.label}" será removida permanentemente.
            </p>
            <div className="flex justify-end gap-2">
              <Button variant="outline" size="sm" onClick={() => setDeleteTarget(null)}>
                Cancelar
              </Button>
              <Button
                variant="destructive"
                size="sm"
                onClick={confirmDelete}
                disabled={remove.isPending}
                data-testid="wa-confirm-delete"
              >
                {remove.isPending ? (
                  <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                ) : null}
                Excluir
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Client section header ───────────────────────────────────────────────────

function ClientSection({
  client,
  accounts,
  onSave,
  onDelete,
  onSetDefault,
  onSync,
  onOpenModal,
  busyId,
}: {
  client: Marca | null; // null = "Unassigned"
  accounts: IntegrationAccount[];
  onSave: (id: string, patch: Record<string, string | null>) => void;
  onDelete: (id: string) => void;
  onSetDefault: (id: string) => void;
  onSync: (id: string) => void;
  onOpenModal: (acc: IntegrationAccount) => void;
  busyId: string | null;
}) {
  const label = client ? client.name : "Sem marca";
  const meta = client
    ? client.slug + (client.kind ? ` · ${client.kind}` : "")
    : "Contas não atribuídas a uma marca";

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <Users className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
        <div>
          <h3 className="text-sm font-semibold text-foreground">{label}</h3>
          <p className="text-xs text-muted-foreground">{meta}</p>
        </div>
        <span className="ml-auto rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">
          {accounts.length}
        </span>
      </div>

      {accounts.length === 0 ? (
        <div className="rounded-md border border-dashed bg-muted/20 py-4 text-center text-xs text-muted-foreground">
          Nenhuma conta neste grupo.
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {accounts.map((acc) => (
            <IntegrationCard
              key={acc.id}
              account={toLibAccount(acc)}
              busy={busyId === acc.id}
              onSave={(patch) => onSave(acc.id, patch as Record<string, string | null>)}
              onDelete={() => onDelete(acc.id)}
              onSetDefault={() => onSetDefault(acc.id)}
              onSync={() => onSync(acc.id)}
              onOpenModal={() => onOpenModal(acc)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ─── YouTube card section ─────────────────────────────────────────────────────

function YouTubeCardSection({
  marcas,
}: {
  marcas: Marca[];
}) {
  const { data: accounts = [], isLoading, isError } =
    useIntegrationAccounts("youtube");

  const adopt = useAdoptLegacy("youtube");
  const oauthStart = useStartYouTubeOAuth();
  const updateAccount = useUpdateAccount();
  const setDefaultAccount = useSetDefaultAccount();
  const deleteAccount = useDeleteAccount();
  const syncAccount = useSyncAccount();

  const [modalAccount, setModalAccount] =
    useState<IntegrationAccount | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [oauthMarcaId, setOauthMarcaId] = useState<string>("");

  // Adopt-legacy once on mount
  useEffect(() => {
    adopt.mutate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Group accounts by client
  const groups = useMemo(() => {
    const clientMap = new Map<string, IntegrationAccount[]>();
    const unassigned: IntegrationAccount[] = [];

    for (const acc of accounts) {
      if (!acc.marca_id) {
        unassigned.push(acc);
      } else {
        const arr = clientMap.get(acc.marca_id) ?? [];
        arr.push(acc);
        clientMap.set(acc.marca_id, arr);
      }
    }

    // Build ordered groups: assigned clients first (ordered by client name),
    // then "Unassigned" last.
    const result: Array<{ client: Marca | null; accounts: IntegrationAccount[] }> = [];

    const sortedClients = [...marcas].sort((a, b) => a.name.localeCompare(b.name));
    for (const client of sortedClients) {
      const accs = clientMap.get(client.id);
      if (accs && accs.length > 0) {
        result.push({ client, accounts: accs });
      }
    }

    // Any accounts assigned to unknown clients (client deleted but accounts
    // remain) treated as unassigned.
    const knownMarcaIds = new Set(marcas.map((c) => c.id));
    for (const [cid, accs] of clientMap.entries()) {
      if (!knownMarcaIds.has(cid)) {
        unassigned.push(...accs);
      }
    }

    if (unassigned.length > 0) {
      result.push({ client: null, accounts: unassigned });
    }

    return result;
  }, [accounts, marcas]);

  async function handleSave(id: string, patch: Record<string, string | null>) {
    setBusyId(id);
    try {
      await updateAccount.mutateAsync({ id, ...patch });
      toast.success("Conta atualizada");
    } catch (err: any) {
      toast.error("Erro ao atualizar conta", { description: err?.message });
    } finally {
      setBusyId(null);
    }
  }

  async function handleDelete(id: string) {
    setBusyId(id);
    try {
      await deleteAccount.mutateAsync(id);
      toast.success("Conta removida");
    } catch (err: any) {
      toast.error("Erro ao remover conta", { description: err?.message });
    } finally {
      setBusyId(null);
    }
  }

  async function handleSetDefault(id: string) {
    setBusyId(id);
    try {
      await setDefaultAccount.mutateAsync(id);
      toast.success("Conta padrão atualizada");
    } catch (err: any) {
      toast.error("Erro ao definir padrão", { description: err?.message });
    } finally {
      setBusyId(null);
    }
  }

  async function handleSync(id: string) {
    setBusyId(id);
    try {
      await syncAccount.mutateAsync(id);
      toast.success("Canal sincronizado");
    } catch (err: any) {
      toast.error("Erro ao sincronizar", { description: err?.message });
    } finally {
      setBusyId(null);
    }
  }

  function handleConnect() {
    oauthStart.mutate(
      oauthMarcaId ? { marcaId: oauthMarcaId } : undefined,
      {
        onError: (e: any) =>
          toast.error("Falha ao iniciar conexão com o YouTube", {
            description: e?.message ?? "Tente novamente",
          }),
      },
    );
  }

  return (
    <div className="space-y-4">
      {/* Section header + add-account affordance */}
      <div className="flex flex-wrap items-center gap-3">
        <h3 className="text-sm font-medium uppercase tracking-wide text-muted-foreground">
          YouTube
        </h3>

        {/* Client pre-select for new OAuth account */}
        {marcas.length > 0 && (
          <select
            value={oauthMarcaId}
            onChange={(e) => setOauthMarcaId(e.target.value)}
            className="h-8 rounded-md border border-input bg-background px-2.5 text-xs"
            aria-label="Atribuir a marca ao conectar"
          >
            <option value="">Sem marca</option>
            {marcas.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        )}

        <Button
          size="sm"
          variant="outline"
          onClick={handleConnect}
          disabled={oauthStart.isPending}
          className="ml-auto"
        >
          {oauthStart.isPending ? (
            <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
          ) : (
            <Link2 className="mr-1.5 h-3.5 w-3.5" />
          )}
          Conectar canal do YouTube
        </Button>
      </div>

      {/* Loading */}
      {isLoading && (
        <div className="flex items-center gap-2 py-4 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Carregando contas YouTube...
        </div>
      )}

      {/* Error */}
      {isError && (
        <p className="py-4 text-sm text-destructive">
          Erro ao carregar contas. Tente recarregar a página.
        </p>
      )}

      {/* Empty */}
      {!isLoading && !isError && accounts.length === 0 && (
        <div className="rounded-md border border-dashed bg-muted/20 py-8 text-center">
          <Plus className="mx-auto mb-2 h-6 w-6 text-muted-foreground" />
          <p className="text-sm text-muted-foreground">
            Nenhuma conta YouTube conectada.
            <br />
            Use o botão acima para autorizar um canal.
          </p>
        </div>
      )}

      {/* Client groups */}
      {!isLoading && !isError && accounts.length > 0 && (
        <div className="space-y-6">
          {groups.map(({ client, accounts: groupAccounts }) => (
            <ClientSection
              key={client?.id ?? "__unassigned__"}
              client={client}
              accounts={groupAccounts}
              onSave={handleSave}
              onDelete={handleDelete}
              onSetDefault={handleSetDefault}
              onSync={handleSync}
              onOpenModal={setModalAccount}
              busyId={busyId}
            />
          ))}
        </div>
      )}

      {/* Detail modal — wider for connection details */}
      <IntegrationCardModal
        account={modalAccount ? toLibAccount(modalAccount) : null}
        onClose={() => setModalAccount(null)}
        className="sm:max-w-2xl"
      />
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function Conexoes() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [manageClientsOpen, setManageClientsOpen] = useState(false);

  const { data: marcas = [], isLoading: clientsLoading } = useMarcas();

  // Handle OAuth callback: ?account_created=<id> → success toast + clear param
  useEffect(() => {
    const accountId = searchParams.get("account_created");
    if (accountId) {
      toast.success("Canal conectado com sucesso!");
      const next = new URLSearchParams(searchParams);
      next.delete("account_created");
      setSearchParams(next, { replace: true });
    }
  }, [searchParams, setSearchParams]);

  return (
    <div className="space-y-8">
      {/* Page header */}
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <Plug className="h-6 w-6 text-primary" />
          <div>
            <h1 className="text-2xl font-bold text-foreground">Conexões</h1>
            <p className="text-sm text-muted-foreground">
              Gerencie todas as suas conexões: WhatsApp (WAHA), YouTube e outros provedores.
            </p>
          </div>
        </div>

        {/* Manage clients */}
        <Button
          size="sm"
          variant="outline"
          onClick={() => setManageClientsOpen(true)}
          disabled={clientsLoading}
        >
          <Settings2 className="mr-1.5 h-3.5 w-3.5" />
          Gerenciar marcas
          {marcas.length > 0 && (
            <span className="ml-1.5 rounded-full bg-muted px-1.5 py-0.5 text-[10px]">
              {marcas.length}
            </span>
          )}
        </Button>
      </div>

      {/* WhatsApp section */}
      <section className="space-y-4">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Smartphone className="h-5 w-5 text-muted-foreground" />
            <h2 className="text-lg font-semibold">WhatsApp</h2>
          </div>
          <Button size="sm" variant="outline" asChild>
            <Link to="/conexao">
              <Plus className="mr-1.5 h-3.5 w-3.5" />
              Nova conexão
            </Link>
          </Button>
        </div>
        <WhatsAppCardSection />
      </section>

      <Separator />

      {/* YouTube card section */}
      <section className="space-y-4">
        <YouTubeCardSection marcas={marcas} />
      </section>

      <Separator />

      {/* Instagram (Instagram-Login model) card section — DMs without a
          Facebook Page. Distinct provider from `meta`; see
          InstagramCardSection's header for why they are not merged. */}
      <section className="space-y-4">
        <InstagramCardSection marcas={marcas} />
      </section>

      {/* Client management modal */}
      {manageClientsOpen && (
        <MarcaManagementModal
          marcas={marcas}
          onClose={() => setManageClientsOpen(false)}
        />
      )}
    </div>
  );
}
