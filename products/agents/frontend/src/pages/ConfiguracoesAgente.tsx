/**
 * Configurações do agente — `/configuracoes-agente` (platform admin only,
 * server-enforced by `require_platform_admin`).
 *
 * Bia's runtime specs: approval timeout, max turns and the message rate
 * limit are editable (DB override, env default, "Restaurar padrão" resets);
 * the slot count is structural and read-only. Model and persona live on the
 * existing persona page (linked).
 */
import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { Settings, ShieldAlert, SlidersHorizontal } from "lucide-react";
import { toast } from "sonner";
import { Badge, Button } from "@noctusai/lib/design-system";
import {
  useAgentSettings,
  useUpdateAgentSettings,
  type AgentSetting,
  type AgentSettingsPatch,
} from "@/hooks/useAgentSettings";
import { ApiError, errorMessage } from "@/lib/errors";

const INPUT_CLASS =
  "w-full h-9 rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-hidden focus:ring-2 focus:ring-primary/50";

const LABELS: Record<string, { label: string; help: string }> = {
  approval_timeout_seconds: {
    label: "Tempo limite de aprovação (segundos)",
    help: "Uma aprovação sem resposta expira e a ação é negada. Ocupa um slot do executor enquanto espera.",
  },
  max_turns: { label: "Máximo de turnos por resposta", help: "Limite de passos que o agente de chat legado executa em uma resposta." },
  messages_rate_limit: {
    label: "Limite de mensagens por usuário",
    help: "Formato N/second|minute|hour|day, ex.: 20/minute.",
  },
  numero_fallback_atendimento: {
    label: "Número de atendimento (passagem a uma pessoa)",
    help: "Quando um agente passa a conversa para uma pessoa, a equipe é avisada neste número. É o número do dono, cadastrado uma única vez no core (Notificações → Quem recebe os avisos); aqui só aparece. Sem ele, nenhum agente de conversa pode ser publicado.",
  },
  claude_cli_slots: {
    label: "Conversas simultâneas (slots)",
    help: "Estrutural — definido na imagem e no compose; muda apenas com um novo deploy.",
  },
};

type FormState = Record<string, string>;

function toForm(items: AgentSetting[]): FormState {
  return Object.fromEntries(items.map((i) => [i.key, i.value === null ? "" : String(i.value)]));
}

export default function ConfiguracoesAgente() {
  const { data: items, error, showSkeleton, isError } = useAgentSettings();
  const update = useUpdateAgentSettings();
  const [form, setForm] = useState<FormState>({});

  useEffect(() => {
    if (items) setForm(toForm(items));
  }, [items]);

  async function save(patch: AgentSettingsPatch) {
    try {
      await update.mutateAsync(patch);
      toast.success("Configurações salvas.");
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!items) return;
    const patch: Record<string, number | string | null> = {};
    for (const item of items) {
      if (!item.editable) continue;
      const raw = (form[item.key] ?? "").trim();
      if (raw === (item.value === null ? "" : String(item.value))) continue;
      patch[item.key] = raw === "" && item.default === null ? null : typeof item.default === "number" ? Number(raw) : raw;
    }
    if (Object.keys(patch).length === 0) {
      toast.info("Nada para salvar.");
      return;
    }
    await save(patch as AgentSettingsPatch);
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <SlidersHorizontal className="h-6 w-6 text-primary" />
        <div>
          <h1 className="text-2xl font-bold text-foreground">Configurações do agente</h1>
          <p className="text-sm text-muted-foreground">Parâmetros do executor claude_sdk e do chat legado. Valem sem novo deploy.</p>
        </div>
        <Link
          to="/agentes/bia/persona"
          className="ml-auto inline-flex items-center gap-1.5 rounded-md border border-input bg-background px-3 py-1.5 text-xs font-medium text-foreground hover:bg-accent"
        >
          <Settings className="h-3.5 w-3.5" />
          Modelo e persona
        </Link>
      </div>

      {showSkeleton ? (
        <div className="h-48 animate-pulse rounded-lg border border-border bg-card" data-testid="agent-settings-skeleton" />
      ) : isError ? (
        <div
          className="flex flex-col items-center gap-2 rounded-lg border border-border bg-card p-8 text-muted-foreground"
          data-testid="agent-settings-error"
        >
          <ShieldAlert className="h-6 w-6" />
          <p className="text-sm">
            {error instanceof ApiError && error.status === 403
              ? "Restrito aos administradores da plataforma NoctusAI."
              : errorMessage(error)}
          </p>
        </div>
      ) : items ? (
        <>
          <form
            onSubmit={handleSubmit}
            className="space-y-4 rounded-lg border border-border bg-card p-6"
            data-testid="agent-settings-form"
          >
            {items.map((item) => {
              const meta = LABELS[item.key] ?? { label: item.key, help: "" };
              return (
                <div key={item.key} className="space-y-1">
                  <div className="flex items-center gap-2">
                    <label htmlFor={`setting-${item.key}`} className="text-sm font-medium text-foreground">
                      {meta.label}
                    </label>
                    <Badge variant="outline">{item.source === "db" ? "personalizado" : item.source === "core" ? "do core" : "padrão"}</Badge>
                    {item.editable && item.source === "db" && (
                      <button
                        type="button"
                        className="text-xs text-primary hover:underline"
                        onClick={() => save({ [item.key]: null } as AgentSettingsPatch)}
                        disabled={update.isPending}
                      >
                        {item.default === null ? "Remover" : `Restaurar padrão (${String(item.default)})`}
                      </button>
                    )}
                  </div>
                  <input
                    id={`setting-${item.key}`}
                    className={INPUT_CLASS}
                    type={typeof item.default === "number" ? "number" : "text"}
                    min={item.min ?? undefined}
                    max={item.max ?? undefined}
                    placeholder={item.source === "core" ? "Nenhum número ativo no core" : undefined}
                    readOnly={!item.editable}
                    disabled={!item.editable}
                    value={form[item.key] ?? ""}
                    onChange={(e) => setForm((prev) => ({ ...prev, [item.key]: e.target.value }))}
                  />
                  <p className="text-xs text-muted-foreground">{meta.help}</p>
                </div>
              );
            })}
            <div className="flex justify-end">
              <Button type="submit" disabled={update.isPending}>
                Salvar
              </Button>
            </div>
          </form>
        </>
      ) : null}
    </div>
  );
}
