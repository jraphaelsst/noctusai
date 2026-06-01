/**
 * Integrations page — multi-account credential management.
 *
 * Lists all non-WAHA providers (YouTube, Meta, n8n, Google Drive, Gmail).
 * Groups accounts by provider. Each provider section shows:
 *   · Header: display name + "Add account" button
 *   · Account rows: label, metadata snippet, default badge, set-default + delete
 *   · Empty state per provider
 *
 * WAHA is explicitly excluded — use the Conexao page for WhatsApp connections.
 *
 * NOTE: `ProviderSection` is exported so Conexoes.tsx can re-use it.
 */
import { useState } from "react";
import { Loader2, Plus, Star, StarOff, Trash2, Plug } from "lucide-react";
import { toast } from "sonner";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
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
  useSetDefaultAccount,
  useDeleteAccount,
  type IntegrationAccount,
  type IntegrationProvider,
} from "@/hooks/useIntegrationAccounts";

// ─── Account row ─────────────────────────────────────────────────────────────

function metadataSnippet(metadata: Record<string, unknown>): string {
  const entries = Object.entries(metadata)
    .filter(([, v]) => typeof v === "string" || typeof v === "number")
    .slice(0, 2);
  return entries.map(([k, v]) => `${k}: ${v}`).join(" · ");
}

function AccountRow({
  account,
  onDelete,
  onSetDefault,
}: {
  account: IntegrationAccount;
  onDelete: (acc: IntegrationAccount) => void;
  onSetDefault: (id: string) => void;
}) {
  const snippet = metadataSnippet(account.metadata ?? {});

  return (
    <div className="flex items-center justify-between gap-4 border-b py-3 last:border-0">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 text-sm font-medium">
          {account.account_label}
          {account.is_default && (
            <Badge variant="default" className="gap-1 text-[10px]">
              <Star className="h-2.5 w-2.5" />
              Padrao
            </Badge>
          )}
        </div>
        {snippet && (
          <p className="truncate text-xs text-muted-foreground">{snippet}</p>
        )}
      </div>
      <div className="flex items-center gap-1">
        {!account.is_default && (
          <Button
            variant="ghost"
            size="icon"
            title="Definir como padrao"
            onClick={() => onSetDefault(account.id)}
          >
            <StarOff className="h-4 w-4 text-muted-foreground" />
          </Button>
        )}
        <Button
          variant="ghost"
          size="icon"
          title="Remover conta"
          onClick={() => onDelete(account)}
        >
          <Trash2 className="h-4 w-4 text-muted-foreground hover:text-destructive" />
        </Button>
      </div>
    </div>
  );
}

// ─── Provider section ─────────────────────────────────────────────────────────

export function ProviderSection({ providerConfig }: { providerConfig: IntegrationProvider }) {
  // providerConfig.id is the canonical identifier (not .name)
  const { data: accounts = [], isLoading } = useIntegrationAccounts(providerConfig.id);
  const setDefault = useSetDefaultAccount();
  const deleteMutation = useDeleteAccount();

  const [addOpen, setAddOpen] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<IntegrationAccount | null>(null);

  async function handleSetDefault(id: string) {
    try {
      await setDefault.mutateAsync(id);
      toast.success("Conta padrao atualizada");
    } catch (err: any) {
      toast.error("Erro ao definir conta padrao", {
        description: err?.message ?? "Tente novamente",
      });
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

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="text-base">{providerConfig.display_name}</CardTitle>
          <Button size="sm" variant="outline" onClick={() => setAddOpen(true)}>
            <Plus className="mr-1.5 h-3.5 w-3.5" />
            Adicionar conta
          </Button>
        </div>
        {accounts.length > 0 && (
          <CardDescription>
            {accounts.length} conta{accounts.length !== 1 ? "s" : ""} configurada{accounts.length !== 1 ? "s" : ""}
          </CardDescription>
        )}
      </CardHeader>

      <CardContent>
        {isLoading ? (
          <div className="flex items-center gap-2 py-4 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            Carregando...
          </div>
        ) : accounts.length === 0 ? (
          <div className="rounded-md border border-dashed bg-muted/20 py-6 text-center text-sm text-muted-foreground">
            Nenhuma conta ainda. Adicione a primeira.
          </div>
        ) : (
          <div>
            {accounts.map((acc) => (
              <AccountRow
                key={acc.id}
                account={acc}
                onDelete={setConfirmDelete}
                onSetDefault={handleSetDefault}
              />
            ))}
          </div>
        )}
      </CardContent>

      {/* Add modal — passes providerConfig.id as the provider identifier */}
      {addOpen && (
        <AddAccountModal
          provider={providerConfig.id}
          providerConfig={providerConfig}
          onClose={() => setAddOpen(false)}
        />
      )}

      {/* Delete confirm */}
      <AlertDialog
        open={!!confirmDelete}
        onOpenChange={(open) => !open && setConfirmDelete(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Remover conta?</AlertDialogTitle>
            <AlertDialogDescription>
              A conta &ldquo;{confirmDelete?.account_label}&rdquo; sera removida permanentemente.
              Videos e publicacoes existentes nao serao afetados.
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
            Gerencie as contas dos seus provedores (YouTube, Meta, n8n, Google Drive, Gmail).
            Para conexoes WhatsApp, use a pagina Conexao.
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
