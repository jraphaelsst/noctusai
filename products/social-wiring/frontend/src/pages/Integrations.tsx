/**
 * Integrations page — multi-account credential management with per-client
 * grouping.
 *
 * Lists all non-WAHA providers (YouTube, Meta, n8n, Google Drive, Gmail).
 * Each provider section uses the seed `ClientCredentialPanel` organ which
 * adds client-tab filtering + full CRUD affordances to the existing
 * `IntegrationCard` cells.
 *
 * WAHA is explicitly excluded — use the Conexao page for WhatsApp connections.
 *
 * NOTE: `ProviderSection` is exported so Conexoes.tsx can re-use it.
 *
 * Canonical import rule: UI organs come from `@noctusai/lib/design-system`.
 * No per-product re-implementation of the credential card or client panel.
 */
import { useState } from "react";
import { Loader2, Plug } from "lucide-react";
import { toast } from "sonner";

import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
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

import AddAccountModal from "@/components/AddAccountModal";
import {
  useIntegrationProviders,
  useIntegrationAccounts,
  useUpdateAccount,
  useSetDefaultAccount,
  useDeleteAccount,
  useSyncAccount,
  type IntegrationAccount,
  type IntegrationProvider,
} from "@/hooks/useIntegrationAccounts";
import { useClients } from "@/hooks/useClients";

// Seed organs — canonical per-client credential CRUD panel + detail modal.
import {
  ClientCredentialPanel,
  IntegrationCardModal as CredentialModal,
} from "@noctusai/lib/design-system";
import type { IntegrationAccount as SeedAccount } from "@noctusai/lib/design-system";

// ─── ProviderSection ──────────────────────────────────────────────────────────

export interface ProviderSectionProps {
  providerConfig: IntegrationProvider;
}

export function ProviderSection({ providerConfig }: ProviderSectionProps) {
  const provider = providerConfig.id;

  const { data: accounts = [], isLoading: accountsLoading, isError: accountsError } =
    useIntegrationAccounts(provider);
  const { data: clients = [], isLoading: clientsLoading } = useClients();

  const updateMutation = useUpdateAccount();
  const setDefaultMutation = useSetDefaultAccount();
  const deleteMutation = useDeleteAccount();
  const syncMutation = useSyncAccount();

  const [addOpen, setAddOpen] = useState(false);
  const [addClientId, setAddClientId] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<IntegrationAccount | null>(null);
  const [modalAccount, setModalAccount] = useState<SeedAccount | null>(null);
  const [busyAccountId, setBusyAccountId] = useState<string | null>(null);

  // ── Handlers ───────────────────────────────────────────────────────────

  function handleAdd(clientId: string | null) {
    setAddClientId(clientId);
    setAddOpen(true);
  }

  async function handleSave(account: IntegrationAccount, patch: Record<string, string | null>) {
    setBusyAccountId(account.id);
    try {
      await updateMutation.mutateAsync({
        id: account.id,
        account_label: patch.account_label ?? undefined,
      });
      toast.success("Conta atualizada");
    } catch (err: any) {
      toast.error("Erro ao salvar conta", {
        description: err?.message ?? "Tente novamente",
      });
    } finally {
      setBusyAccountId(null);
    }
  }

  async function handleSetDefault(account: IntegrationAccount) {
    setBusyAccountId(account.id);
    try {
      await setDefaultMutation.mutateAsync(account.id);
      toast.success("Conta padrão atualizada");
    } catch (err: any) {
      toast.error("Erro ao definir conta padrão", {
        description: err?.message ?? "Tente novamente",
      });
    } finally {
      setBusyAccountId(null);
    }
  }

  async function handleSync(account: IntegrationAccount) {
    setBusyAccountId(account.id);
    try {
      await syncMutation.mutateAsync(account.id);
      toast.success("Conta sincronizada");
    } catch (err: any) {
      toast.error("Erro ao sincronizar conta", {
        description: err?.message ?? "Tente novamente",
      });
    } finally {
      setBusyAccountId(null);
    }
  }

  async function handleDelete() {
    if (!confirmDelete) return;
    try {
      await deleteMutation.mutateAsync(confirmDelete.id);
      toast.success("Conta removida");
      setConfirmDelete(null);
    } catch (err: any) {
      toast.error("Erro ao remover conta", {
        description: err?.message ?? "Tente novamente",
      });
    }
  }

  const isLoading = accountsLoading || clientsLoading;

  // Map product IntegrationAccount[] to the seed SeedAccount[] shape (same
  // field names — cast is safe; both types mirror the same BE contract).
  const seedAccounts = accounts as unknown as SeedAccount[];
  const seedClients = clients.map((c) => ({
    id: c.id,
    name: c.name,
    slug: c.slug,
  }));

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{providerConfig.display_name}</CardTitle>
      </CardHeader>

      <CardContent>
        <ClientCredentialPanel
          accounts={seedAccounts}
          clients={seedClients}
          provider={provider}
          isLoading={isLoading}
          error={accountsError ? new Error("Erro ao carregar contas") : null}
          busyAccountId={busyAccountId}
          onAdd={handleAdd}
          onSave={handleSave as any}
          onDelete={(acc) => setConfirmDelete(acc as unknown as IntegrationAccount)}
          onSetDefault={handleSetDefault as any}
          onSync={handleSync as any}
          onOpenModal={(acc) => setModalAccount(acc)}
        />
      </CardContent>

      {/* Add account modal */}
      {addOpen && (
        <AddAccountModal
          provider={provider}
          providerConfig={providerConfig}
          clientId={addClientId}
          onClose={() => {
            setAddOpen(false);
            setAddClientId(null);
          }}
        />
      )}

      {/* Detail modal */}
      <CredentialModal
        account={modalAccount}
        onClose={() => setModalAccount(null)}
      />

      {/* Delete confirm */}
      <AlertDialog
        open={!!confirmDelete}
        onOpenChange={(open) => !open && setConfirmDelete(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Remover conta?</AlertDialogTitle>
            <AlertDialogDescription>
              A conta &ldquo;{confirmDelete?.account_label}&rdquo; sera
              removida permanentemente. Videos e publicacoes existentes nao
              serao afetados.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete}>Remover</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function Integrations() {
  const { data: providers = [], isLoading, isError } = useIntegrationProviders();

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-3">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
        <p className="text-sm text-muted-foreground">Carregando integracoes...</p>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-3">
        <p className="text-sm text-destructive">
          Erro ao carregar provedores. Tente recarregar a pagina.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Plug className="h-6 w-6 text-primary" />
        <div>
          <h1 className="text-2xl font-bold text-foreground">Integracoes</h1>
          <p className="text-sm text-muted-foreground">
            Gerencie as contas dos seus provedores (YouTube, Meta, n8n, Google
            Drive, Gmail). Use as abas para filtrar por cliente. Para conexoes
            WhatsApp, use a pagina Conexao.
          </p>
        </div>
      </div>

      {/* Provider sections */}
      {providers.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center gap-2 py-12 text-center text-sm text-muted-foreground">
            <Plug className="h-8 w-8" />
            Nenhum provedor disponivel no momento.
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {providers.map((p) => (
            <ProviderSection key={p.id} providerConfig={p} />
          ))}
        </div>
      )}
    </div>
  );
}
