/**
 * Persona da Julia — contract §E.2 (`GET`/`PUT /api/agents/julia/persona`),
 * `/agentes/julia/persona`. Admin-only (server-enforced via `require_admin`;
 * this page also gates on `useIsAdmin()` so a non-admin never sees an
 * editable form that would 403 on submit — members are redirected to
 * `/agentes`).
 */
import { useEffect, useState, type FormEvent } from "react";
import { Navigate } from "react-router-dom";
import { Settings, ShieldAlert } from "lucide-react";
import { toast } from "sonner";
import { Badge, Button } from "@noctusai/lib/design-system";
import {
  PERSONA_EFFORTS,
  PERSONA_MODELS,
  usePersona,
  useUpdatePersona,
  type PersonaUpdateInput,
} from "@/hooks/usePersona";
import { useIsAdmin } from "@/hooks/useIsAdmin";
import { errorMessage } from "@/lib/errors";

const INPUT_CLASS =
  "w-full h-9 rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50";

const EFFORT_LABELS: Record<string, string> = {
  low: "Baixo",
  medium: "Médio",
  high: "Alto",
  xhigh: "Muito alto",
  max: "Máximo",
};

// Defaults for the very first persona (no row yet, contract §E.2 404 →
// "nenhuma persona ainda"). `nome`/`model`/`effort`/`idioma` use the
// backend's own canonical values (never invented — `model`/`effort` are
// CHECK-constrained, `app/stores/personas.py`); the free-text fields
// (`papel`, `tom`, `system_prompt_append`) stay EMPTY — persona content is
// the admin's to author, not a UI default.
function emptyForm(): PersonaUpdateInput {
  return {
    nome: "Julia",
    papel: "",
    model: PERSONA_MODELS[1],
    effort: "medium",
    tom: "",
    system_prompt_append: "",
    idioma: "pt-BR",
    org_display_name: "",
    project_display_name: "",
  };
}

