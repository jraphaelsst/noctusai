import { Link } from "react-router-dom";
import { toast } from "sonner";
import { useAutomations, useDeleteAutomation, Automation } from "@/hooks/useAutomations";
import { Loader2, AlertCircle, Workflow, Plus, Trash2 } from "lucide-react";

const STATUS_BADGE: Record<Automation["status"], { label: string; cls: string }> = {
  rascunho: { label: "Rascunho", cls: "bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-300" },
  ativa: { label: "Ativa", cls: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300" },
  pausada: { label: "Pausada", cls: "bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-300" },
};

const TRIGGER_LABEL: Record<string, string> = {
  contact_added: "Contato adicionado",
  tag_added: "Tag adicionada",
  list_joined: "Entrou em lista",
  manual: "Manual",
  webhook: "Webhook",
};

function fmtDate(iso: string) {
  return new Date(iso).toLocaleDateString("pt-BR", { day: "2-digit", month: "short", year: "numeric" });
}

export default function Automations() {
  const { data, isLoading, isError } = useAutomations();
  const deleteMut = useDeleteAutomation();
  const automations: Automation[] = data?.data ?? [];

  function handleDelete(id: string) {
    if (!confirm("Tem certeza que deseja excluir esta automacao?")) return;
    deleteMut.mutate(id, {
      onSuccess: () => toast.success("Automacao excluida."),
      onError: () => toast.error("Erro ao excluir automacao."),
    });
  }

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-3">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
        <p className="text-sm text-muted-foreground">Carregando automacoes...</p>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-3">
        <AlertCircle className="h-8 w-8 text-destructive" />
        <p className="text-sm text-muted-foreground">Erro ao carregar automacoes. Tente novamente.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Automacoes</h1>
          <p className="text-sm text-muted-foreground">
            Configure fluxos automaticos de e-mail baseados em gatilhos e acoes.
          </p>
        </div>
        <Link
          to="/automations/new"
          className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
        >
          <Plus className="h-4 w-4" />
          Nova Automacao
        </Link>
      </div>

      {/* Automations Table */}
      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-border bg-muted/50">
            <tr>
              <th className="px-4 py-3 font-medium text-muted-foreground">Nome</th>
              <th className="px-4 py-3 font-medium text-muted-foreground">Gatilho</th>
              <th className="px-4 py-3 font-medium text-muted-foreground">Status</th>
              <th className="px-4 py-3 font-medium text-muted-foreground hidden md:table-cell">Criada em</th>
              <th className="px-4 py-3 font-medium text-muted-foreground">Acoes</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {automations.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-4 py-12 text-center">
                  <Workflow className="mx-auto h-8 w-8 text-muted-foreground/50" />
                  <p className="mt-2 text-sm text-muted-foreground">Nenhuma automacao configurada.</p>
                  <p className="text-xs text-muted-foreground mt-1">
                    Crie automacoes para enviar e-mails automaticamente com base em gatilhos.
                  </p>
                </td>
              </tr>
            ) : (
              automations.map((a) => {
                const badge = STATUS_BADGE[a.status];
                return (
                  <tr key={a.id} className="hover:bg-muted/30 transition-colors">
                    <td className="px-4 py-3">
                      <Link to={`/automations/${a.id}`} className="font-medium text-foreground hover:text-primary transition-colors">
                        {a.nome}
                      </Link>
                    </td>
                    <td className="px-4 py-3">
                      <span className="inline-flex rounded-full bg-primary/10 px-2.5 py-0.5 text-xs font-medium text-primary">
                        {TRIGGER_LABEL[a.trigger_type] ?? a.trigger_type}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${badge.cls}`}>
                        {badge.label}
                      </span>
                    </td>
                    <td className="px-4 py-3 hidden md:table-cell text-muted-foreground">
                      {fmtDate(a.created_at)}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <Link to={`/automations/${a.id}`} className="text-sm text-primary hover:underline">
                          Ver
                        </Link>
                        {a.status === "rascunho" && (
                          <button
                            onClick={() => handleDelete(a.id)}
                            disabled={deleteMut.isPending}
                            className="text-destructive hover:text-destructive/80 transition-colors disabled:opacity-50"
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                        )}
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
  );
}
