import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { toast } from "sonner";
import { useCreateAutomation } from "@/hooks/useAutomations";
import { Loader2 } from "lucide-react";

const TRIGGER_OPTIONS = [
  { value: "contact_added", label: "Contato adicionado" },
  { value: "tag_added", label: "Tag adicionada" },
  { value: "list_joined", label: "Entrou em lista" },
  { value: "manual", label: "Inscricao manual" },
  { value: "webhook", label: "Webhook" },
];

export default function AutomationCreate() {
  const navigate = useNavigate();
  const createMut = useCreateAutomation();

  const [nome, setNome] = useState("");
  const [descricao, setDescricao] = useState("");
  const [triggerType, setTriggerType] = useState("");

  const canSubmit = nome.trim() && triggerType && !createMut.isPending;

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;

    createMut.mutate(
      {
        nome: nome.trim(),
        descricao: descricao.trim() || undefined,
        trigger_type: triggerType,
        trigger_config: {},
      },
      {
        onSuccess: (res: any) => {
          toast.success("Automacao criada com sucesso!");
          const id = res?.data?.id;
          navigate(id ? `/automations/${id}` : "/automations");
        },
        onError: () => toast.error("Erro ao criar automacao. Tente novamente."),
      }
    );
  }

  const inputCls =
    "flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-foreground">Nova Automacao</h1>
        <p className="text-sm text-muted-foreground">
          Defina o gatilho e as informacoes basicas. Etapas podem ser adicionadas depois.
        </p>
      </div>

      {/* Form */}
      <form onSubmit={handleSubmit} className="space-y-5 max-w-2xl">
        <div>
          <label className="mb-1 block text-sm font-medium text-foreground">Nome da Automacao *</label>
          <input
            type="text"
            placeholder="Ex: Onboarding Novos Contatos"
            className={inputCls}
            value={nome}
            onChange={(e) => setNome(e.target.value)}
          />
        </div>

        <div>
          <label className="mb-1 block text-sm font-medium text-foreground">Descricao</label>
          <textarea
            placeholder="Descreva o objetivo desta automacao..."
            className="flex min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring resize-y"
            value={descricao}
            onChange={(e) => setDescricao(e.target.value)}
          />
        </div>

        <div>
          <label className="mb-1 block text-sm font-medium text-foreground">Tipo de Gatilho *</label>
          <select className={inputCls} value={triggerType} onChange={(e) => setTriggerType(e.target.value)}>
            <option value="">Selecione o gatilho</option>
            {TRIGGER_OPTIONS.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
          <p className="mt-1 text-xs text-muted-foreground">
            O gatilho determina quando a automacao sera iniciada para cada contato.
          </p>
        </div>

        <div className="flex gap-3 pt-2">
          <button
            type="submit"
            disabled={!canSubmit}
            className="inline-flex items-center gap-2 rounded-md bg-primary px-6 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50 disabled:pointer-events-none"
          >
            {createMut.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            Criar Automacao
          </button>
          <Link
            to="/automations"
            className="inline-flex items-center rounded-md border border-input bg-background px-6 py-2.5 text-sm font-medium hover:bg-muted transition-colors"
          >
            Cancelar
          </Link>
        </div>
      </form>
    </div>
  );
}