export default function JuliaPersona() {
  const isAdmin = useIsAdmin();
  const { data: persona, showSkeleton, isError } = usePersona();
  const updatePersona = useUpdatePersona();
  // No persona row yet (contract §E.2 404, "Nenhuma persona ativa
  // configurada") vs. editing the existing one — drives copy + the submit
  // button label. `PUT` creates versão 1 either way (`update_persona`,
  // `app/routers/persona_router.py`); the UI difference is honesty about
  // which is about to happen.
  const isCreateMode = !persona;

  const [form, setForm] = useState<PersonaUpdateInput>(emptyForm());
  const [formError, setFormError] = useState<string | null>(null);

  useEffect(() => {
    if (!persona) return;
    setForm({
      nome: persona.nome,
      papel: persona.papel,
      model: persona.model,
      effort: persona.effort,
      tom: persona.tom ?? "",
      system_prompt_append: persona.system_prompt_append ?? "",
      idioma: persona.idioma,
      org_display_name: persona.org_display_name ?? "",
      project_display_name: persona.project_display_name ?? "",
    });
  }, [persona]);

  if (!isAdmin) {
    return <Navigate to="/agentes" replace />;
  }

  function setField<K extends keyof PersonaUpdateInput>(key: K, value: PersonaUpdateInput[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    try {
      await updatePersona.mutateAsync(form);
      toast.success(isCreateMode ? "Persona criada." : "Persona atualizada.");
    } catch (err) {
      // 422 → field-level validation error (contract §E.2) — the backend
      // returns a single message naming the offending field/allowlist.
      setFormError(errorMessage(err));
    }
  }

  return (
    <div className="max-w-2xl space-y-6">
      <div className="flex items-center gap-3">
        <Settings className="h-6 w-6 text-primary" />
        <div>
          <h1 className="text-2xl font-bold text-foreground">Persona da Julia</h1>
          <p className="text-sm text-muted-foreground">
            Configure o comportamento e o modelo usados pela Julia.
          </p>
        </div>
      </div>

      {showSkeleton ? (
        <div className="space-y-3" data-testid="persona-skeleton">
          <div className="h-9 w-full animate-pulse rounded-md bg-muted" />
          <div className="h-9 w-full animate-pulse rounded-md bg-muted" />
          <div className="h-24 w-full animate-pulse rounded-md bg-muted" />
        </div>
      ) : isError ? (
        <div className="flex flex-col items-center gap-2 rounded-lg border border-border bg-card p-8 text-muted-foreground">
          <ShieldAlert className="h-6 w-6" />
          <p className="text-sm">Erro ao carregar a persona.</p>
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="space-y-4 rounded-lg border border-border bg-card p-6">
          {persona ? (
            <Badge variant="muted" data-testid="persona-version">
              Versão {persona.versao}
            </Badge>
          ) : (
            <p className="text-sm text-muted-foreground" data-testid="persona-create-notice">
              Julia ainda não tem uma persona configurada e não vai responder até que uma seja
              salva aqui.
            </p>
          )}

          <div>
            <label className="mb-1 block text-sm font-medium text-foreground" htmlFor="persona-nome">
              Nome *
            </label>
            <input
              id="persona-nome"
              className={INPUT_CLASS}
              value={form.nome}
              required
              onChange={(e) => setField("nome", e.target.value)}
            />
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-foreground" htmlFor="persona-papel">
              Papel *
            </label>
            <input
              id="persona-papel"
              className={INPUT_CLASS}
              value={form.papel}
              placeholder="Ex: assistente de atendimento da Academia de Reciclagem"
              required
              onChange={(e) => setField("papel", e.target.value)}
            />
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label className="mb-1 block text-sm font-medium text-foreground" htmlFor="persona-model">
                Modelo *
              </label>
              <select
                id="persona-model"
                className={INPUT_CLASS}
                value={form.model}
                onChange={(e) => setField("model", e.target.value)}
                data-testid="persona-model-select"
              >
                {PERSONA_MODELS.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="mb-1 block text-sm font-medium text-foreground" htmlFor="persona-effort">
                Esforço *
              </label>
              <select
                id="persona-effort"
                className={INPUT_CLASS}
                value={form.effort}
                onChange={(e) => setField("effort", e.target.value)}
                data-testid="persona-effort-select"
              >
                {PERSONA_EFFORTS.map((ef) => (
                  <option key={ef} value={ef}>
                    {EFFORT_LABELS[ef] ?? ef}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-foreground" htmlFor="persona-tom">
              Tom
            </label>
            <input
              id="persona-tom"
              className={INPUT_CLASS}
              value={form.tom ?? ""}
              placeholder="Ex: formal, direto, acolhedor"
              onChange={(e) => setField("tom", e.target.value)}
            />
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label className="mb-1 block text-sm font-medium text-foreground" htmlFor="persona-org-name">
                Nome da organização exibido
              </label>
              <input
                id="persona-org-name"
                className={INPUT_CLASS}
                value={form.org_display_name ?? ""}
                onChange={(e) => setField("org_display_name", e.target.value)}
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-foreground" htmlFor="persona-project-name">
                Nome do projeto exibido
              </label>
              <input
                id="persona-project-name"
                className={INPUT_CLASS}
                value={form.project_display_name ?? ""}
                onChange={(e) => setField("project_display_name", e.target.value)}
              />
            </div>
          </div>

          <div>
            <label
              className="mb-1 block text-sm font-medium text-foreground"
              htmlFor="persona-system-prompt"
            >
              Instruções adicionais
            </label>
            <textarea
              id="persona-system-prompt"
              className={`${INPUT_CLASS} h-32 resize-y py-2`}
              value={form.system_prompt_append ?? ""}
              placeholder="Instruções extras anexadas ao prompt de sistema da Julia"
              onChange={(e) => setField("system_prompt_append", e.target.value)}
              data-testid="persona-system-prompt"
            />
          </div>

          {formError && (
            <p className="text-sm text-destructive" data-testid="persona-form-error">
              {formError}
            </p>
          )}

          <Button type="submit" variant="primary" disabled={updatePersona.isPending}>
            {updatePersona.isPending
              ? "Salvando..."
              : isCreateMode
                ? "Criar persona"
                : "Salvar"}
          </Button>
        </form>
      )}
    </div>
  );
}
