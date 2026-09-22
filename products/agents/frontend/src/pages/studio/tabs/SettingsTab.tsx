/**
 * Agent Studio — "Configurações" (CONTRACT §G): the draft's model, effort,
 * max_turns, idioma, tool_policy and changelog note (`PATCH .../draft`), plus
 * the agent-level `publicacao_limiar` (`PATCH /api/studio/agents/{key}`).
 * Without a draft the active version's settings are shown read-only.
 */
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Button, EmptyState } from "@noctusai/lib/design-system";
import {
  MAX_TURNS_MAX,
  MAX_TURNS_MIN,
  STUDIO_EFFORTS,
  STUDIO_MODELS,
  type DraftPatchInput,
  type StudioEffort,
  type StudioModel,
  type VersionDetail,
} from "@/api/studio/types";
import { PromptMarkdownField } from "@/components/studio/PromptMarkdownField";
import { StudioError, StudioLoading } from "@/components/studio/StudioStates";
import { useUpdateStudioAgent } from "@/hooks/studio/useStudioAgents";
import { useAgentVersionRefs, useUpdateDraft, useVersion } from "@/hooks/studio/useVersions";
import { useIsAdmin } from "@/hooks/useIsAdmin";
import { errorMessage } from "@/lib/errors";

const INPUT_CLASS =
  "w-full h-9 rounded-md border border-input bg-background px-3 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 disabled:opacity-70";

const EFFORT_LABELS: Record<StudioEffort, string> = {
  low: "Baixo",
  medium: "Médio",
  high: "Alto",
  xhigh: "Muito alto",
  max: "Máximo",
};

interface Form {
  model: StudioModel;
  effort: StudioEffort;
  max_turns: string;
  idioma: string;
  web_search: boolean;
  knowledge: boolean;
  notas: string;
}

function toForm(v: VersionDetail): Form {
  return {
    model: v.model,
    effort: v.effort,
    max_turns: String(v.max_turns),
    idioma: v.idioma,
    web_search: v.tool_policy.web_search,
    knowledge: v.tool_policy.knowledge,
    notas: v.notas ?? "",
  };
}

/** Only the fields that changed — the PATCH is partial by contract. */
function settingsPatch(v: VersionDetail, f: Form): DraftPatchInput {
  const p: DraftPatchInput = {};
  if (f.model !== v.model) p.model = f.model;
  if (f.effort !== v.effort) p.effort = f.effort;
  if (Number(f.max_turns) !== v.max_turns) p.max_turns = Number(f.max_turns);
  if (f.idioma.trim() !== v.idioma) p.idioma = f.idioma.trim();
  if (f.web_search !== v.tool_policy.web_search || f.knowledge !== v.tool_policy.knowledge)
    p.tool_policy = { web_search: f.web_search, knowledge: f.knowledge };
  if (f.notas !== (v.notas ?? "")) p.notas = f.notas || null;
  return p;
}

