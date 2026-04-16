import { useState } from "react";
import { toast } from "sonner";
import {
  useDomains,
  useAddDomain,
  useDeleteDomain,
  useVerifyDomain,
  SenderDomain,
} from "@/hooks/useSettings";
import { Loader2, AlertCircle, Globe, Plus, Trash2, RefreshCw } from "lucide-react";

const STATUS_BADGE: Record<SenderDomain["status"], { label: string; cls: string }> = {
  pending: { label: "Pendente", cls: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-300" },
  verified: { label: "Verificado", cls: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300" },
  failed: { label: "Falhou", cls: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-300" },
};

function fmtDate(iso?: string) {
  if (!iso) return "--";
  return new Date(iso).toLocaleDateString("pt-BR", { day: "2-digit", month: "short", year: "numeric" });
}

export default function Settings() {
  const { data, isLoading, isError } = useDomains();
  const addMut = useAddDomain();
  const deleteMut = useDeleteDomain();
  const verifyMut = useVerifyDomain();

  const domains: SenderDomain[] = data?.data ?? [];
  const [newDomain, setNewDomain] = useState("");
  const [showAdd, setShowAdd] = useState(false);

  function handleAdd() {
    const d = newDomain.trim();
    if (!d) return;
    addMut.mutate(d, {
      onSuccess: () => {
        toast.success("Dominio adicionado!");
        setNewDomain("");
        setShowAdd(false);
      },
      onError: () => toast.error("Erro ao adicionar dominio."),
    });
  }

  function handleVerify(id: string) {
    verifyMut.mutate(id, {
      onSuccess: (res: any) => {
        const status = res?.data?.status;
        if (status === "verified") toast.success("Dominio verificado com sucesso!");
        else toast.info("Verificacao em andamento. Status: " + (status ?? "pendente"));
      },
      onError: () => toast.error("Erro ao verificar dominio."),
    });
  }

  function handleDelete(id: string) {
    if (!confirm("Tem certeza que deseja remover este dominio?")) return;
    deleteMut.mutate(id, {
      onSuccess: () => toast.success("Dominio removido."),
      onError: () => toast.error("Erro ao remover dominio."),
    });
  }

  const inputCls =
    "flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-3">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
        <p className="text-sm text-muted-foreground">Carregando configuracoes...</p>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-3">
        <AlertCircle className="h-8 w-8 text-destructive" />
        <p className="text-sm text-muted-foreground">Erro ao carregar configuracoes. Tente novamente.</p>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-foreground">Configuracoes</h1>
        <p className="text-sm text-muted-foreground">
          Configure seu dominio de envio e verifique a autenticacao (SPF, DKIM, DMARC).
        </p>
      </div>

      {/* Domain Verification */}
      <div className="rounded-lg border border-border bg-card p-6 space-y-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="text-lg font-semibold text-foreground">Verificacao de Dominio</h2>
            <p className="text-sm text-muted-foreground">
              Verifique seu dominio para melhorar a entregabilidade dos e-mails.
            </p>
          </div>
          <button
            onClick={() => setShowAdd(!showAdd)}
            className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
          >
            <Plus className="h-4 w-4" />
            Adicionar Dominio
          </button>
        </div>

        {/* Add Domain Form */}
        {showAdd && (
          <div className="flex items-end gap-3 max-w-md">
            <div className="flex-1">
              <label className="mb-1 block text-sm font-medium text-foreground">Dominio</label>
              <input
                type="text"
                placeholder="Ex: seudominio.com"
                className={inputCls}
                value={newDomain}
                onChange={(e) => setNewDomain(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleAdd()}
              />
            </div>
            <button
              onClick={handleAdd}
              disabled={!newDomain.trim() || addMut.isPending}
              className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50"
            >
              {addMut.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
              Adicionar
            </button>
          </div>
        )}

        {/* Domains Table */}
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-border bg-muted/50">
              <tr>
                <th className="px-4 py-3 font-medium text-muted-foreground">Dominio</th>
                <th className="px-4 py-3 font-medium text-muted-foreground">Status</th>
                <th className="px-4 py-3 font-medium text-muted-foreground hidden md:table-cell">Verificado em</th>
                <th className="px-4 py-3 font-medium text-muted-foreground hidden md:table-cell">Adicionado em</th>
                <th className="px-4 py-3 font-medium text-muted-foreground">Acoes</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {domains.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-4 py-12 text-center">
                    <Globe className="mx-auto h-8 w-8 text-muted-foreground/50" />
                    <p className="mt-2 text-sm text-muted-foreground">Nenhum dominio verificado.</p>
                    <p className="text-xs text-muted-foreground mt-1">Adicione um dominio para comecar.</p>
                  </td>
                </tr>
              ) : (
                domains.map((d) => {
                  const badge = STATUS_BADGE[d.status];
                  return (
                    <tr key={d.id} className="hover:bg-muted/30 transition-colors">
                      <td className="px-4 py-3 font-medium text-foreground">{d.domain}</td>
                      <td className="px-4 py-3">
                        <span className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${badge.cls}`}>
                          {badge.label}
                        </span>
                      </td>
                      <td className="px-4 py-3 hidden md:table-cell text-muted-foreground">
                        {fmtDate(d.verified_at)}
                      </td>
                      <td className="px-4 py-3 hidden md:table-cell text-muted-foreground">
                        {fmtDate(d.created_at)}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => handleVerify(d.id)}
                            disabled={verifyMut.isPending}
                            className="inline-flex items-center gap-1 text-sm text-primary hover:text-primary/80 transition-colors disabled:opacity-50"
                            title="Verificar"
                          >
                            <RefreshCw className={`h-4 w-4 ${verifyMut.isPending ? "animate-spin" : ""}`} />
                          </button>
                          <button
                            onClick={() => handleDelete(d.id)}
                            disabled={deleteMut.isPending}
                            className="text-destructive hover:text-destructive/80 transition-colors disabled:opacity-50"
                            title="Remover"
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
