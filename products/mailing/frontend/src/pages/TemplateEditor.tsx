import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useTemplate, useCreateTemplate, useUpdateTemplate, usePreviewTemplate, Template } from "@/hooks/useTemplates";
import { toast } from "sonner";
import { Loader2, ArrowLeft, Save, Eye, AlertCircle } from "lucide-react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface TemplateForm {
  nome: string;
  assunto: string;
  categoria: Template["categoria"];
  corpo_html: string;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const EMPTY_FORM: TemplateForm = {
  nome: "",
  assunto: "",
  categoria: "marketing",
  corpo_html: "",
};

const CATEGORIAS: { value: Template["categoria"]; label: string }[] = [
  { value: "marketing", label: "Marketing" },
  { value: "transactional", label: "Transacional" },
  { value: "follow_up", label: "Follow-up" },
  { value: "newsletter", label: "Newsletter" },
];

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function TemplateEditor() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const isEditing = !!id;

  // Fetch existing template for editing
  const { data: templateRes, isLoading: loadingTemplate, isError } = useTemplate(id ?? "");
  const createMutation = useCreateTemplate();
  const updateMutation = useUpdateTemplate();
  const previewMutation = usePreviewTemplate();

  const [form, setForm] = useState<TemplateForm>(EMPTY_FORM);
  const [showPreview, setShowPreview] = useState(false);
  const [previewHtml, setPreviewHtml] = useState("");
  const [initialized, setInitialized] = useState(false);

  // Load template data into form when editing
  useEffect(() => {
    if (isEditing && templateRes?.data && !initialized) {
      const t = templateRes.data as Template;
      setForm({
        nome: t.nome,
        assunto: t.assunto,
        categoria: t.categoria,
        corpo_html: t.corpo_html,
      });
      setInitialized(true);
    }
  }, [isEditing, templateRes, initialized]);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!form.nome.trim() || !form.assunto.trim()) return;

    const payload: Partial<Template> = {
      nome: form.nome.trim(),
      assunto: form.assunto.trim(),
      categoria: form.categoria,
      corpo_html: form.corpo_html,
    };

    if (isEditing) {
      updateMutation.mutate({ id: id!, ...payload }, {
        onSuccess: () => {
          toast.success("Template atualizado");
          navigate("/templates");
        },
        onError: (err: any) => toast.error("Erro ao atualizar template", { description: err?.message }),
      });
    } else {
      createMutation.mutate(payload, {
        onSuccess: () => {
          toast.success("Template criado com sucesso");
          navigate("/templates");
        },
        onError: (err: any) => toast.error("Erro ao criar template", { description: err?.message }),
      });
    }
  }

  function handlePreview() {
    if (isEditing && id) {
      previewMutation.mutate({ id, variaveis: {} }, {
        onSuccess: (data: any) => {
          setPreviewHtml(data?.data?.html ?? data?.html ?? form.corpo_html);
          setShowPreview(true);
        },
        onError: () => {
          // Fallback: show raw HTML
          setPreviewHtml(form.corpo_html);
          setShowPreview(true);
        },
      });
    } else {
      // For new templates, just show the raw HTML
      setPreviewHtml(form.corpo_html);
      setShowPreview(true);
    }
  }

  const saving = createMutation.isPending || updateMutation.isPending;

  if (isEditing && loadingTemplate) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-3">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
        <p className="text-sm text-muted-foreground">Carregando template...</p>
      </div>
    );
  }

  if (isEditing && isError) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-3">
        <AlertCircle className="h-8 w-8 text-destructive" />
        <p className="text-sm text-muted-foreground">Template nao encontrado.</p>
        <button onClick={() => navigate("/templates")} className="text-sm text-primary hover:underline">
          Voltar para templates
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <button
          onClick={() => navigate("/templates")}
          className="rounded-md p-1.5 text-muted-foreground hover:bg-muted transition-colors"
        >
          <ArrowLeft className="h-5 w-5" />
        </button>
        <div>
          <h1 className="text-2xl font-bold text-foreground">
            {isEditing ? "Editar Template" : "Novo Template"}
          </h1>
          <p className="text-sm text-muted-foreground">
            {isEditing ? "Edite o conteudo do seu template de e-mail." : "Crie um novo template de e-mail."}
          </p>
        </div>
      </div>

      {/* Form + Preview Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-5">
          <div>
            <label className="mb-1 block text-sm font-medium text-foreground">Nome do Template *</label>
            <input
              type="text"
              required
              value={form.nome}
              onChange={(e) => setForm({ ...form, nome: e.target.value })}
              placeholder="Ex: Newsletter Mensal"
              className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-foreground">Assunto *</label>
            <input
              type="text"
              required
              value={form.assunto}
              onChange={(e) => setForm({ ...form, assunto: e.target.value })}
              placeholder="Ex: Novidades de abril - {{empresa}}"
              className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-foreground">Categoria</label>
            <select
              value={form.categoria}
              onChange={(e) => setForm({ ...form, categoria: e.target.value as Template["categoria"] })}
              className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              {CATEGORIAS.map((c) => (
                <option key={c.value} value={c.value}>{c.label}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-foreground">Corpo HTML</label>
            <textarea
              rows={16}
              value={form.corpo_html}
              onChange={(e) => setForm({ ...form, corpo_html: e.target.value })}
              placeholder={"<html>\n  <body>\n    <h1>Ola {{nome}},</h1>\n    <p>Conteudo do e-mail aqui...</p>\n  </body>\n</html>"}
              className="flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground font-mono placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring resize-y"
            />
            <p className="mt-1 text-xs text-muted-foreground">
              Use variaveis como {"{{nome}}"}, {"{{empresa}}"}, {"{{email}}"} para personalizacao.
            </p>
          </div>

          <div className="flex gap-3 pt-2">
            <button
              type="submit"
              disabled={saving || !form.nome.trim() || !form.assunto.trim()}
              className="inline-flex items-center gap-2 rounded-md bg-primary px-6 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors disabled:cursor-not-allowed disabled:opacity-50"
            >
              {saving ? (
                <><Loader2 className="h-4 w-4 animate-spin" />Salvando...</>
              ) : (
                <><Save className="h-4 w-4" />{isEditing ? "Salvar alteracoes" : "Criar Template"}</>
              )}
            </button>
            <button
              type="button"
              onClick={handlePreview}
              disabled={!form.corpo_html.trim() || previewMutation.isPending}
              className="inline-flex items-center gap-2 rounded-md border border-input bg-background px-6 py-2.5 text-sm font-medium hover:bg-muted transition-colors disabled:cursor-not-allowed disabled:opacity-50"
            >
              {previewMutation.isPending ? (
                <><Loader2 className="h-4 w-4 animate-spin" />Carregando...</>
              ) : (
                <><Eye className="h-4 w-4" />Pre-visualizar</>
              )}
            </button>
          </div>
        </form>

        {/* Preview Panel */}
        <div className="rounded-lg border border-border bg-card">
          <div className="border-b border-border px-4 py-3">
            <h2 className="text-sm font-medium text-foreground">Pre-visualizacao</h2>
          </div>
          <div className="p-4">
            {showPreview && previewHtml ? (
              <div className="rounded-md border border-border bg-white p-4 min-h-[300px]">
                <iframe
                  srcDoc={previewHtml}
                  title="Template Preview"
                  className="w-full min-h-[400px] border-0"
                  sandbox="allow-same-origin"
                />
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center py-16 text-center">
                <Eye className="h-8 w-8 mb-3 text-muted-foreground" />
                <p className="text-sm text-muted-foreground">
                  Clique em "Pre-visualizar" para ver o resultado do template.
                </p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
