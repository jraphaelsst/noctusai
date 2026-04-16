import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useTemplates, useDeleteTemplate, Template } from "@/hooks/useTemplates";
import { toast } from "sonner";
import { Plus, Trash2, Loader2, FileText, Pencil, AlertCircle } from "lucide-react";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const CATEGORIA_CONFIG: Record<string, { label: string; className: string }> = {
  marketing: { label: "Marketing", className: "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400" },
  transactional: { label: "Transacional", className: "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400" },
  follow_up: { label: "Follow-up", className: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400" },
  newsletter: { label: "Newsletter", className: "bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-400" },
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function Templates() {
  const navigate = useNavigate();
  const [confirmDelete, setConfirmDelete] = useState<Template | null>(null);

  const { data: templatesRes, isLoading, isError } = useTemplates();
  const deleteMutation = useDeleteTemplate();

  const templates: Template[] = templatesRes?.data ?? [];

  function handleDelete(template: Template) {
    deleteMutation.mutate(template.id, {
      onSuccess: () => {
        toast.success("Template removido");
        setConfirmDelete(null);
      },
      onError: (err: any) => toast.error("Erro ao remover template", { description: err?.message }),
    });
  }

  if (isError) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-3">
        <AlertCircle className="h-8 w-8 text-destructive" />
        <p className="text-sm text-muted-foreground">Erro ao carregar templates.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <FileText className="h-6 w-6 text-primary" />
          <div>
            <h1 className="text-2xl font-bold text-foreground">Templates</h1>
            <p className="text-sm text-muted-foreground">
              Crie e gerencie templates de e-mail reutilizaveis para suas campanhas.
            </p>
          </div>
        </div>
        <Link
          to="/templates/new"
          className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
        >
          <Plus className="h-4 w-4" />
          Novo Template
        </Link>
      </div>

      {/* Template Grid */}
      {isLoading ? (
        <div className="flex flex-col items-center justify-center py-20 gap-3">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
          <p className="text-sm text-muted-foreground">Carregando templates...</p>
        </div>
      ) : templates.length === 0 ? (
        <div className="col-span-full rounded-lg border border-dashed border-border bg-card p-12 text-center">
          <FileText className="h-10 w-10 mx-auto mb-3 text-muted-foreground" />
          <p className="text-sm text-muted-foreground">Nenhum template criado.</p>
          <p className="text-xs text-muted-foreground mt-1">
            Templates permitem padronizar o visual dos seus e-mails e agilizar a criacao de campanhas.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {templates.map((t) => {
            const cat = CATEGORIA_CONFIG[t.categoria] ?? CATEGORIA_CONFIG.marketing;
            return (
              <div
                key={t.id}
                className="rounded-lg border border-border bg-card p-5 space-y-3 hover:shadow-md hover:border-primary/30 transition-all"
              >
                <div className="flex items-start justify-between gap-2">
                  <h3 className="font-semibold text-foreground truncate">{t.nome}</h3>
                  <span className={`inline-flex shrink-0 rounded-full px-2.5 py-0.5 text-xs font-medium ${cat.className}`}>
                    {cat.label}
                  </span>
                </div>
                <p className="text-sm text-muted-foreground line-clamp-1">
                  Assunto: {t.assunto}
                </p>
                <div className="flex items-center justify-between">
                  <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${t.ativo ? "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400" : "bg-muted text-muted-foreground"}`}>
                    {t.ativo ? "Ativo" : "Inativo"}
                  </span>
                  <div className="flex items-center gap-1">
                    <button
                      className="rounded-md p-1.5 text-muted-foreground hover:bg-muted transition-colors"
                      onClick={() => navigate(`/templates/${t.id}/edit`)}
                      title="Editar"
                    >
                      <Pencil className="h-4 w-4" />
                    </button>
                    <button
                      className="rounded-md p-1.5 text-destructive hover:bg-destructive/10 transition-colors"
                      onClick={() => setConfirmDelete(t)}
                      title="Remover"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Delete Confirm */}
      {confirmDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={() => setConfirmDelete(null)}>
          <div
            className="w-full max-w-[calc(100vw-2rem)] sm:max-w-md rounded-lg border border-border bg-card p-6 shadow-lg"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="mb-2 text-lg font-semibold text-foreground">Remover template</h2>
            <p className="mb-6 text-sm text-muted-foreground">
              Tem certeza que deseja remover o template <strong className="text-foreground">{confirmDelete.nome}</strong>?
            </p>
            <div className="flex justify-end gap-3">
              <button
                className="rounded-md border border-border bg-background px-4 py-2 text-sm text-foreground hover:bg-muted transition-colors"
                onClick={() => setConfirmDelete(null)}
              >
                Cancelar
              </button>
              <button
                className="inline-flex items-center gap-2 rounded-md bg-destructive px-6 py-2 text-sm font-medium text-destructive-foreground hover:bg-destructive/90 transition-colors disabled:cursor-not-allowed disabled:opacity-50"
                disabled={deleteMutation.isPending}
                onClick={() => handleDelete(confirmDelete)}
              >
                {deleteMutation.isPending ? (
                  <><Loader2 className="h-4 w-4 animate-spin" />Removendo...</>
                ) : "Confirmar remocao"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