export default function SettingsTab({ agentKey }: { agentKey: string }) {
  const isAdmin = useIsAdmin();
  const refs = useAgentVersionRefs(agentKey);
  const target = refs.draft ?? refs.ativa;
  const version = useVersion(agentKey, target?.id);
  const updateDraft = useUpdateDraft(agentKey);
  const updateAgent = useUpdateStudioAgent(agentKey);

  const data = version.isPlaceholderData ? undefined : version.data;
  const editable = isAdmin && data?.status === "rascunho";
  const [form, setForm] = useState<Form | null>(null);
  const [limiar, setLimiar] = useState("");
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    if (data) setForm(toForm(data));
  }, [data]);
  useEffect(() => {
    if (refs.data && !refs.isPlaceholderData) setLimiar(String(refs.data.publicacao_limiar));
  }, [refs.data, refs.isPlaceholderData]);

  if (refs.showSkeleton || (target && version.showSkeleton)) return <StudioLoading rows={4} />;
  if (refs.isError) return <StudioError error={refs.error} onRetry={refs.refetch} />;
  if (version.isError) return <StudioError error={version.error} onRetry={version.refetch} />;
  const agent = refs.data;

  async function saveDraft() {
    if (!data || !form) return;
    const turns = Number(form.max_turns);
    if (!Number.isInteger(turns) || turns < MAX_TURNS_MIN || turns > MAX_TURNS_MAX) {
      setErro(`Máximo de turnos deve ser um inteiro entre ${MAX_TURNS_MIN} e ${MAX_TURNS_MAX}.`);
      return;
    }
    const patch = settingsPatch(data, form);
    if (Object.keys(patch).length === 0) {
      toast.info("Nada para salvar.");
      return;
    }
    setErro(null);
    try {
      await updateDraft.mutateAsync(patch);
      toast.success("Configurações do rascunho salvas.");
    } catch (err) {
      setErro(errorMessage(err));
    }
  }

  async function saveLimiar() {
    const value = Number(limiar.replace(",", "."));
    if (!Number.isFinite(value) || value < 0 || value > 1) {
      toast.error("O limiar deve estar entre 0 e 1 (ex.: 0.8).");
      return;
    }
    try {
      await updateAgent.mutateAsync({ publicacao_limiar: value });
      toast.success("Limiar de publicação atualizado.");
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }

  return (
    <div className="grid gap-4 lg:grid-cols-2" data-testid="settings-tab">
      <section className="space-y-3 rounded-lg border border-border bg-card p-4">
        <h2 className="text-sm font-semibold">
          Versão {target ? `v${target.versao}` : ""} {data?.status === "rascunho" ? "(rascunho)" : ""}
        </h2>
        {!target || !form ? (
          <EmptyState message="Este agente ainda não tem versões." />
        ) : (
          <>
            {!editable && (
              <p className="text-xs text-muted-foreground">
                {refs.draft ? "Somente administradores editam o rascunho." : "Versão publicada — somente leitura."}
              </p>
            )}
            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <label htmlFor="cfg-model" className="mb-1 block text-xs font-medium">
                  Modelo
                </label>
                <select
                  id="cfg-model"
                  className={INPUT_CLASS}
                  value={form.model}
                  disabled={!editable}
                  onChange={(e) => setForm({ ...form, model: e.target.value as StudioModel })}
                >
                  {STUDIO_MODELS.map((m) => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label htmlFor="cfg-effort" className="mb-1 block text-xs font-medium">
                  Esforço
                </label>
                <select
                  id="cfg-effort"
                  className={INPUT_CLASS}
                  value={form.effort}
                  disabled={!editable}
                  onChange={(e) => setForm({ ...form, effort: e.target.value as StudioEffort })}
                >
                  {STUDIO_EFFORTS.map((ef) => (
                    <option key={ef} value={ef}>
                      {EFFORT_LABELS[ef]}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label htmlFor="cfg-turns" className="mb-1 block text-xs font-medium">
                  Máximo de turnos
                </label>
                <input
                  id="cfg-turns"
                  type="number"
                  min={MAX_TURNS_MIN}
                  max={MAX_TURNS_MAX}
                  className={INPUT_CLASS}
                  value={form.max_turns}
                  disabled={!editable}
                  onChange={(e) => setForm({ ...form, max_turns: e.target.value })}
                />
              </div>
              <div>
                <label htmlFor="cfg-idioma" className="mb-1 block text-xs font-medium">
                  Idioma
                </label>
                <input
                  id="cfg-idioma"
                  className={INPUT_CLASS}
                  value={form.idioma}
                  disabled={!editable}
                  onChange={(e) => setForm({ ...form, idioma: e.target.value })}
                />
              </div>
            </div>
            <fieldset className="space-y-1">
              <legend className="mb-1 text-xs font-medium">Ferramentas</legend>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={form.web_search}
                  disabled={!editable}
                  onChange={(e) => setForm({ ...form, web_search: e.target.checked })}
                />
                Busca na web
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={form.knowledge}
                  disabled={!editable}
                  onChange={(e) => setForm({ ...form, knowledge: e.target.checked })}
                />
                Base de conhecimento (kb_buscar / kb_ler)
              </label>
            </fieldset>
            <div>
              <label htmlFor="cfg-notas" className="mb-1 block text-xs font-medium">
                Notas da versão (changelog)
              </label>
              <PromptMarkdownField
                id="cfg-notas"
                value={form.notas}
                onChange={(v) => setForm({ ...form, notas: v })}
                readOnly={!editable}
                rows={3}
                mono={false}
                semTokens
              />
            </div>
            {erro && (
              <p className="text-sm text-destructive" role="alert">
                {erro}
              </p>
            )}
            {editable && (
              <div className="flex justify-end">
                <Button variant="primary" onClick={saveDraft} disabled={updateDraft.isPending} data-testid="settings-save">
                  {updateDraft.isPending ? "Salvando..." : "Salvar configurações"}
                </Button>
              </div>
            )}
          </>
        )}
      </section>

      <section className="space-y-3 rounded-lg border border-border bg-card p-4">
        <h2 className="text-sm font-semibold">Agente</h2>
        <div>
          <label htmlFor="cfg-limiar" className="mb-1 block text-xs font-medium">
            Limiar de publicação (0–1)
          </label>
          <input
            id="cfg-limiar"
            inputMode="decimal"
            className={INPUT_CLASS}
            value={limiar}
            disabled={!isAdmin}
            onChange={(e) => setLimiar(e.target.value)}
          />
          <p className="mt-1 text-xs text-muted-foreground">
            Publicar exige uma avaliação concluída no hash atual do rascunho com nota igual ou maior — ou uma
            justificativa de exceção registrada.
          </p>
        </div>
        {isAdmin && agent && (
          <div className="flex justify-end">
            <Button
              size="sm"
              variant="primary"
              onClick={saveLimiar}
              disabled={updateAgent.isPending || Number(limiar) === agent.publicacao_limiar}
            >
              Salvar limiar
            </Button>
          </div>
        )}
      </section>
    </div>
  );
}
