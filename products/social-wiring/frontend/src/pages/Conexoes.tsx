/**
 * Conexoes — unified connections page.
 *
 * Sections:
 *   1. WhatsApp  — reuses WhatsAppConnections from Conexao.tsx (WAHA sessions)
 *   2. YouTube   — card listing using the IntegrationCard lib organ, grouped
 *                  by client ("Unassigned" for client_id=null).
 *                  Full card treatment: onSave / onDelete / onSetDefault / onSync
 *                  wired to real mutations. IntegrationCardModal for details.
 *
 * Client management: "Gerenciar clientes" button opens ClientManagementModal
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
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import {
  Link2,
  Loader2,
  Plug,
  Plus,
  Settings2,
  Smartphone,
  Users,
} from "lucide-react";

import {
  IntegrationCard,
  IntegrationCardModal,
  type IntegrationAccount as LibIntegrationAccount,
} from "@noctusai/lib";

import { Separator } from "@/components/ui/separator";
import { Button } from "@/components/ui/button";

import { WhatsAppConnections } from "@/pages/Conexao";
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
import { useClients, type Client } from "@/hooks/useClients";
import { ClientManagementModal } from "@/components/ClientManagementModal";

// ─── Type bridge ──────────────────────────────────────────────────────────────
// The lib's IntegrationAccount and the product's IntegrationAccount are
// structurally identical (lib mirrors BE contract). Cast is safe; the lib type
// is the upstream source of truth from 70efce67.
function toLibAccount(acc: IntegrationAccount): LibIntegrationAccount {
  return acc as unknown as LibIntegrationAccount;
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
  client: Client | null; // null = "Unassigned"
  accounts: IntegrationAccount[];
  onSave: (id: string, patch: Record<string, string | null>) => void;
  onDelete: (id: string) => void;
  onSetDefault: (id: string) => void;
  onSync: (id: string) => void;
  onOpenModal: (acc: IntegrationAccount) => void;
  busyId: string | null;
}) {
  const label = client ? client.name : "Sem cliente";
  const meta = client
    ? client.slug + (client.kind ? ` · ${client.kind}` : "")
    : "Contas não atribuídas a um cliente";

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
  clients,
}: {
  clients: Client[];
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
  const [oauthClientId, setOauthClientId] = useState<string>("");

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
      if (!acc.client_id) {
        unassigned.push(acc);
      } else {
        const arr = clientMap.get(acc.client_id) ?? [];
        arr.push(acc);
        clientMap.set(acc.client_id, arr);
      }
    }

    // Build ordered groups: assigned clients first (ordered by client name),
    // then "Unassigned" last.
    const result: Array<{ client: Client | null; accounts: IntegrationAccount[] }> = [];

    const sortedClients = [...clients].sort((a, b) => a.name.localeCompare(b.name));
    for (const client of sortedClients) {
      const accs = clientMap.get(client.id);
      if (accs && accs.length > 0) {
        result.push({ client, accounts: accs });
      }
    }

    // Any accounts assigned to unknown clients (client deleted but accounts
    // remain) treated as unassigned.
    const knownClientIds = new Set(clients.map((c) => c.id));
    for (const [cid, accs] of clientMap.entries()) {
      if (!knownClientIds.has(cid)) {
        unassigned.push(...accs);
      }
    }

    if (unassigned.length > 0) {
      result.push({ client: null, accounts: unassigned });
    }

    return result;
  }, [accounts, clients]);

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
      oauthClientId ? { clientId: oauthClientId } : undefined,
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
        {clients.length > 0 && (
          <select
            value={oauthClientId}
            onChange={(e) => setOauthClientId(e.target.value)}
            className="h-8 rounded-md border border-input bg-background px-2.5 text-xs"
            aria-label="Atribuir a cliente ao conectar"
          >
            <option value="">Sem cliente</option>
            {clients.map((c) => (
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

      {/* Detail modal */}
      <IntegrationCardModal
        account={modalAccount ? toLibAccount(modalAccount) : null}
        onClose={() => setModalAccount(null)}
      />
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function Conexoes() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [manageClientsOpen, setManageClientsOpen] = useState(false);

  const { data: clients = [], isLoading: clientsLoading } = useClients();

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
          Gerenciar clientes
          {clients.length > 0 && (
            <span className="ml-1.5 rounded-full bg-muted px-1.5 py-0.5 text-[10px]">
              {clients.length}
            </span>
          )}
        </Button>
      </div>

      {/* WhatsApp section */}
      <section className="space-y-4">
        <div className="flex items-center gap-2">
          <Smartphone className="h-5 w-5 text-muted-foreground" />
          <h2 className="text-lg font-semibold">WhatsApp</h2>
        </div>
        <WhatsAppConnections />
      </section>

      <Separator />

      {/* YouTube card section */}
      <section className="space-y-4">
        <YouTubeCardSection clients={clients} />
      </section>

      {/* Client management modal */}
      {manageClientsOpen && (
        <ClientManagementModal
          clients={clients}
          onClose={() => setManageClientsOpen(false)}
        />
      )}
    </div>
  );
}
