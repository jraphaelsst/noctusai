/**
 * Per-agent config form — patches `model` / `provider` for one agent in
 * the named YAML config. Calls `PATCH /api/configs/{name}` and surfaces
 * the engine's response (or the 503 / 400 error) inline.
 *
 * Defaults to the "default" config since that's the one the engine boots
 * with; the agents-grid endpoint also reads from it.
 */
import { useState, FormEvent } from "react";
import { Save, AlertCircle, CheckCircle, Loader2 } from "lucide-react";
import { patchConfig } from "@/lib/api";

interface ConfigFormProps {
  agentName: string;
  /** Config name to patch — defaults to "default". */
  configName?: string;
  /** Optional initial values from the loaded config (for the placeholders). */
  initialModel?: string;
  initialProvider?: string;
}

export function ConfigForm({
  agentName,
  configName = "default",
  initialModel,
  initialProvider,
}: ConfigFormProps) {
  const [model, setModel] = useState(initialModel ?? "");
  const [provider, setProvider] = useState(initialProvider ?? "");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<number | null>(null);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setSavedAt(null);

    if (!model && !provider) {
      setError("At least one of model / provider must be set.");
      return;
    }

    setSubmitting(true);
    try {
      await patchConfig(configName, {
        agent_name: agentName,
        model: model || undefined,
        provider: provider || undefined,
      });
      setSavedAt(Date.now());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form
      onSubmit={handleSubmit}
      data-testid="config-form"
      className="rounded-lg border border-border bg-card p-5 space-y-4"
    >
      <div>
        <h3 className="font-semibold text-foreground">Override config</h3>
        <p className="text-xs text-muted-foreground">
          Patches <code>{configName}</code> → {agentName}. Either field is optional.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <label className="block text-sm">
          <span className="text-foreground">Model</span>
          <input
            type="text"
            value={model}
            onChange={(e) => setModel(e.target.value)}
            placeholder={initialModel || "claude-3-7-sonnet-latest"}
            className="mt-1 block w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
          />
        </label>
        <label className="block text-sm">
          <span className="text-foreground">Provider</span>
          <input
            type="text"
            value={provider}
            onChange={(e) => setProvider(e.target.value)}
            placeholder={initialProvider || "anthropic"}
            className="mt-1 block w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
          />
        </label>
      </div>

      {error && (
        <div className="flex items-start gap-2 text-sm text-destructive" role="alert">
          <AlertCircle className="h-4 w-4 mt-0.5" />
          <span>{error}</span>
        </div>
      )}
      {savedAt && (
        <div className="flex items-center gap-2 text-sm text-green-600">
          <CheckCircle className="h-4 w-4" />
          <span>Saved.</span>
        </div>
      )}

      <button
        type="submit"
        disabled={submitting}
        className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-60"
      >
        {submitting ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <Save className="h-4 w-4" />
        )}
        Save
      </button>
    </form>
  );
}
