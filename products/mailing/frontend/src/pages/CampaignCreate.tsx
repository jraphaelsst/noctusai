import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { toast } from "sonner";
import { useCreateCampaign } from "@/hooks/useCampaigns";
import { useTemplates, Template } from "@/hooks/useTemplates";
import { useLists, ContactList } from "@/hooks/useLists";
import { Loader2 } from "lucide-react";

export default function CampaignCreate() {
  const navigate = useNavigate();
  const createCampaign = useCreateCampaign();

  const { data: templatesData, isLoading: loadingTemplates } = useTemplates();
  const { data: listsData, isLoading: loadingLists } = useLists();

  const templates: Template[] = templatesData?.data ?? [];
  const lists: ContactList[] = listsData?.data ?? [];

  const [nome, setNome] = useState("");
  const [templateId, setTemplateId] = useState("");
  const [listId, setListId] = useState("");
  const [assuntoOverride, setAssuntoOverride] = useState("");
  const [remetenteNome, setRemetenteNome] = useState("");
  const [remetenteEmail, setRemetenteEmail] = useState("");

  const canSubmit = nome.trim() && templateId && listId && !createCampaign.isPending;

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;

    createCampaign.mutate(
      {
        nome: nome.trim(),
        template_id: templateId,
        list_id: listId,
        ...(assuntoOverride.trim() && { assunto_override: assuntoOverride.trim() }),
        ...(remetenteNome.trim() && { remetente_nome: remetenteNome.trim() }),
        ...(remetenteEmail.trim() && { remetente_email: remetenteEmail.trim() }),
      },
      {
        onSuccess: (res: any) => {
          toast.success("Campanha criada com sucesso!");
          const id = res?.data?.id;
          navigate(id ? `/campaigns/${id}` : "/campaigns");
        },
        onError: () => toast.error("Erro ao criar campanha. Tente novamente."),
      }
    );
  }

  const inputCls =
    "flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-foreground">Nova Campanha</h1>
        <p className="text-sm text-muted-foreground">
          Configure os detalhes da campanha, escolha o template e a lista de destinatarios.
        </p>
      </div>

      {/* Form */}
      <form onSubmit={handleSubmit} className="space-y-5 max-w-2xl">
        <div>
          <label className="mb-1 block text-sm font-medium text-foreground">Nome da Campanha *</label>
          <input
            type="text"
            placeholder="Ex: Newsletter Abril 2026"
            className={inputCls}
            value={nome}
            onChange={(e) => setNome(e.target.value)}
          />
        </div>

        <div>
          <label className="mb-1 block text-sm font-medium text-foreground">Template *</label>
          <select className={inputCls} value={templateId} onChange={(e) => setTemplateId(e.target.value)}>
            <option value="">
              {loadingTemplates ? "Carregando templates..." : "Selecione um template"}
            </option>
            {templates.map((t) => (
              <option key={t.id} value={t.id}>
                {t.nome} ({t.categoria})
              </option>
            ))}
          </select>
          <p className="mt-1 text-xs text-muted-foreground">
            Escolha um template previamente criado para usar nesta campanha.
          </p>
        </div>

        <div>
          <label className="mb-1 block text-sm font-medium text-foreground">Lista de Destinatarios *</label>
          <select className={inputCls} value={listId} onChange={(e) => setListId(e.target.value)}>
            <option value="">
              {loadingLists ? "Carregando listas..." : "Selecione uma lista"}
            </option>
            {lists.map((l) => (
              <option key={l.id} value={l.id}>
                {l.nome} ({l.contact_count} contatos)
              </option>
            ))}
          </select>
          <p className="mt-1 text-xs text-muted-foreground">
            A campanha sera enviada para todos os contatos ativos da lista selecionada.
          </p>
        </div>

        {/* Optional fields */}
        <div>
          <label className="mb-1 block text-sm font-medium text-foreground">Assunto (override)</label>
          <input
            type="text"
            placeholder="Deixe vazio para usar o assunto do template"
            className={inputCls}
            value={assuntoOverride}
            onChange={(e) => setAssuntoOverride(e.target.value)}
          />
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="mb-1 block text-sm font-medium text-foreground">Nome do Remetente</label>
            <input
              type="text"
              placeholder="Ex: Equipe NoctusAI"
              className={inputCls}
              value={remetenteNome}
              onChange={(e) => setRemetenteNome(e.target.value)}
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-foreground">E-mail do Remetente</label>
            <input
              type="email"
              placeholder="Ex: contato@seudominio.com"
              className={inputCls}
              value={remetenteEmail}
              onChange={(e) => setRemetenteEmail(e.target.value)}
            />
          </div>
        </div>

        <div className="flex gap-3 pt-2">
          <button
            type="submit"
            disabled={!canSubmit}
            className="inline-flex items-center gap-2 rounded-md bg-primary px-6 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50 disabled:pointer-events-none"
          >
            {createCampaign.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            Criar Campanha
          </button>
          <Link
            to="/campaigns"
            className="inline-flex items-center rounded-md border border-input bg-background px-6 py-2.5 text-sm font-medium hover:bg-muted transition-colors"
          >
            Cancelar
          </Link>
        </div>
      </form>
    </div>
  );
}
