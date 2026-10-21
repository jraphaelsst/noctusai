/**
 * Clientes -- client list with create / edit (ClientForm), soft delete (admin, confirm, 409 shown inline) and inactivation with kept charges (ClientOffboardingDialog).
 *
 * The list is the canonical ResourceManager (page-scoped CRUD organ) wired to /api/clients with create/edit turned off:
 * the form is Orbity's own `ClientForm` because it needs what the organ's form cannot do (Razão Social required, nome
 * fantasia optional, the "Buscar CNPJ" prefill). "Inativar" never flips a flag: it opens the dialog that decides every
 * open charge (cancel or keep) and ends the client's contracts -- one admin-only server operation.
 *
 * Nav key: "clientes".
 */
import { useState } from "react";
import { Archive, Pencil, RotateCcw, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { ResourceManager, useConfirm } from "@noctusai/lib/components";
import { Button, useIsOrgAdmin } from "@noctusai/lib/design-system";
import { ClientForm, EMPTY_CLIENT, valuesOf, type ClientFormValues, type ClientRowLike } from "@/components/ClientForm";
import { ClientOffboardingDialog } from "@/components/ClientOffboardingDialog";
import { api } from "@/lib/api";
import { useQueryClient } from "@tanstack/react-query";

interface ClientRow extends ClientRowLike {
  org_id: string;
  active: boolean;
  created_at: string;
  updated_at: string;
}

function formatCurrency(value: number | null): string {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(value);
}

function formatDate(value: string): string {
  if (!value) return "—";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? value : d.toLocaleDateString("pt-BR");
}

async function reactivateClient(id: string, reload: () => void) {
  try {
    await api.patch(`/api/clients/${id}`, { active: true });
    toast.success("Cliente reativado");
    reload();
  } catch (err: unknown) {
    toast.error("Falha ao reativar cliente", { description: err instanceof Error ? err.message : undefined });
  }
}

/** The server's pt-BR reason (`{detail}` of a 409 etc.), not the transport `[409] ...` wrapper. */
function serverReason(err: unknown): string {
  const body = (err as { body?: { detail?: unknown } } | null)?.body;
  if (typeof body?.detail === "string") return body.detail;
  return err instanceof Error ? err.message : "Falha ao excluir cliente";
}

export default function Clientes() {
  const isAdmin = useIsOrgAdmin();
  const confirm = useConfirm();
  const queryClient = useQueryClient();
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [showArchived, setShowArchived] = useState(false);
  const [editing, setEditing] = useState<ClientFormValues | null>(null);
  const [offboarding, setOffboarding] = useState<string | null>(null);
  // Remounting the list is how a save made outside the organ's own form refreshes it.
  const [refreshKey, setRefreshKey] = useState(0);
  const refresh = () => setRefreshKey((k) => k + 1);

  async function deleteClient(row: ClientRow) {
    setDeleteError(null);
    const ok = await confirm({
      title: `Excluir ${row.legal_name || row.name}?`,
      description: "O cliente deixa de aparecer em listas e seletores. Contratos e cobranças já encerrados continuam no histórico.",
      confirmLabel: "Excluir cliente",
      tone: "danger",
    });
    if (!ok) return;
    try {
      await api.delete(`/api/clients/${row.id}`);
      toast.success("Cliente excluído");
      queryClient.invalidateQueries({ queryKey: ["orbity-client-options"] });
      queryClient.invalidateQueries({ queryKey: ["orbity-dashboard-clients"] });
      refresh();
    } catch (err: unknown) {
      setDeleteError(serverReason(err));
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <label className="inline-flex items-center gap-2 text-sm text-muted-foreground">
          <input type="checkbox" checked={showArchived} onChange={(e) => setShowArchived(e.target.checked)} />
          Mostrar inativos
        </label>
        <Button onClick={() => setEditing(EMPTY_CLIENT)}>Novo cliente</Button>
      </div>

      {deleteError ? (
        <div role="alert" className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
          {deleteError}
        </div>
      ) : null}

      <ResourceManager<ClientRow>
        key={`${refreshKey}-${showArchived}`}
        title="Clientes"
        description="Gerencie os clientes da agência"
        api={api}
        apiPath={showArchived ? "/api/clients?active_only=false" : "/api/clients"}
        singularName="Cliente"
        canCreate={false}
        canEdit={false}
        canDelete={false}
        emptyMessage="Nenhum cliente cadastrado ainda."
        fields={[]}
        rowActions={(row, reload) => (
          <span className="inline-flex gap-1">
            <button
              type="button"
              onClick={() => setEditing(valuesOf(row))}
              title="Editar"
              className="inline-flex items-center gap-1 rounded px-2 py-1 text-xs text-gray-500 hover:bg-gray-50 hover:text-foreground transition-colors"
            >
              <Pencil className="h-3.5 w-3.5" />
              Editar
            </button>
            {isAdmin ? (
              <button
                type="button"
                onClick={() => void deleteClient(row)}
                title="Excluir cliente"
                className="inline-flex items-center gap-1 rounded px-2 py-1 text-xs text-gray-500 hover:bg-red-50 hover:text-red-600 transition-colors"
              >
                <Trash2 className="h-3.5 w-3.5" />
                Excluir cliente
              </button>
            ) : null}
            {row.active ? (
              isAdmin ? (
                <button
                  type="button"
                  onClick={() => setOffboarding(row.id)}
                  title="Inativar"
                  className="inline-flex items-center gap-1 rounded px-2 py-1 text-xs text-gray-500 hover:bg-amber-50 hover:text-amber-600 transition-colors"
                >
                  <Archive className="h-3.5 w-3.5" />
                  Inativar
                </button>
              ) : null
            ) : (
              <button
                type="button"
                onClick={() => void reactivateClient(row.id, reload)}
                title="Reativar"
                className="inline-flex items-center gap-1 rounded px-2 py-1 text-xs text-gray-500 hover:bg-green-50 hover:text-green-700 transition-colors"
              >
                <RotateCcw className="h-3.5 w-3.5" />
                Reativar
              </button>
            )}
          </span>
        )}
        columns={[
          { key: "legal_name", header: "Razão Social", render: (row) => row.legal_name || row.name },
          { key: "name", header: "Nome fantasia", render: (row) => (row.legal_name && row.name !== row.legal_name ? row.name : "—") },
          { key: "document", header: "CPF/CNPJ", render: (row) => row.document ?? "—" },
          { key: "email", header: "E-mail", render: (row) => row.email ?? "—" },
          { key: "phone", header: "Telefone", render: (row) => row.phone ?? "—" },
          { key: "monthly_value", header: "Valor Mensal", render: (row) => formatCurrency(row.monthly_value) },
          {
            key: "active",
            header: "Status",
            render: (row) =>
              row.active ? (
                <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-green-100 text-green-800">Ativo</span>
              ) : (
                <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-600">Inativo</span>
              ),
          },
          { key: "created_at", header: "Criado em", render: (row) => formatDate(row.created_at) },
        ]}
      />

      {editing ? (
        <ClientForm
          key={editing.id ?? "new"}
          open
          initial={editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            refresh();
          }}
        />
      ) : null}

      {offboarding ? (
        <ClientOffboardingDialog
          key={offboarding}
          clientId={offboarding}
          open
          onClose={() => setOffboarding(null)}
          onDone={() => {
            setOffboarding(null);
            refresh();
          }}
        />
      ) : null}
    </div>
  );
}
